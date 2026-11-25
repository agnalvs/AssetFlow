"""A gaveta `gpt-image-v1` — a primeira remota (pesquisa PixelLab).

Ela existe para provar uma tese: **um motor não precisa saber fazer Pixel Art
para o AssetFlow entregar Pixel Art.** O provedor exige no mínimo 655.360
pixels por imagem — 640 vezes mais que um sprite 32×32 —, então ele nunca
desenha na grade. Ele entrega composição e leitura do pedido; a grade é do
Pixel Exact, depois dele.

Nenhum teste aqui toca a rede. O cliente HTTP é substituído por um dublê: o
que se está exercitando é a **tradução** — grid lógico para tamanho válido,
spec para prompt, capacidade ausente para aviso —, e não a API da OpenAI.
"""

from __future__ import annotations

import base64
import struct
import zlib
from dataclasses import dataclass

import pytest

from assetflow.bootstrap import AppContainer, build_container
from assetflow.generation.engines.gpt_image.client import ImageRequest, _decode
from assetflow.generation.engines.gpt_image.config import GPTImageConfig
from assetflow.generation.engines.gpt_image.prompting import budget_for, compile_prompt
from assetflow.generation.engines.gpt_image.sizing import (
    MAX_TOTAL_PIXELS,
    MIN_TOTAL_PIXELS,
    RenderSize,
    SizeNotRepresentable,
    render_size_for,
)
from assetflow.generation.kernel.exceptions import EngineExecutionError
from assetflow.generation.schemas import AssetGenerationRequest
from assetflow.settings import Settings
from tests.conftest import run

ENGINE_ID = "gpt-image-v1"


def _png(width: int, height: int) -> bytes:
    """Um PNG opaco válido, do tamanho pedido."""
    linha = bytes([0]) + bytes([180, 90, 40, 255] * width)
    bruto = linha * height
    saida = bytes([137, 80, 78, 71, 13, 10, 26, 10])
    for tag, corpo in (
        (b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
        (b"IDAT", zlib.compress(bruto)),
        (b"IEND", b""),
    ):
        saida += struct.pack(">I", len(corpo)) + tag + corpo
        saida += struct.pack(">I", zlib.crc32(tag + corpo) & 0xFFFFFFFF)
    return saida


# ---------------------------------------------------------------------------
# A tradução de tamanho — o núcleo da gaveta
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "logical", [(16, 16), (24, 32), (32, 32), (48, 48), (64, 64), (96, 96), (128, 128)]
)
def test_the_render_size_is_an_exact_integer_multiple_of_the_grid(logical):
    """A redução que vem depois é **por blocos**, e blocos precisam fechar.

    Com 900×900 para um grid de 32, cada pixel lógico cobriria 28,125 pixels de
    origem: as bordas de bloco cairiam no meio de um pixel, e a silhueta
    chegaria à grade já contaminada. Um render 3% maior custa quase nada; uma
    silhueta borrada custa o asset.
    """
    render = render_size_for(logical, (1024, 1024))

    assert render.scale is not None
    assert render.width == logical[0] * render.scale
    assert render.height == logical[1] * render.scale


@pytest.mark.parametrize(
    "logical", [(16, 16), (24, 32), (32, 32), (48, 48), (64, 64), (96, 96), (128, 128)]
)
def test_every_render_size_satisfies_the_provider_rules(logical):
    """As quatro regras do provedor, verificadas na documentação dele."""
    render = render_size_for(logical, (1024, 1024))

    assert render.width % 16 == 0 and render.height % 16 == 0
    assert MIN_TOTAL_PIXELS <= render.total_pixels <= MAX_TOTAL_PIXELS
    assert max(render.width, render.height) <= 3840
    assert max(render.width, render.height) / min(render.width, render.height) <= 3.0


def test_the_smallest_valid_size_is_chosen():
    """Cada imagem é cobrada: gerar maior do que o necessário é dinheiro.

    32×32 poderia virar 1024×1024 (escala 32) e funcionaria. 832×832 é 34%
    menos pixels e a mesma escala inteira.
    """
    render = render_size_for((32, 32), (1024, 1024))

    assert render == RenderSize(832, 832, scale=26)
    # E é de fato o menor: uma escala a menos não alcança o mínimo.
    assert (32 * 25) ** 2 < MIN_TOTAL_PIXELS


