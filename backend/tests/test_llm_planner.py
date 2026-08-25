"""O planejador por modelo de linguagem (plano de correção §18).

O que precisa estar certo aqui não é "o LLM desenha bem" — isso depende do
modelo e não se testa em CI. É o **contrato em volta dele**:

* tudo que o modelo devolve é entrada não confiável, e o parse recusa cada
  forma de lixo com um motivo específico;
* um motivo específico vira crítica na segunda tentativa;
* provedor fora do ar ou plano insalvável cai nas receitas **com aviso**, e
  nunca derruba a geração;
* o plano aceito atravessa o mesmo executor, a mesma paleta fechada e o mesmo
  revisor que uma receita — as garantias do agente não dependem de quem
  planejou.
"""

from __future__ import annotations

import pytest

from assetflow.generation.pixel_agent import (
    AssetFlowPixelAgent,
    ChatConfig,
    DrawingBrief,
    LLMPlanner,
    RecipePlanner,
)
from assetflow.generation.pixel_agent.llm.client import ChatError
from assetflow.generation.pixel_agent.llm.prompting import (
    LLMPlanError,
    build_prompt,
    parse_plan,
)

_BRIEF = DrawingBrief(
    subject="a rusty key",
    asset_type="prop",
    width=32,
    height=32,
    max_colors=8,
    transparent=True,
    seed=7,
)

_VALID = """
{
  "palette": {"base": "#b08d57", "shade": "#6d5433", "light": "#d9bd85",
              "accent": "#8a6a3d", "outline": "#1a1410"},
  "regions": [{"name": "haste", "bounds": [14, 6, 18, 24]}],
  "calls": [
    {"tool": "fill_rect", "params": {"x0": 14, "y0": 6, "x1": 17, "y1": 24,
                                     "color": "#b08d57"}, "note": "haste"},
    {"tool": "draw_circle", "params": {"cx": 16, "cy": 7, "radius": 5,
                                       "color": "#b08d57", "filled": false},
     "note": "argola"},
    {"tool": "fill_rect", "params": {"x0": 18, "y0": 20, "x1": 22, "y1": 22,
                                     "color": "#6d5433"}, "note": "dente"}
  ]
}
"""


class FakeChat:
    """Um provedor de mentira, com respostas roteirizadas."""

    def __init__(self, *responses: str | Exception) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []
        self.config = ChatConfig(base_url="http://fake/v1", model="fake-model")

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self._responses:
            raise AssertionError("o planejador pediu mais respostas do que o roteiro")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def health(self) -> tuple[bool, str | None]:
        return (True, None)

    def describe(self) -> str:
        return "fake"


# ---------------------------------------------------------------------------
# O prompt
# ---------------------------------------------------------------------------
def test_the_prompt_states_the_canvas_limits():
    """O erro que os modelos mais cometem é coordenada fora da grade."""
    system, user = build_prompt(_BRIEF)

    assert "[0, 31]" in system
    assert "at most 8 distinct colors" in system.lower()
    assert "a rusty key" in user
    assert "32x32" in user
    # O contorno é do sistema: pedir ao modelo produziria contorno duplo.
    assert "Do NOT draw the outline" in system


def test_the_prompt_advice_changes_with_the_canvas_size():
    tiny, _ = build_prompt(
        DrawingBrief(subject="key", asset_type="prop", width=16, height=16)
    )
    large, _ = build_prompt(
        DrawingBrief(subject="key", asset_type="prop", width=64, height=64)
    )
    assert "tiny" in tiny
    assert "tiny" not in large


# ---------------------------------------------------------------------------
# O parse — tudo que vem do modelo é entrada não confiável
# ---------------------------------------------------------------------------
def test_a_valid_plan_becomes_a_drawing_plan():
    plan = parse_plan(_VALID, _BRIEF)

    assert plan.recipe == "llm"
    assert plan.canvas == (32, 32)
    assert len(plan.calls) == 3
    assert plan.calls[0].tool == "fill_rect"
    assert plan.palette.outline == "#1a1410"
    assert plan.regions["haste"] == (14, 6, 18, 24)


def test_markdown_fences_and_prose_are_tolerated():
    """Modelos pequenos embrulham JSON mesmo quando se pede o contrário."""
    plan = parse_plan(f"Sure! Here is the plan:\n```json\n{_VALID}\n```\n", _BRIEF)
    assert len(plan.calls) == 3


def test_out_of_canvas_coordinates_are_refused():
    """Recusar, e não recortar: a coordenada fora significa que o modelo
    entendeu o tamanho errado, e recortar acharia a forma contra a borda."""
    raw = """{"palette": {"base": "#fff"},
              "calls": [{"tool": "fill_rect",
                         "params": {"x0": 0, "y0": 0, "x1": 99, "y1": 4,
                                    "color": "#ffffff"}}]}"""
    with pytest.raises(LLMPlanError) as excinfo:
        parse_plan(raw, _BRIEF)
    assert "outside the canvas" in str(excinfo.value)


