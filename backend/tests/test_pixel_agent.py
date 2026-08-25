"""O AssetFlow Pixel Agent (plano de correção §15 a §25, §48 e §50).

Este arquivo cobra o agente pelas propriedades que o distinguem de um motor —
grade nativa, paleta fechada, coordenadas inteiras, revisão que descreve em
vez de mexer, e um histórico que reconstrói o desenho.

A entrega mínima do §48 é nomeada nos casos: árvore, pedra, poção, baú, bloco,
tile, moeda e espada simples, em 16×16 e 32×32.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from assetflow.generation.pixel_agent import (
    AGENT_ID,
    AssetFlowPixelAgent,
    DrawingBrief,
    PaletteManager,
    PixelCanvas,
    PixelReviewer,
    PixelToolExecutor,
    PlanningAgent,
    QualityMode,
    ToolCall,
)
from assetflow.generation.pixel_agent.contracts.command import ToolCallLog
from assetflow.generation.pixel_agent.session import ITERATIONS_BY_QUALITY


#: A entrega mínima da primeira versão (plano de correção §48).
FASE_1 = [
    ("uma árvore com folhas", "tree"),
    ("stone rock", "rock"),
    ("red potion", "potion"),
    ("wooden chest", "chest"),
    ("grass block", "tile"),
    ("stone tile", "tile"),
    ("gold coin", "coin"),
    ("simple sword", "sword"),
]


def _brief(subject: str, *, size: int = 32, colors: int | None = 16, seed: int = 99):
    return DrawingBrief(
        subject=subject,
        asset_type="prop",
        width=size,
        height=size,
        max_colors=colors,
        transparent=True,
        seed=seed,
    )


def _image(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGBA")


def _stats(image: Image.Image) -> dict[str, int]:
    colors = set()
    opaque = 0
    for y in range(image.height):
        for x in range(image.width):
            pixel = image.getpixel((x, y))
            if pixel[3] == 0:
                continue
            opaque += 1
            colors.add(pixel)
    return {"opaque": opaque, "colors": len(colors)}


# ---------------------------------------------------------------------------
# Canvas (§20)
# ---------------------------------------------------------------------------
def test_canvas_counts_only_opaque_colors():
    """Pixel transparente não é cor do sprite e não gasta paleta."""
    canvas = PixelCanvas(4, 4)
    canvas.set(0, 0, (255, 0, 0, 255))
    canvas.set(1, 0, (255, 0, 0, 255))
    canvas.set(2, 0, (0, 0, 0, 0))

    assert canvas.colors() == {(255, 0, 0, 255): 2}
    assert canvas.stats().color_count == 1
    assert canvas.stats().opaque_pixels == 2


def test_canvas_finds_orphans_and_edges():
    canvas = PixelCanvas(8, 8)
    canvas.set(0, 0, (10, 20, 30, 255))  # sozinho no canto
    canvas.set(4, 4, (10, 20, 30, 255))
    canvas.set(4, 5, (10, 20, 30, 255))  # par com vizinho

    assert (0, 0) in canvas.orphans()
    assert (4, 4) not in canvas.orphans()
    assert (3, 4) in canvas.edge_pixels()


def test_canvas_refuses_a_degenerate_size():
    with pytest.raises(ValueError):
        PixelCanvas(0, 10)


# ---------------------------------------------------------------------------
# Coordenadas inteiras (§21)
# ---------------------------------------------------------------------------
def test_fractional_coordinates_are_refused():
    """§21: a grade não tem meio pixel, e truncar esconderia o erro."""
    canvas = PixelCanvas(8, 8)
    executor = PixelToolExecutor()
    log = ToolCallLog()

    record = executor.execute(
        canvas, ToolCall("draw_pixel", {"x": 2.5, "y": 1, "color": "#fff"}), log
    )
    assert record.error is not None
    assert "fracion" in record.error
    assert record.pixels_changed == 0


def test_an_integer_written_as_float_is_accepted():
    """``12.0`` é inteiro escrito como float — acontece o tempo todo em JSON."""
    canvas = PixelCanvas(8, 8)
    executor = PixelToolExecutor()
    record = executor.execute(
        canvas, ToolCall("draw_pixel", {"x": 2.0, "y": 1.0, "color": "#ffffff"})
    )
    assert record.error is None
    assert canvas.is_opaque(2, 1)


# ---------------------------------------------------------------------------
# Paleta fechada (§22)
# ---------------------------------------------------------------------------
def test_palette_manager_refuses_to_invent_a_new_colour():
    """§22: com 2 cores no orçamento, não existe terceira."""
    palette = PaletteManager(["#ff0000", "#00ff00"], max_colors=2)

    assert palette.resolve("#ff0000") == (255, 0, 0, 255)
    # Uma cor nova é resolvida para a mais próxima já em uso — não recusada,
    # senão a pincelada sumiria e o sprite ficaria com um buraco.
    assert palette.resolve("#fe0000") == (255, 0, 0, 255)
    assert len(palette.colors) == 2


def test_palette_manager_admits_while_there_is_room():
    palette = PaletteManager(["#ff0000"], max_colors=3)
    palette.resolve("#00ff00")
    palette.resolve("#0000ff")
    assert len(palette.colors) == 3
    # Cheia, a próxima é remapeada.
    palette.resolve("#000000")
    assert len(palette.colors) == 3


def test_erasing_does_not_spend_a_palette_slot():
    """Alpha 0 é borracha; tratá-lo como cor consumiria o orçamento."""
    palette = PaletteManager(["#ff0000"], max_colors=1)
    assert palette.resolve([0, 0, 0, 0]) == (0, 0, 0, 0)
    assert len(palette.colors) == 1


def test_the_executor_routes_colours_through_the_palette():
    """A guarda vale **durante** o desenho, não só na conferência do fim."""
    canvas = PixelCanvas(8, 8)
    executor = PixelToolExecutor(
        palette=PaletteManager(["#ff0000", "#00ff00"], max_colors=2)
    )

    executor.execute(
        canvas, ToolCall("fill_rect", {"x0": 0, "y0": 0, "x1": 7, "y1": 3, "color": "#ff0000"})
    )
    executor.execute(
        canvas, ToolCall("fill_rect", {"x0": 0, "y0": 4, "x1": 7, "y1": 7, "color": "#123456"})
    )

    assert canvas.stats().color_count == 2, "o executor deixou passar uma cor nova"


# ---------------------------------------------------------------------------
# Executor e log (§19)
# ---------------------------------------------------------------------------
def test_executor_records_every_call_with_the_pixels_it_changed():
    canvas = PixelCanvas(8, 8)
    executor = PixelToolExecutor()
    log = ToolCallLog()

    executor.execute_all(
        canvas,
        [
            ToolCall("fill_rect", {"x0": 1, "y0": 1, "x1": 2, "y1": 2, "color": "#ff0000"}),
            ToolCall("inspect_canvas", {}, note="conferindo"),
        ],
        log,
    )

    assert log.records[0].pixels_changed == 4
    assert log.records[1].snapshot is not None
    assert log.records[1].snapshot["opaque_pixels"] == 4
    assert log.summary()["by_tool"] == {"fill_rect": 1, "inspect_canvas": 1}


def test_a_bad_tool_call_becomes_a_logged_error_not_a_crash():
    canvas = PixelCanvas(8, 8)
    executor = PixelToolExecutor()
    log = ToolCallLog()

    executor.execute(canvas, ToolCall("ferramenta_inexistente", {}), log)
    executor.execute(canvas, ToolCall("draw_pixel", {"x": "abc", "y": 1, "color": "#fff"}), log)
    executor.execute(canvas, ToolCall("draw_pixel", {"x": 1, "y": 1, "color": "#ffffff"}), log)

    assert len(log.errors) == 2
    assert canvas.is_opaque(1, 1), "a chamada boa depois das ruins precisa valer"


def test_the_ellipse_tool_draws_a_wider_than_tall_shape():
    """A elipse do §16 resolve o que dois círculos aproximariam com degraus."""
    canvas = PixelCanvas(32, 32)
    PixelToolExecutor().execute(
        canvas, ToolCall("draw_ellipse", {"cx": 16, "cy": 16, "rx": 10, "ry": 4, "color": "#fff"})
    )
    bounds = canvas.bounds()
    largura = bounds[2] - bounds[0]
    altura = bounds[3] - bounds[1]
    assert largura > altura


# ---------------------------------------------------------------------------
# Planejador (§17)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("subject,expected", FASE_1)
def test_planner_recognises_the_first_delivery_subjects(subject: str, expected: str):
    assert PlanningAgent().choose_recipe(subject, "prop") == expected


def test_planner_matches_the_subject_before_the_asset_type():
    assert PlanningAgent().choose_recipe("uma arvore", "character") == "tree"


def test_plan_declares_canvas_palette_roles_and_regions():
    """O plano do §17: canvas, regiões com bounds e papéis de cor."""
    document = PlanningAgent().plan(_brief("tree")).document()

    assert document["canvas"] == [32, 32]
    assert document["recipe"] == "tree"
    assert document["palette_roles"]["outline"]
    nomes = {region["name"] for region in document["regions"]}
    assert {"tronco", "copa"} <= nomes
    assert all(len(region["bounds"]) == 4 for region in document["regions"])


# ---------------------------------------------------------------------------
# Revisor (§23 e §24)
# ---------------------------------------------------------------------------
def test_the_reviewer_describes_and_does_not_touch_the_canvas():
    """§24: o revisor gera instruções; quem corrige é o agente."""
    canvas = PixelCanvas(16, 16)
    PixelToolExecutor().execute(
        canvas, ToolCall("fill_rect", {"x0": 6, "y0": 6, "x1": 9, "y1": 9, "color": "#4a8c3f"})
    )
    PixelToolExecutor().execute(
        canvas, ToolCall("draw_pixel", {"x": 1, "y": 14, "color": "#4a8c3f"})
    )
    antes = canvas.to_bytes()

    plan = PlanningAgent().plan(_brief("tree", size=16))
    review = PixelReviewer().review(canvas, plan=plan, max_colors=8)

    assert canvas.to_bytes() == antes, "o revisor não pode alterar o canvas"
    codes = {issue.code for issue in review.issues}
    assert "PX-AGENT-ORPHAN" in codes
    assert "PX-AGENT-OUTLINE" in codes
    # As ações são vocabulário fechado: é o agente que as executa.
    assert "remove_orphans" in {
        action for issue in review.issues for action in issue.recommended_actions
    }


def test_the_reviewer_reports_an_empty_sprite_without_recommending_a_fix():
    """Não há correção honesta: inventar pixels entregaria o que ninguém pediu."""
    canvas = PixelCanvas(32, 32)
    canvas.set(0, 0, (255, 255, 255, 255))
    plan = PlanningAgent().plan(_brief("tree"))

    review = PixelReviewer().review(canvas, plan=plan, max_colors=16)
    vazio = next(issue for issue in review.issues if issue.code == "PX-AGENT-EMPTY")
    assert vazio.recommended_actions == ()


def test_a_tile_is_not_asked_for_an_outline():
    """Tile ocupa o canvas inteiro de propósito: sem margem, sem contorno."""
    canvas = PixelCanvas(16, 16)
    PixelToolExecutor().execute(
        canvas, ToolCall("fill_rect", {"x0": 0, "y0": 0, "x1": 15, "y1": 15, "color": "#7a6a55"})
    )
    plan = PlanningAgent().plan(_brief("grass block", size=16))

    review = PixelReviewer().review(canvas, plan=plan, max_colors=16)
    assert "PX-AGENT-OUTLINE" not in {issue.code for issue in review.issues}
    assert "PX-AGENT-BOUNDS" not in {issue.code for issue in review.issues}


# ---------------------------------------------------------------------------
# Sessão e modos de qualidade (§25)
# ---------------------------------------------------------------------------
def test_quality_modes_carry_the_iteration_budget_of_the_plan():
    assert ITERATIONS_BY_QUALITY[QualityMode.FAST] == 2
    assert ITERATIONS_BY_QUALITY[QualityMode.BALANCED] == 4
    assert ITERATIONS_BY_QUALITY[QualityMode.DETAILED] == 6


def test_an_explicit_iteration_limit_wins_over_the_quality_mode():
    from assetflow.generation.pixel_agent.session import AgentSession

    session = AgentSession.for_quality(QualityMode.DETAILED, max_iterations=1)
    assert session.max_iterations == 1


def test_the_review_loop_stops_when_there_is_nothing_left_to_fix():
    """Gastar seis iterações em um sprite limpo cobra tempo e não muda nada."""
    agent = AssetFlowPixelAgent()
    drawing = agent.draw(_brief("tree"), quality=QualityMode.DETAILED)

    assert drawing.session.iterations < ITERATIONS_BY_QUALITY[QualityMode.DETAILED]
    assert drawing.session.reviews[-1].actionable == []


def test_auto_review_off_skips_the_loop_entirely():
    agent = AssetFlowPixelAgent()
    drawing = agent.draw(_brief("tree"), auto_review=False)

    assert drawing.session.iterations == 0
    assert drawing.session.reviews == []


# ---------------------------------------------------------------------------
# O agente inteiro (§48 e §50)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("subject,recipe", FASE_1)
def test_first_delivery_subjects_produce_a_usable_sprite(subject: str, recipe: str):
    drawing = AssetFlowPixelAgent().draw(_brief(subject))
    image = _image(drawing.data)

    assert image.size == (32, 32), "o agente desenha na grade, não em alta resolução"
    assert drawing.plan.recipe == recipe

    stats = _stats(image)
    assert stats["opaque"] > 40, "o sprite não pode sair praticamente vazio"
    assert stats["colors"] <= 16, "a paleta pedida tem de ser respeitada"


@pytest.mark.parametrize("size", [16, 32])
def test_the_sprite_comes_out_at_the_requested_grid(size: int):
    """§20: canvas pixel-native — 32×32 pedido é 32×32 entregue."""
    drawing = AssetFlowPixelAgent().draw(_brief("tree", size=size))
    assert _image(drawing.data).size == (size, size)


def test_the_same_seed_produces_the_same_sprite():
    agent = AssetFlowPixelAgent()
    first = agent.draw(_brief("tree", seed=7))
    second = agent.draw(_brief("tree", seed=7))
    third = agent.draw(_brief("tree", seed=8))

    assert first.data == second.data
    assert first.data != third.data


def test_the_agent_applies_the_outline_the_reviewer_asked_for():
    drawing = AssetFlowPixelAgent().draw(_brief("wooden chest"))
    assert "PX-AGENT-OUTLINE" in drawing.session.repairs
    assert drawing.session.repairs["PX-AGENT-OUTLINE"] > 0


def test_the_execution_log_reconstructs_the_drawing():
    """§19: o histórico reconstrói o resultado, e não só o rascunho.

    Reexecutar o log em um canvas vazio tem de reproduzir o mesmo sprite. Se
    alguma etapa — inclusive o reparo da revisão — mexesse no canvas por fora
    das ferramentas, este teste falharia.
    """
    drawing = AssetFlowPixelAgent().draw(_brief("tree"))

    canvas = PixelCanvas(32, 32)
    executor = PixelToolExecutor()
    for entry in drawing.session.log.document():
        executor.execute(canvas, ToolCall(entry["tool"], entry["params"]))

    replay = Image.frombytes("RGBA", (32, 32), canvas.to_bytes())
    assert replay.tobytes() == _image(drawing.data).tobytes()


def test_a_solid_background_is_filled_from_the_palette():
    brief = _brief("tree")
    brief = DrawingBrief(
        subject=brief.subject,
        asset_type=brief.asset_type,
        width=brief.width,
        height=brief.height,
        max_colors=brief.max_colors,
        transparent=False,
        seed=brief.seed,
    )
    image = _image(AssetFlowPixelAgent().draw(brief).data)
    assert all(image.getpixel((x, y))[3] == 255 for x in range(32) for y in range(32))


def test_the_agent_documents_what_it_did():
    """Os metadados do §28: plano, sessão e histórico de tool calls."""
    document = AssetFlowPixelAgent().draw(_brief("red potion")).document()

    assert document["plan"]["recipe"] == "potion"
    assert document["session"]["quality_mode"]
    assert document["session"]["tool_calls"] > 0
    assert len(document["tool_calls"]) == document["session"]["tool_calls"]


def test_the_agent_has_an_identity():
    agent = AssetFlowPixelAgent()
    assert agent.id == AGENT_ID == "assetflow_pixel_agent"
    assert agent.version


# ---------------------------------------------------------------------------
# Vocabulário: o que o agente sabe, e o que ele faz quando não sabe
# ---------------------------------------------------------------------------
def test_the_agent_draws_a_house():
    """Pedir uma casa tinha de devolver uma casa.

    O caso que originou esta bateria: "house" caía na receita genérica e saía
    uma bolha salpicada — e `house_64` está na suíte de benchmark do projeto
    desde o começo, ou seja, o próprio comparativo media uma bolha.
    """
    assert PlanningAgent().choose_recipe("house", "prop") == "house"
    assert PlanningAgent().choose_recipe("small medieval house", "prop") == "house"
    assert PlanningAgent().choose_recipe("uma casa de pedra", "prop") == "house"

    drawing = AssetFlowPixelAgent().draw(_brief("small medieval house", size=32))
    image = _image(drawing.data)

    assert drawing.plan.recipe == "house"
    # Porta e janelas são o que faz o olho ler "casa" em vez de "caixa".
    nomes = set(drawing.plan.regions)
    assert {"parede", "porta", "janela_esquerda", "janela_direita"} <= nomes
    assert _stats(image)["opaque"] > 200


def test_the_planner_says_when_it_does_not_know_the_subject():
    """A pergunta que faltava, e cuja falta produzia silêncio."""
    planner = PlanningAgent()

    assert planner.recognizes("uma arvore") is True
    assert planner.recognizes("small medieval house") is True
    assert planner.recognizes("objeto misterioso") is False
    # Um tipo conhecido conta como reconhecimento, mesmo sem palavra no sujeito.
    assert planner.recognizes("xyz", "tileset") is True


def test_the_generic_fallback_reads_as_a_solid_object():
    """Sem ruído: em um objeto que ninguém reconhece, textura parece defeito.

    A versão anterior salpicava a forma, e o resultado não sugeria material
    nenhum — só dava a impressão de que a geração tinha falhado.
    """
    drawing = AssetFlowPixelAgent().draw(_brief("objeto misterioso"))
    image = _image(drawing.data)

    assert drawing.plan.recipe == "generic"
    stats = _stats(image)
    assert stats["opaque"] > 150, "o volume precisa ler como objeto sólido"
    # Poucas cores, em áreas grandes: é o que separa volume de estática.
    assert stats["colors"] <= 5
    assert drawing.session.reviews[-1].actionable == []
