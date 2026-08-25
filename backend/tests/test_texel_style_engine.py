"""O engine estilo Texel: canvas, ferramentas, plano e revisão (plano de motores §9, §15).

A entrega mínima da Fase 5 é nomeada no §15: prop simples, árvore, pedra,
poção, baú e bloco. Este arquivo cobra exatamente isso, e cobra também as
propriedades que separam um agente de desenho de um gerador procedural
qualquer — determinismo, silhueta com contorno, paleta dentro do orçamento e
um histórico de tool calls que reconstrói o desenho.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from assetflow.generation.engines.texel_style.canvas import PixelCanvas
from assetflow.generation.engines.texel_style.engine import TexelStyleEngine
from assetflow.generation.engines.texel_style.planner import (
    DrawingBrief,
    PlanningAgent,
)
from assetflow.generation.engines.texel_style.review_loop import ReviewLoop
from assetflow.generation.engines.texel_style.tool_executor import (
    ToolCall,
    ToolCallLog,
    ToolExecutor,
)
from assetflow.generation.kernel.contracts import EngineExecutionContext
from assetflow.generation.schemas import (
    AssetSpec,
    EngineRuntimeConfig,
    GenerationParams,
    ImageGenerationRequest,
    OutputSpec,
    PromptSpec,
)
from tests.conftest import run

#: A entrega mínima da Fase 5, nomeada no plano de motores §15.
FASE_5 = [
    ("uma árvore com folhas", "tree"),
    ("stone rock", "rock"),
    ("red potion", "potion"),
    ("wooden chest", "chest"),
    ("grass tile block", "tile"),
]


def _engine() -> TexelStyleEngine:
    engine = TexelStyleEngine()
    run(engine.initialize(EngineRuntimeConfig(engine_id="texel-style-v1")))
    return engine


def _request(subject: str, *, size: int = 32, colors: int | None = 16, seed: int = 99):
    return ImageGenerationRequest(
        capability="text_to_image.pixel",
        asset=AssetSpec(type="prop", mode="pixel"),
        prompt=PromptSpec(positive=subject),
        output=OutputSpec(
            width=512,
            height=512,
            logical_width=size,
            logical_height=size,
            max_colors=colors,
            transparent=True,
        ),
        generation=GenerationParams(seed=seed),
    )


def _image(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGBA")


# ---------------------------------------------------------------------------
# Canvas
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

    orphans = canvas.orphans()
    assert (0, 0) in orphans
    assert (4, 4) not in orphans
    # A borda externa do par tem de existir para o contorno ter onde ir.
    assert (3, 4) in canvas.edge_pixels()


def test_canvas_refuses_a_degenerate_size():
    with pytest.raises(ValueError):
        PixelCanvas(0, 10)


# ---------------------------------------------------------------------------
# Ferramentas e executor
# ---------------------------------------------------------------------------
def test_executor_records_every_call_with_the_pixels_it_changed():
    canvas = PixelCanvas(8, 8)
    executor = ToolExecutor()
    log = ToolCallLog()

    executor.execute_all(
        canvas,
        [
            ToolCall("fill_rect", {"x0": 1, "y0": 1, "x1": 2, "y1": 2, "color": "#ff0000"}),
            ToolCall("view_canvas", {}, note="conferindo"),
        ],
        log,
    )

    assert log.records[0].pixels_changed == 4
    # A inspeção guarda o retrato do canvas junto — é o `view_canvas` do §9.4.
    assert log.records[1].snapshot is not None
    assert log.records[1].snapshot["opaque_pixels"] == 4
    assert log.summary()["by_tool"] == {"fill_rect": 1, "view_canvas": 1}


def test_a_bad_tool_call_becomes_a_logged_error_not_a_crash():
    """Um plano com uma coordenada ruim produz um defeito e um log — não um
    job perdido inteiro."""
    canvas = PixelCanvas(8, 8)
    executor = ToolExecutor()
    log = ToolCallLog()

    executor.execute(canvas, ToolCall("ferramenta_inexistente", {}), log)
    executor.execute(canvas, ToolCall("draw_pixel", {"x": "abc", "y": 1, "color": "#fff"}), log)
    executor.execute(canvas, ToolCall("draw_pixel", {"x": 1, "y": 1, "color": "#ffffff"}), log)

    assert len(log.errors) == 2
    assert canvas.is_opaque(1, 1), "a chamada boa depois das ruins precisa valer"


def test_drawing_outside_the_canvas_is_ignored_not_an_error():
    canvas = PixelCanvas(4, 4)
    executor = ToolExecutor()
    record = executor.execute(
        canvas, ToolCall("draw_circle", {"cx": 0, "cy": 0, "radius": 9, "color": "#fff"})
    )
    assert record.error is None
    assert record.pixels_changed == 16  # só o que coube


# ---------------------------------------------------------------------------
# Planejador
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("subject,expected", FASE_5)
def test_planner_recognises_the_phase_5_subjects(subject: str, expected: str):
    """O sujeito escolhe a receita — e acentuação não pode atrapalhar."""
    assert PlanningAgent().choose_recipe(subject, "prop") == expected


def test_planner_matches_the_subject_before_the_asset_type():
    """Uma árvore continua árvore mesmo classificada como personagem.

    É a mesma prioridade da taxonomia do AssetFlow, e pelo mesmo motivo: o
    tipo descreve a gaveta de produto, o sujeito descreve o desenho.
    """
    assert PlanningAgent().choose_recipe("uma arvore", "character") == "tree"


def test_planner_falls_back_to_a_generic_recipe():
    assert PlanningAgent().choose_recipe("objeto misterioso", "prop") == "generic"


def test_plan_declares_canvas_palette_and_regions():
    """O plano do §9.2 tem de ser inspecionável antes de virar pixel."""
    plan = PlanningAgent().plan(
        DrawingBrief(subject="tree", asset_type="prop", width=32, height=32, max_colors=16)
    )
    document = plan.document()

    assert document["canvas"] == [32, 32]
    assert document["recipe"] == "tree"
    assert document["palette"], "o plano precisa declarar as cores"
    nomes = {region["name"] for region in document["regions"]}
    assert {"tronco", "copa"} <= nomes


def test_palette_shrinks_to_the_budget_without_losing_the_outline():
    """Com orçamento apertado, o contorno é a última cor a sair.

    Um sprite sem contorno perde a silhueta, que é a única coisa legível em
    16×16; um sprite sem segunda tonalidade fica só mais chapado.
    """
    plan = PlanningAgent().plan(
        DrawingBrief(subject="tree", asset_type="prop", width=16, height=16, max_colors=3)
    )
    assert len(plan.palette.colors()) <= 3
    assert plan.palette.outline in plan.palette.colors()


# ---------------------------------------------------------------------------
# Review loop
# ---------------------------------------------------------------------------
def test_review_loop_draws_the_outline_and_removes_orphans():
    canvas = PixelCanvas(16, 16)
    executor = ToolExecutor()
    executor.execute(
        canvas, ToolCall("fill_rect", {"x0": 6, "y0": 6, "x1": 9, "y1": 9, "color": "#4a8c3f"})
    )
    executor.execute(canvas, ToolCall("draw_pixel", {"x": 1, "y": 14, "color": "#4a8c3f"}))

    log = ToolCallLog()
    report = ReviewLoop(executor).run(
        canvas, outline_color="#1e2a1a", max_colors=8, log=log
    )

    codes = {finding.code for finding in report.findings}
    assert "TX-OUTLINE" in codes
    assert "TX-ORPHAN" in codes
    assert not canvas.is_opaque(1, 14), "o pixel solto tinha de sair"
    assert canvas.is_opaque(5, 6), "o contorno tinha de entrar"
    # Toda correção passou pelas mesmas ferramentas do desenho (§9.5).
    assert all(record.call.tool in executor.tool_names for record in log.records)


def test_review_loop_brings_the_palette_into_the_budget():
    canvas = PixelCanvas(8, 8)
    executor = ToolExecutor()
    for index, color in enumerate(["#ff0000", "#00ff00", "#0000ff", "#ffff00"]):
        executor.execute(
            canvas, ToolCall("fill_rect", {"x0": 0, "y0": index, "x1": 7, "y1": index, "color": color})
        )

    report = ReviewLoop(executor).run(
        canvas, outline_color="#000000", max_colors=2, log=ToolCallLog()
    )

    assert canvas.stats().color_count <= 2
    assert any(finding.code == "TX-PALETTE" for finding in report.findings)


def test_review_loop_reports_an_empty_sprite_instead_of_inventing_pixels():
    canvas = PixelCanvas(32, 32)
    executor = ToolExecutor()
    executor.execute(canvas, ToolCall("draw_pixel", {"x": 0, "y": 0, "color": "#fff"}))

    report = ReviewLoop(executor).run(
        canvas, outline_color="#000", max_colors=None, log=ToolCallLog()
    )
    assert any(finding.code == "TX-EMPTY" for finding in report.findings)


# ---------------------------------------------------------------------------
# O engine inteiro (entrega mínima da Fase 5 — plano de motores §15)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("subject,recipe", FASE_5)
def test_phase_5_subjects_produce_a_usable_sprite(subject: str, recipe: str):
    engine = _engine()
    result = run(engine.generate(_request(subject), EngineExecutionContext(job_id="j")))
    artifact = result.artifacts[0]
    image = _image(artifact.data)

    assert image.size == (32, 32), "o agente desenha no grid, não em alta resolução"
    assert artifact.metadata["recipe"] == recipe

    canvas_stats = _stats(image)
    assert canvas_stats["opaque"] > 40, "o sprite não pode sair praticamente vazio"
    assert canvas_stats["colors"] <= 16, "a paleta pedida tem de ser respeitada"


def test_the_sprite_comes_out_at_the_logical_size_untouched():
    """A entrega no grid é a razão de ser desta gaveta (plano de motores §9.2).

    Devolver 512×512 para o pós-processamento reduzir jogaria fora justamente
    o controle pixel a pixel que o motor acabou de exercer.
    """
    engine = _engine()
    for size in (16, 32, 64):
        result = run(
            engine.generate(_request("tree", size=size), EngineExecutionContext(job_id="j"))
        )
        assert _image(result.artifacts[0].data).size == (size, size)


def test_the_same_seed_produces_the_same_sprite():
    """Determinismo — sem ele o benchmark do §19 não compara nada."""
    engine = _engine()
    ctx = EngineExecutionContext(job_id="j")
    first = run(engine.generate(_request("tree", seed=7), ctx))
    second = run(engine.generate(_request("tree", seed=7), ctx))
    third = run(engine.generate(_request("tree", seed=8), ctx))

    assert first.artifacts[0].data == second.artifacts[0].data
    # Seeds diferentes mudam só a textura semeada, então a imagem muda pouco —
    # mas tem de mudar, senão a seed não está sendo usada.
    assert first.artifacts[0].data != third.artifacts[0].data


def test_the_sprite_has_an_outline_around_the_silhouette():
    engine = _engine()
    result = run(engine.generate(_request("wooden chest"), EngineExecutionContext(job_id="j")))
    image = _image(result.artifacts[0].data)

    # A cor mais escura precisa aparecer encostando no vazio: é o contorno.
    pixels = {(x, y): image.getpixel((x, y)) for x in range(32) for y in range(32)}
    escuras = [
        position
        for position, color in pixels.items()
        if color[3] > 0 and sum(color[:3]) < 160
    ]
    assert escuras, "nenhum pixel escuro: o contorno não foi aplicado"


def test_the_execution_log_reconstructs_the_drawing():
    """O histórico de tool calls é a promessa do §9.5.

    Reexecutar o log em um canvas vazio tem de reproduzir o mesmo sprite. Se
    alguma etapa mexesse no canvas por fora das ferramentas, este teste
    falharia — e é exatamente por isso que ele existe.
    """
    engine = _engine()
    result = run(engine.generate(_request("tree"), EngineExecutionContext(job_id="j")))
    log = result.engine_metadata["tool_calls"][0]

    canvas = PixelCanvas(32, 32)
    executor = ToolExecutor()
    for entry in log:
        executor.execute(canvas, ToolCall(entry["tool"], entry["params"]))

    replay = Image.frombytes("RGBA", (32, 32), canvas.to_bytes())
    assert replay.tobytes() == _image(result.artifacts[0].data).tobytes()


def test_variations_differ_from_each_other():
    engine = _engine()
    request = _request("rock").model_copy(
        update={"output": _request("rock").output.model_copy(update={"variations": 3})}
    )
    result = run(engine.generate(request, EngineExecutionContext(job_id="j")))

    assert len(result.artifacts) == 3
    assert len({artifact.data for artifact in result.artifacts}) == 3


def test_the_engine_reports_its_own_identity_for_the_history():
    """Sem modelo baixado, o campo `model_id` diz o que de fato gerou (§18)."""
    engine = _engine()
    ref = engine.engine_ref()

    assert ref.id == "texel-style-v1"
    assert ref.adapter_version
    assert ref.model_id and ref.model_id.startswith("agent://")


def test_a_solid_background_is_filled_from_the_palette():
    engine = _engine()
    request = _request("tree")
    request = request.model_copy(
        update={"output": request.output.model_copy(update={"transparent": False})}
    )
    result = run(engine.generate(request, EngineExecutionContext(job_id="j")))
    image = _image(result.artifacts[0].data)

    assert all(image.getpixel((x, y))[3] == 255 for x in range(32) for y in range(32))


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