def test_fractional_coordinates_are_refused():
    raw = """{"palette": {"base": "#fff"},
              "calls": [{"tool": "draw_pixel",
                         "params": {"x": 4.5, "y": 4, "color": "#ffffff"}}]}"""
    with pytest.raises(LLMPlanError) as excinfo:
        parse_plan(raw, _BRIEF)
    assert "fractional" in str(excinfo.value)


def test_an_invented_tool_is_refused_with_the_allowed_list():
    raw = """{"palette": {"base": "#fff"},
              "calls": [{"tool": "draw_star",
                         "params": {"x": 4, "y": 4, "color": "#ffffff"}}]}"""
    with pytest.raises(LLMPlanError) as excinfo:
        parse_plan(raw, _BRIEF)
    message = str(excinfo.value)
    assert "draw_star" in message
    # A mensagem vira a crítica da segunda tentativa: ela precisa ensinar.
    assert "fill_rect" in message


def test_common_tool_aliases_are_accepted():
    """Recusar um plano bom por um sinônimo seria desperdício."""
    raw = """{"palette": {"base": "#fff"},
              "calls": [{"tool": "rect",
                         "params": {"x0": 1, "y0": 1, "x1": 5, "y1": 5,
                                    "color": "#ffffff"}}]}"""
    assert parse_plan(raw, _BRIEF).calls[0].tool == "fill_rect"


def test_params_at_the_top_level_are_accepted():
    """Alguns modelos põem os parâmetros ao lado de `tool`."""
    raw = """{"palette": {"base": "#fff"},
              "calls": [{"tool": "fill_rect", "x0": 1, "y0": 1, "x1": 5,
                         "y1": 5, "color": "#ffffff"}]}"""
    assert parse_plan(raw, _BRIEF).calls[0].params["x1"] == 5


def test_a_plan_with_no_calls_is_refused():
    with pytest.raises(LLMPlanError):
        parse_plan('{"palette": {"base": "#fff"}, "calls": []}', _BRIEF)


def test_garbage_is_refused():
    for raw in ["", "não sei desenhar isso", "{", "[]"]:
        with pytest.raises(LLMPlanError):
            parse_plan(raw, _BRIEF)


def test_missing_palette_roles_are_derived_but_the_outline_is_not_invented():
    """Sem contorno declarado, um escuro previsível — nunca um tom qualquer."""
    plan = parse_plan(
        '{"palette": {"base": "#8a8a92"}, "calls": [{"tool": "draw_pixel",'
        ' "params": {"x": 1, "y": 1, "color": "#8a8a92"}}]}',
        _BRIEF,
    )
    assert plan.palette.base == "#8a8a92"
    assert plan.palette.light != plan.palette.base
    assert plan.palette.shade != plan.palette.base
    assert plan.palette.outline == "#1a1a1a"


# ---------------------------------------------------------------------------
# O planejador
# ---------------------------------------------------------------------------
def test_the_planner_returns_the_model_plan():
    planner = LLMPlanner(FakeChat(_VALID))
    plan = planner.plan(_BRIEF)

    assert plan.recipe == "llm"
    assert planner.last_fallback_reason is None


def test_a_rejected_plan_is_retried_with_the_reason():
    """A crítica é o que faz a segunda tentativa valer a pena."""
    bad = '{"palette": {"base": "#fff"}, "calls": [{"tool": "draw_pixel",' \
          ' "params": {"x": 99, "y": 1, "color": "#ffffff"}}]}'
    chat = FakeChat(bad, _VALID)
    planner = LLMPlanner(chat)

    plan = planner.plan(_BRIEF)

    assert plan.recipe == "llm"
    assert len(chat.calls) == 2
    segunda = chat.calls[1][1]
    assert "rejected" in segunda
    assert "outside the canvas" in segunda


def test_it_falls_back_to_recipes_after_exhausting_the_attempts():
    """E o motivo fica guardado — a queda tem de virar aviso no job."""
    planner = LLMPlanner(FakeChat("lixo", "mais lixo"), max_attempts=2)
    plan = planner.plan(_BRIEF)

    assert plan.recipe != "llm"
    assert planner.last_fallback_reason
    assert "2 tentativas" in planner.last_fallback_reason


def test_a_provider_that_is_down_does_not_retry():
    """Insistir contra uma rede fora do ar só gasta o tempo de quem espera."""
    chat = FakeChat(ChatError("conexão recusada"), _VALID)
    planner = LLMPlanner(chat)

    plan = planner.plan(_BRIEF)

    assert plan.recipe != "llm"
    assert len(chat.calls) == 1
    assert "conexão recusada" in planner.last_fallback_reason


def test_the_llm_planner_recognises_everything_while_the_provider_is_up():
    """É a razão de ele existir: um LLM não tem lista de objetos conhecidos."""
    planner = LLMPlanner(FakeChat())
    assert planner.recognizes("uma escrivaninha art déco") is True
    assert planner.recognizes("qualquer coisa") is True


