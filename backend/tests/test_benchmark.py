"""O benchmark comparativo entre motores (plano de motores §19 a §21).

O que precisa estar certo aqui, além de "roda sem quebrar":

* o benchmark passa pelo **caminho normal** do sistema, com pós-processamento
  e validação — senão ele mede o motor, e não o asset entregue (§21);
* fallback **não** conta como sucesso do motor pedido, senão o relatório
  credita a um motor o trabalho de outro;
* os dois eixos ficam separados: o técnico é medido, o visual é humano e
  nasce vazio (§21).
"""

from __future__ import annotations

from assetflow.bootstrap import AppContainer
from assetflow.generation.benchmark import (
    BenchmarkCase,
    BenchmarkRunner,
    BenchmarkSuite,
    CaseOutcome,
    EngineReport,
    TechnicalMetrics,
)
from assetflow.settings import load_settings
from tests.conftest import BACKEND_ROOT, run

_CASES = (
    BenchmarkCase(
        id="tree_32", prompt="tree", asset_type="prop", logical_size=32, max_colors=16
    ),
    BenchmarkCase(
        id="potion_16",
        prompt="red potion",
        asset_type="prop",
        logical_size=16,
        max_colors=8,
    ),
)


def test_the_shipped_suite_matches_the_plan():
    """Os casos do §19 estão no YAML entregue, com os nomes do plano."""
    settings = load_settings(base_dir=BACKEND_ROOT)
    suite = BenchmarkSuite.from_config(settings.benchmark_config)
    ids = {case.id for case in suite.cases}

    assert {"tree_32", "tree_64", "red_potion_16", "wooden_chest_32", "stone_sword_32"} <= ids
    assert {"knight_side_64", "mage_front_64", "slime_32", "house_64"} <= ids
    # Seed fixa por caso: sem ela duas execuções do mesmo caso já divergem.
    assert all(case.seed for case in suite.cases)


def test_runner_produces_one_block_per_engine(container: AppContainer):
    container.registry.enable("texel-style-v1")
    runner = BenchmarkRunner(
        container.service, container.worker, suite=BenchmarkSuite(cases=_CASES)
    )

    report = run(runner.run(engines=["texel-style-v1", "mock-image-v1"]))

    assert [block.engine_id for block in report.engines] == [
        "texel-style-v1",
        "mock-image-v1",
    ]
    for block in report.engines:
        assert block.total == 2
        assert block.succeeded == 2, [outcome.error for outcome in block.outcomes]


def test_the_measured_asset_went_through_postprocessing(container: AppContainer):
    """O que o benchmark mede é o asset final, não a saída crua do motor.

    Se o caminho medido pulasse o Pixel Exact, um motor que entrega 512×512
    borrado apareceria com as mesmas métricas de um que entrega 32×32 exato —
    e o §21 seria letra morta.
    """
    container.registry.enable("texel-style-v1")
    runner = BenchmarkRunner(
        container.service, container.worker, suite=BenchmarkSuite(cases=_CASES[:1])
    )

    report = run(runner.run(engines=["texel-style-v1"]))
    outcome = report.engines[0].outcomes[0]

    assert outcome.succeeded
    assert outcome.technical.logical_size == (32, 32)
    assert outcome.technical.size_matches is True
    assert outcome.technical.palette_within_budget is True
    assert outcome.technical.quality_score is not None
    assert outcome.technical.pixel_exact is not None


def test_a_fallback_does_not_count_as_success_for_the_requested_engine():
    """Se outro motor atendeu, o motor pedido falhou — e o relatório diz isso."""
    honesto = CaseOutcome(
        case_id="a", engine_id="motor-a", resolved_engine_id="motor-a", succeeded=True
    )
    substituido = CaseOutcome(
        case_id="b", engine_id="motor-a", resolved_engine_id="motor-b", succeeded=True
    )
    report = EngineReport(engine_id="motor-a", outcomes=[honesto, substituido])

    assert honesto.counts_for_engine is True
    assert substituido.counts_for_engine is False
    assert report.succeeded == 1
    assert report.failure_rate == 0.5


def test_a_failed_engine_is_reported_not_swallowed(container: AppContainer):
    """Motor indisponível vira falha registrada, não caso ausente."""
    runner = BenchmarkRunner(
        container.service, container.worker, suite=BenchmarkSuite(cases=_CASES[:1])
    )
    report = run(runner.run(engines=["motor-que-nao-existe"]))
    block = report.engines[0]

    assert block.total == 1
    assert block.failure_rate == 1.0
    assert block.outcomes[0].error


def test_correction_ratio_measures_how_much_the_postprocessor_had_to_fix():
    """A métrica mais reveladora do §20, e a que quase ninguém olha."""
    exigente = TechnicalMetrics(raw_color_count=200, color_count=16)
    comportado = TechnicalMetrics(raw_color_count=18, color_count=16)

    assert exigente.correction_ratio == 0.92
    assert comportado.correction_ratio is not None
    assert comportado.correction_ratio < 0.15
    # Sem a contagem bruta não há como afirmar nada — e `None` diz isso.
    assert TechnicalMetrics(color_count=16).correction_ratio is None


def test_the_visual_axis_starts_empty_and_stays_separate():
    """O §21 em forma de teste: o AssetFlow não inventa nota de beleza."""
    outcome = CaseOutcome(case_id="a", engine_id="motor-a", succeeded=True)
    document = outcome.document()

    assert document["visual"]["pending"] is True
    assert document["visual"]["silhouette"] is None
    # Os dois eixos são chaves diferentes — nunca somados em um número só.
    assert set(document) >= {"technical", "visual"}


def test_report_document_explains_both_axes(container: AppContainer):
    container.registry.enable("texel-style-v1")
    runner = BenchmarkRunner(
        container.service, container.worker, suite=BenchmarkSuite(cases=_CASES[:1])
    )
    document = run(runner.run(engines=["texel-style-v1"])).document()

    assert "technical" in document["axes"]
    assert "visual" in document["axes"]
    assert document["suite_size"] == 1


def test_suite_can_be_filtered_by_case():
    suite = BenchmarkSuite(cases=_CASES)
    assert [case.id for case in suite.filtered(["potion_16"]).cases] == ["potion_16"]
    # Filtro vazio devolve a suíte inteira, e não uma suíte vazia.
    assert suite.filtered(None).cases == _CASES