def test_an_extreme_aspect_ratio_is_refused_instead_of_deformed():
    """Uma barra de vida 128×8 é 16:1, e o provedor não passa de 3:1.

    Gerar em 3:1 e esticar depois entregaria um asset deformado sem avisar
    ninguém — que é exatamente o tipo de correção silenciosa que o projeto
    proíbe. A recusa diz o que fazer.
    """
    with pytest.raises(SizeNotRepresentable) as erro:
        render_size_for((128, 8), (1024, 1024))

    assert "3:1" in str(erro.value)


def test_without_a_logical_grid_the_size_still_lands_in_range():
    """Arte 2D convencional não tem grade, mas o provedor tem mínimo igual."""
    render = render_size_for(None, (1024, 768))

    assert render.scale is None
    assert MIN_TOTAL_PIXELS <= render.total_pixels <= MAX_TOTAL_PIXELS
    assert render.width % 16 == 0 and render.height % 16 == 0


# ---------------------------------------------------------------------------
# O compilador de prompt
# ---------------------------------------------------------------------------
def _compile(**overrides):
    base = dict(
        positive="uma casa de pedra",
        negative=None,
        subject="casa de pedra",
        asset_type="prop",
        is_pixel=True,
        logical=(32, 32),
        max_colors=8,
        transparent=True,
        view=None,
        seed_requested=False,
    )
    base.update(overrides)
    return compile_prompt(**base)


def test_the_prompt_asks_for_what_survives_downscaling():
    """O que decide a redução não é o realismo — é a estrutura.

    Uma ilustração com degradês suaves vira uma mancha em 32×32. O prompt
    inteiro existe para pedir massas chapadas e bordas duras.
    """
    texto = _compile().text.lower()

    assert "flat" in texto
    assert "no gradients" in texto
    assert "anti-aliasing" in texto
    assert "32×32" in texto, "o grid alvo precisa chegar ao modelo"
    assert "8 flat colours" in texto or "8 flat colors" in texto
    assert "transparent" in texto
    # E o erro que a redução não perdoa: várias poses no mesmo quadro.
    assert "sprite sheet" in texto


def test_the_detail_budget_shrinks_with_the_grid():
    """"Cicatriz no olho" não cabe em 256 pixels.

    O spec continua completo; quem reduz a densidade é só o compilador — e ele
    o faz pedindo silhueta onde não cabe detalhe.
    """
    assert budget_for((16, 16)).name == "silhouette"
    assert budget_for((32, 32)).name == "compact"
    assert budget_for((64, 64)).name == "standard"
    assert budget_for((128, 128)).name == "detailed"
    assert budget_for(None).name == "detailed"

    pequeno = _compile(logical=(16, 16)).text.lower()
    assert "silhouette" in pequeno
    assert "omit facial features" in pequeno


def test_a_missing_capability_becomes_a_warning_not_a_silence():
    """O provedor não tem seed nem negative prompt. Os dois viram aviso.

    Uma capacidade que falta em silêncio é pior que uma capacidade que falta:
    quem pediu uma seed acharia que o resultado é reprodutível.
    """
    compilado = _compile(negative="texto, moldura", seed_requested=True)

    assert any("seed" in aviso for aviso in compilado.warnings)
    assert any("negative prompt" in aviso for aviso in compilado.warnings)
    # O negative não é descartado: vira "Avoid:" no texto.
    assert "Avoid: texto, moldura." in compilado.text


def test_conventional_2d_art_does_not_get_pixel_art_instructions():
    """Encher o prompt de regras de pixel art estragaria arte 2D comum."""
    texto = _compile(is_pixel=False, logical=None).text.lower()

    assert "no gradients" not in texto
    assert "pixel grid" not in texto


def test_the_camera_view_becomes_language_the_model_understands():
    """O spec guarda `low_top_down`; o modelo entende graus."""
    texto = _compile(view="low_top_down").text

    assert "20 degrees" in texto