def test_without_a_provider_it_promises_only_what_the_recipes_deliver():
    """Prometer mais faria a escolha automática mandar para cá o que o
    agente, sem LLM, não sabe desenhar."""
    planner = LLMPlanner(_UnconfiguredChat())

    assert planner.recognizes("uma arvore") is True
    assert planner.recognizes("uma escrivaninha art déco") is False


class _UnconfiguredChat(FakeChat):
    def __init__(self) -> None:
        super().__init__()
        self.config = ChatConfig()

    def health(self) -> tuple[bool, str | None]:
        return (False, "planejador por LLM não configurado")


# ---------------------------------------------------------------------------
# O plano do modelo atravessa as mesmas garantias
# ---------------------------------------------------------------------------
def test_a_model_plan_keeps_the_grid_the_palette_and_the_outline():
    """O agente não afrouxa nada por o plano ter vindo de um LLM."""
    agent = AssetFlowPixelAgent(planner=LLMPlanner(FakeChat(_VALID)))
    drawing = agent.draw(_BRIEF)

    from PIL import Image
    import io

    image = Image.open(io.BytesIO(drawing.data)).convert("RGBA")
    colors = {
        image.getpixel((x, y))
        for y in range(image.height)
        for x in range(image.width)
        if image.getpixel((x, y))[3] > 0
    }

    assert image.size == (32, 32), "a grade continua sendo a pedida"
    assert len(colors) <= 8, "o orçamento de cores continua fechado"
    assert "PX-AGENT-OUTLINE" in drawing.session.repairs, "o contorno continua"
    # O log continua reconstruindo o desenho, plano de LLM ou não.
    assert drawing.session.tool_calls > len(drawing.plan.calls)


def test_an_out_of_vocabulary_subject_now_gets_a_real_plan():
    """O caso que motivou tudo: um sujeito fora das receitas.

    Com o planejador por LLM, "escrivaninha" deixa de cair na forma genérica —
    o modelo planeja, e o agente desenha o que ele planejou.
    """
    agent = AssetFlowPixelAgent(planner=LLMPlanner(FakeChat(_VALID)))
    drawing = agent.draw(
        DrawingBrief(subject="uma escrivaninha", asset_type="prop", width=32,
                     height=32, max_colors=8, transparent=True, seed=1)
    )
    assert drawing.plan.recipe == "llm"

    # E, sem LLM, ele volta a ser honesto sobre o limite.
    receitas = AssetFlowPixelAgent(planner=RecipePlanner())
    assert receitas.draw(
        DrawingBrief(subject="uma escrivaninha", asset_type="prop", width=32,
                     height=32, max_colors=8, transparent=True, seed=1)
    ).plan.recipe == "generic"


# ---------------------------------------------------------------------------
# O caminho HTTP de verdade
# ---------------------------------------------------------------------------
def test_the_client_speaks_the_openai_chat_format():
    """Sobe um servidor de mentira e confere o que sai e o que entra.

    Os testes acima usam um provedor falso no nível do Python, o que não
    exercita a serialização, os cabeçalhos nem o parse da resposta. Este sobe
    HTTP de verdade — é o que garante que a integração funcione com Ollama,
    LM Studio ou OpenAI sem ninguém ter descoberto na primeira geração real.
    """
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from assetflow.generation.pixel_agent.llm.client import ChatClient

    recebido: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - assinatura da stdlib
            length = int(self.headers["Content-Length"])
            recebido["path"] = self.path
            recebido["auth"] = self.headers.get("Authorization")
            recebido["body"] = _json.loads(self.rfile.read(length))
            payload = _json.dumps(
                {"choices": [{"message": {"role": "assistant", "content": _VALID}}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # silencia o log da stdlib
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        client = ChatClient(
            ChatConfig(
                base_url=f"http://127.0.0.1:{port}/v1",
                model="modelo-de-teste",
                api_key_env="ASSETFLOW_TEST_PLANNER_KEY",
                timeout_s=5,
            )
        )
        plan = LLMPlanner(client).plan(_BRIEF)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert plan.recipe == "llm"
    assert recebido["path"] == "/v1/chat/completions"
    assert recebido["body"]["model"] == "modelo-de-teste"
    assert [m["role"] for m in recebido["body"]["messages"]] == ["system", "user"]
    # Sem a variável de ambiente definida, não se manda cabeçalho de chave:
    # provedores locais recusam requisições com Authorization vazio.
    assert recebido["auth"] is None


def test_an_unreachable_provider_falls_back_instead_of_failing():
    """A porta fechada é o caso comum: Ollama que não está rodando."""
    from assetflow.generation.pixel_agent.llm.client import ChatClient

    planner = LLMPlanner(
        ChatClient(
            ChatConfig(
                base_url="http://127.0.0.1:9/v1",  # porta "discard", sempre fechada
                model="qualquer",
                timeout_s=2,
            )
        )
    )
    plan = planner.plan(_BRIEF)

    assert plan.recipe != "llm"
    assert planner.last_fallback_reason
    assert "não foi possível falar" in planner.last_fallback_reason