# ---------------------------------------------------------------------------
# Configuração e credencial
# ---------------------------------------------------------------------------
def test_the_api_key_never_comes_from_configuration(monkeypatch: pytest.MonkeyPatch):
    """`engines.yaml` é versionado: uma chave ali é um incidente."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = GPTImageConfig()

    assert config.api_key is None
    assert config.configured is False
    assert "OPENAI_API_KEY" in config.unavailable_reason()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    assert GPTImageConfig().configured is True
    assert GPTImageConfig().unavailable_reason() is None


def test_quality_is_translated_not_leaked():
    """`medium` é vocabulário do provedor e não pode vazar para o núcleo."""
    config = GPTImageConfig()

    assert config.quality_for("draft") == "low"
    assert config.quality_for("standard") == "medium"
    assert config.quality_for("high") == "high"
    assert config.quality_for("desconhecido") == "auto"


def test_transparent_background_is_only_sent_when_decided():
    """"auto" explícito é ruído, e alguns gateways compatíveis o recusam."""
    assert "background" not in ImageRequest("p", "832x832").payload("m")
    assert (
        ImageRequest("p", "832x832", background="transparent").payload("m")["background"]
        == "transparent"
    )


# ---------------------------------------------------------------------------
# A resposta do provedor
# ---------------------------------------------------------------------------
def test_a_response_without_images_fails_instead_of_returning_nothing():
    """Um job "concluído" sem asset é o pior resultado possível."""
    with pytest.raises(EngineExecutionError):
        _decode({"data": []})
    with pytest.raises(EngineExecutionError):
        _decode({"data": [{"revised_prompt": "..."}]})


def test_images_are_decoded_from_base64():
    dados = _png(16, 16)
    payload = {"data": [{"b64_json": base64.b64encode(dados).decode("ascii")}]}

    assert _decode(payload) == [dados]


# ---------------------------------------------------------------------------
# A gaveta inteira, dentro do pipeline
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class GPTHarness:
    """O container com a gaveta ligada, e o que o dublê recebeu."""

    container: AppContainer
    calls: list[ImageRequest]


@pytest.fixture
def gpt(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> GPTHarness:
    """Container com a gaveta ligada e o HTTP dublado.

    O dublê entra em `GPTImageClient.generate`, e não em `urllib`: o que
    interessa provar é o encaixe da gaveta no pipeline, não a serialização
    HTTP — que já tem teste próprio acima.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    monkeypatch.setenv("ASSETFLOW_ENGINES_ENABLED", ENGINE_ID)
    settings.worker.embedded = False

    from assetflow.generation.engines.gpt_image import client as modulo

    chamadas: list[ImageRequest] = []

    async def falso_generate(self, request: ImageRequest) -> list[bytes]:
        chamadas.append(request)
        largura, altura = (int(parte) for parte in request.size.split("x"))
        return [_png(largura, altura) for _ in range(request.n)]

    monkeypatch.setattr(modulo.GPTImageClient, "generate", falso_generate)

    return GPTHarness(build_container(settings), chamadas)


def test_a_1024px_proposal_becomes_an_exact_32x32_sprite(gpt: GPTHarness):
    """A tese da pesquisa, em forma de teste.

    O motor nunca vê 32×32 — ele gera 832×832. Quem entrega o sprite exato é o
    pipeline que já existia, sem uma linha de código específica de motor.
    """
    job = run(gpt.container.service.submit(AssetGenerationRequest(
        project_id="p",
        profile="pixel_character_64",
        prompt="uma casa de pedra 32x32 com 8 cores",
        engine={"mode": "manual", "engine_id": ENGINE_ID, "allow_fallback": False},
    )))
    run(gpt.container.worker.run_once())
    job = run(gpt.container.jobs.get(job.id))

    assert job.status.value == "completed", job.error
    assert job.engine.id == ENGINE_ID

    variante = job.asset.variants[0]
    assert (variante.logical_width, variante.logical_height) == (32, 32)
    assert variante.pixel_exact is True
    assert variante.color_count <= 8

    # O motor gerou grande; o AssetFlow entregou pequeno.
    chamada = gpt.calls[0]
    assert chamada.size == "832x832"
    assert chamada.background == "transparent"

    # E o Optimizer rodou nele, como roda em qualquer motor.
    assert (variante.metadata.get("pixel_metrics") or {}).get("optimizer_status")


def test_the_engine_warnings_reach_the_job(gpt: GPTHarness):
    """Sem seed, o job precisa dizer que não é reprodutível."""
    job = run(gpt.container.service.submit(AssetGenerationRequest(
        project_id="p",
        profile="pixel_character_64",
        prompt="uma casa 32x32",
        seed=42,
        engine={"mode": "manual", "engine_id": ENGINE_ID, "allow_fallback": False},
    )))
    run(gpt.container.worker.run_once())
    job = run(gpt.container.jobs.get(job.id))

    assert job.status.value == "completed", job.error
    assert any("seed" in aviso for aviso in job.warnings), job.warnings


def test_variations_become_n_in_a_single_call(gpt: GPTHarness):
    """`n` é o que torna candidate pool barato: uma chamada, várias imagens."""
    job = run(gpt.container.service.submit(AssetGenerationRequest(
        project_id="p",
        profile="pixel_character_64",
        prompt="uma casa 32x32",
        output={"variations": 3},
        engine={"mode": "manual", "engine_id": ENGINE_ID, "allow_fallback": False},
    )))
    run(gpt.container.worker.run_once())
    job = run(gpt.container.jobs.get(job.id))

    assert job.status.value == "completed", job.error
    assert len(gpt.calls) == 1
    assert gpt.calls[0].n == 3
    assert len(job.asset.variants) == 3


def test_the_effective_prompt_is_recorded(gpt: GPTHarness):
    """"Por que saiu isso?" não se responde com o prompt do usuário.

    O texto que gerou o asset é o compilado, e é ele que o histórico guarda.
    """
    job = run(gpt.container.service.submit(AssetGenerationRequest(
        project_id="p",
        profile="pixel_character_64",
        prompt="uma casa 32x32",
        engine={"mode": "manual", "engine_id": ENGINE_ID, "allow_fallback": False},
    )))
    run(gpt.container.worker.run_once())
    job = run(gpt.container.jobs.get(job.id))

    registro = run(gpt.container.records.list(limit=1))[0]
    assert "no gradients" in registro.positive_prompt.lower()
    assert registro.positive_prompt != "uma casa 32x32"


# ---------------------------------------------------------------------------
# Repetir custa dinheiro
# ---------------------------------------------------------------------------
def test_a_definitive_refusal_is_not_retried():
    """`400` devolve o mesmo erro na segunda tentativa — e cobra de novo.

    Este teste nasceu do primeiro erro real da gaveta: um *"Billing hard limit
    has been reached"* foi repetido pelo retry do worker. Sem crédito, insistir
    nunca ia funcionar; com moderação recusando o prompt, também não. O que o
    retry existe para cobrir é rede instável e sobrecarga do provedor.
    """
    from assetflow.generation.engines.gpt_image.client import _is_retryable

    # Definitivos: insistir devolve o mesmo, e cada tentativa é cobrável.
    assert _is_retryable(400) is False   # sem crédito, prompt recusado, tamanho inválido
    assert _is_retryable(401) is False   # credencial errada
    assert _is_retryable(403) is False
    assert _is_retryable(404) is False

    # Transitórios: insistir resolve.
    assert _is_retryable(429) is True    # limite de taxa
    assert _is_retryable(500) is True
    assert _is_retryable(503) is True


def test_the_provider_message_survives_the_translation():
    """"Erro na geração" apagaria o diagnóstico inteiro.

    A mensagem do provedor costuma **ser** a informação: sem crédito, prompt
    recusado, tamanho inválido. Quem lê o job precisa dela.
    """
    import io
    import urllib.error

    from assetflow.generation.engines.gpt_image.client import _http_message

    corpo = io.BytesIO(
        b'{"error": {"message": "Billing hard limit has been reached."}}'
    )
    erro = urllib.error.HTTPError(
        "http://x", 400, "Bad Request", {}, corpo  # type: ignore[arg-type]
    )

    mensagem = _http_message(erro)
    assert "Billing hard limit" in mensagem
    assert "400" in mensagem
