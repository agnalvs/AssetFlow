"""Analisadores estruturais, nota de qualidade e política de aceitação.

O outro lado da separação do plano Pixel §38: aqui nada reprova por si só. Os
analisadores medem indicadores (§48 a §55), o QualityScorer os transforma em
uma nota (§56) e a PixelAcceptancePolicy decide o que fazer com o conjunto
(§59 e §60).

Dois princípios governam o arquivo inteiro:

* **detectar não é corrigir** (§29 e §106) — um pixel isolado pode ser um olho
  ou o brilho de uma lâmina, então os testes conferem que a imagem sai da
  análise byte a byte igual à que entrou;
* **nota não é veredito** (§57 e §107) — o último teste do arquivo existe só
  para provar que ``pixel_exact`` e ``quality_score`` nunca se compensam.

As figuras são desenhadas pixel a pixel: cada número esperado pode ser
conferido contando os quadradinhos descritos no comentário acima dele.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

from assetflow.pixel.acceptance import PixelAcceptancePolicy
from assetflow.pixel.contracts.output_spec import PixelOutputSpec
from assetflow.pixel.contracts.validation_report import (
    CheckStatus,
    HardCheckResult,
    PixelAssetStatus,
    PixelValidationReport,
    QualityMetrics,
    QualityReport,
)
from assetflow.pixel.imaging import to_array, to_image
from assetflow.pixel.validation import PixelValidator
from assetflow.pixel.validation.analyzers import (
    ClusterAnalyzer,
    ColorRedundancyAnalyzer,
    OrphanPixelAnalyzer,
    OutlineAnalyzer,
    PaletteUsageAnalyzer,
    SpriteOccupancyAnalyzer,
    ValidationContext,
)
from assetflow.pixel.validation.scoring import (
    MICROCLUSTER_PENALTY_MAX,
    OCCUPANCY_PENALTY_MAX,
    ORPHAN_FREE_RATIO,
    ORPHAN_PENALTY_RATE,
    OUTLINE_PENALTY_MAX,
    RARE_COLOR_PENALTY_MAX,
    RARE_COLOR_PENALTY_PER_COLOR,
    REDUNDANCY_PENALTY_MAX,
    REDUNDANCY_PENALTY_PER_PAIR,
    QualityScorer,
)

#: Cor do corpo dos sprites de teste, e o hexadecimal correspondente.
_BODY = (0x3A, 0x5A, 0x40)
_BODY_HEX = "#3a5a40"


# ---------------------------------------------------------------------------
# Helpers de imagem
# ---------------------------------------------------------------------------
def _blank(width: int, height: int) -> np.ndarray:
    """Canvas RGBA totalmente transparente no formato interno ``(h, w, 4)``."""
    return np.zeros((height, width, 4), dtype=np.uint8)


def _fill(
    array: np.ndarray,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
    alpha: int = 255,
) -> None:
    """Pinta o retângulo **inclusivo** ``(x0, y0)``-``(x1, y1)``."""
    array[y0 : y1 + 1, x0 : x1 + 1, :3] = color
    array[y0 : y1 + 1, x0 : x1 + 1, 3] = alpha


def _clean_square(canvas: int, side: int) -> Image.Image:
    """Quadrado sólido centralizado — o sprite estruturalmente perfeito."""
    array = _blank(canvas, canvas)
    start = (canvas - side) // 2
    _fill(array, start, start, start + side - 1, start + side - 1, _BODY)
    return to_image(array)


def _spec(width: int = 64, height: int = 64, **overrides: object) -> PixelOutputSpec:
    """PixelOutputSpec inline: só a resolução lógica é obrigatória."""
    payload: dict[str, object] = {"logical_size": {"width": width, "height": height}}
    payload.update(overrides)
    return PixelOutputSpec.model_validate(payload)


def _context(image: Image.Image, spec: PixelOutputSpec) -> ValidationContext:
    """A imagem e o spec — o único material que um analisador recebe."""
    return ValidationContext(image=image, spec=spec)


# ---------------------------------------------------------------------------
# Analisadores estruturais (§48 a §55)
# ---------------------------------------------------------------------------
def test_orphan_analyzer_counts_isolated_pixels_without_erasing_them():
    """§48: pixels sem vizinho da mesma cor viram número, não sumiço.

    A figura: um bloco sólido de 8×8 (nenhum pixel dele é órfão, todos têm
    vizinho igual) e três pixels de outra cor jogados longe uns dos outros.
    São exatamente três órfãos.

    A segunda metade do teste é o que o §51 e o §106 protegem: detectar não
    autoriza remover. Um pixel isolado pode ser um olho ou um brilho, e o
    analisador que o apagasse melhoraria a nota destruindo o desenho.
    """
    array = _blank(24, 24)
    _fill(array, 4, 4, 11, 11, _BODY)
    for x, y in ((16, 2), (2, 16), (20, 20)):
        array[y, x] = (0xFF, 0xE8, 0x66, 255)
    image = to_image(array)
    before = to_array(image).tobytes()

    result = OrphanPixelAnalyzer().analyze(_context(image, _spec(24, 24)))

    assert result.metrics["orphan_pixel_count"] == 3
    # Posições em (x, y), varridas de cima para baixo e da esquerda para a
    # direita: a ordem do relatório não pode depender da varredura.
    assert result.metrics["orphan_positions"] == ((16, 2), (2, 16), (20, 20))
    # 64 pixels do bloco + os 3 soltos.
    assert result.metrics["orphan_pixel_ratio"] == round(3 / 67, 6)
    assert to_array(image).tobytes() == before


def test_cluster_analyzer_counts_components_by_size():
    """§49 e §50: componentes conexos **por cor**, separados por tamanho.

    A figura tem quatro blocos de cores diferentes: um de 1 pixel, um de 2,
    um de 3 e um de 25. Três dos quatro são microclusters — a proporção alta
    é o sintoma de superfície que se desfez na redução, e vira aviso, nunca
    reprovação (§51).
    """
    array = _blank(16, 16)
    array[1, 1] = (0xD9, 0x4F, 0x3A, 255)
    array[1, 5] = array[1, 6] = (0x3A, 0x7B, 0xD9, 255)
    array[1, 9] = array[1, 10] = array[2, 9] = (0xF0, 0xE6, 0xB0, 255)
    _fill(array, 2, 8, 6, 12, _BODY)

    result = ClusterAnalyzer().analyze(_context(to_image(array), _spec(16, 16)))

    assert result.metrics["cluster_total"] == 4
    assert result.metrics["single_pixel_clusters"] == 1
    assert result.metrics["two_pixel_clusters"] == 1
    assert result.metrics["three_pixel_clusters"] == 1
    assert result.metrics["microcluster_ratio"] == round(3 / 4, 6)
    assert [warning.code for warning in result.warnings] == ["PX-WARN-MICROCLUSTER"]


def test_occupancy_analyzer_measures_the_sprite_box():
    """§53: quanto do canvas o sprite ocupa, e onde ele está.

    Um quadrado de 32×32 no centro de um canvas 64×64 ocupa um quarto da
    área e não encosta em nada — a situação saudável, sem aviso nenhum.
    """
    array = _blank(64, 64)
    _fill(array, 16, 16, 47, 47, _BODY)

    result = SpriteOccupancyAnalyzer().analyze(_context(to_image(array), _spec(64, 64)))

    assert result.metrics["foreground_pixels"] == 32 * 32
    assert result.metrics["foreground_occupancy"] == 0.25
    assert result.metrics["bounding_box"] == (16, 16, 47, 47)
    assert result.metrics["touches_border"] is False
    assert result.warnings == ()


def test_occupancy_analyzer_warns_on_a_tiny_sprite_and_on_border_contact():
    """§53: dois defeitos silenciosos que nenhum hard check pega.

    Um personagem de 4×4 perdido em um canvas de 64×64 é um arquivo
    tecnicamente perfeito e artisticamente inútil; um sprite encostado na
    borda quase sempre saiu decepado. Nenhum dos dois viola requisito algum —
    por isso são aviso, e por isso precisam existir.
    """
    tiny = _blank(64, 64)
    _fill(tiny, 30, 30, 33, 33, _BODY)  # 16 de 4096 pixels = 0,39%
    small = SpriteOccupancyAnalyzer().analyze(_context(to_image(tiny), _spec(64, 64)))

    assert [warning.code for warning in small.warnings] == ["PX-WARN-OCCUPANCY-LOW"]
    assert small.warnings[0].detail["threshold"] == _spec().validation.min_occupancy

    clipped = _blank(64, 64)
    _fill(clipped, 0, 20, 40, 43, _BODY)  # ocupação saudável, mas colada à esquerda
    on_border = SpriteOccupancyAnalyzer().analyze(
        _context(to_image(clipped), _spec(64, 64))
    )

    assert [warning.code for warning in on_border.warnings] == ["PX-WARN-BORDER"]
    assert on_border.metrics["touches_border"] is True


def test_palette_usage_analyzer_returns_the_frequency_of_each_color():
    """§54: o limite de cores é um orçamento, e este é o extrato.

    Dez pixels de uma cor, cinco de outra, um da terceira. A ordem do
    dicionário é o próprio ranking — quem lê o relatório vê primeiro quem
    mais gasta do orçamento. A cor de um pixel só é destacada como rara, sem
    que isso a condene: ela pode ser exatamente o brilho do olho (§47).
    """
    array = _blank(8, 8)
    _fill(array, 0, 0, 4, 1, _BODY)  # 10 pixels
    _fill(array, 0, 2, 4, 2, (0xA3, 0xB1, 0x8A))  # 5 pixels
    array[3, 0] = (0xFF, 0xE8, 0x66, 255)  # 1 pixel

    result = PaletteUsageAnalyzer().analyze(_context(to_image(array), _spec(8, 8)))

    assert list(result.metrics["palette_usage"].items()) == [
        (_BODY_HEX, 10),
        ("#a3b18a", 5),
        ("#ffe866", 1),
    ]
    assert result.metrics["rare_colors"] == ("#ffe866",)
    assert [warning.code for warning in result.warnings] == ["PX-WARN-PALETTE-RARE"]


def test_color_redundancy_analyzer_pairs_only_indistinguishable_colors():
    """§55: duas entradas de paleta gastas na mesma cor.

    ``#aa6255`` e ``#ab6356`` diferem em 1 por canal — na tela são a mesma
    cor, e a paleta de 16 vira uma paleta de 15. ``#12151c`` está a uma
    distância enorme das duas e por isso não forma par com ninguém: o
    analisador aponta desperdício, não qualquer proximidade.
    """
    array = _blank(8, 8)
    _fill(array, 0, 0, 7, 2, (0xAA, 0x62, 0x55))
    _fill(array, 0, 3, 7, 5, (0xAB, 0x63, 0x56))
    _fill(array, 0, 6, 7, 7, (0x12, 0x15, 0x1C))

    result = ColorRedundancyAnalyzer().analyze(_context(to_image(array), _spec(8, 8)))

    assert result.metrics["redundant_color_pairs"] == (("#aa6255", "#ab6356"),)
    assert [warning.code for warning in result.warnings] == [
        "PX-WARN-COLOR-REDUNDANCY"
    ]


def test_outline_analyzer_measures_the_outline_without_rebuilding_it():
    """§52: o contorno é medido; reconstruí-lo seria desenhar por cima.

    Em um quadrado sólido de 10×10 o contorno é o anel externo: 10² − 8² = 36
    pixels, em uma peça só. Fragmentação perto de zero é o que significa
    "silhueta inteira" — e a versão 1.0 para exatamente aqui, porque reforçar
    contorno dentro do Validator violaria a regra de não alterar pixel (§37,
    §104).
    """
    array = _blank(32, 32)
    _fill(array, 8, 8, 17, 17, _BODY)
    image = to_image(array)
    before = to_array(image).tobytes()

    result = OutlineAnalyzer().analyze(_context(image, _spec(32, 32)))

    assert result.metrics["outline_pixels"] == 36
    assert result.metrics["outline_colors"] == (_BODY_HEX,)
    assert result.metrics["outline_fragmentation"] == round(1 / 36, 6)
    assert result.warnings == ()
    assert to_array(image).tobytes() == before


# ---------------------------------------------------------------------------
# QualityScorer (§56)
# ---------------------------------------------------------------------------
def test_scorer_gives_a_structurally_clean_sprite_the_top_score():
    """Nota alta é o estado natural de quem não tem defeito estrutural.

    Nenhum órfão, um único bloco de cor, ocupação dentro da faixa do profile
    e contorno inteiro: nada a descontar, e o dicionário de penalidades sai
    vazio em vez de listar seis zeros.
    """
    array = _blank(64, 64)
    _fill(array, 16, 16, 47, 47, _BODY)

    quality = PixelValidator().validate(to_image(array), _spec(64, 64)).quality

    assert quality.score == 100
    assert quality.penalties == {}
    assert quality.warnings == ()
    # A nota só é comparável entre relatórios feitos pela mesma lista (§56).
    assert set(quality.analyzers) == {
        "orphan_pixels",
        "clusters",
        "occupancy",
        "palette_usage",
        "color_redundancy",
        "outline",
    }


def test_scorer_records_every_penalty_and_the_score_closes_with_the_sum():
    """§56: a nota precisa poder responder "por que 42?".

    Os pesos são experimentais por decisão do §60, então o teste não fixa os
    números: ele fixa o mecanismo — franquia (abaixo dela não há desconto),
    taxa linear acima dela, teto por indicador para que um defeito só não
    zere a nota, e ``nota = 100 − soma das penalidades registradas``. Sem esse
    fechamento a nota seria um número mágico impossível de depurar.
    """
    excess = 0.04
    metrics = QualityMetrics(
        orphan_pixel_ratio=ORPHAN_FREE_RATIO + excess,
        microcluster_ratio=1.0,  # muito acima da franquia: bate no teto
        foreground_occupancy=0.0,  # abaixo da faixa saudável do profile
        redundant_color_pairs=(("#aa6255", "#ab6356"), ("#12151c", "#13161d")),
        outline_fragmentation=1.0,  # idem: bate no teto
        rare_colors=("#ffe866",),
    )

    score, penalties = QualityScorer().score(metrics, (), _spec(64, 64))

    assert penalties["orphan"] == round(excess * ORPHAN_PENALTY_RATE, 2)
    assert penalties["microcluster"] == MICROCLUSTER_PENALTY_MAX
    assert penalties["outline"] == OUTLINE_PENALTY_MAX
    assert penalties["redundancy"] == 2 * REDUNDANCY_PENALTY_PER_PAIR
    assert penalties["rare_colors"] == RARE_COLOR_PENALTY_PER_COLOR
    assert 0.0 < penalties["occupancy"] <= OCCUPANCY_PENALTY_MAX
    assert score == math.floor(100.0 - math.fsum(penalties.values()))


def test_occupancy_penalty_is_measured_against_what_the_profile_lets_you_miss():
    """§53: o teto da ocupação precisa ser alcançável em qualquer profile.

    Ocupação é uma fração de 0 a 1, então o quanto dá para errar depende do
    lado: abaixo de ``min_occupancy`` cabem ``min_occupancy`` pontos, acima de
    ``max_occupancy`` cabem ``1 - max_occupancy``. Normalizar o desvio por
    outra coisa — a largura da faixa, por exemplo — mistura dois eixos e
    afunda a penalidade: com a faixa padrão ``[0.05, 0.95]``, um sprite
    **inteiramente vazio**, que é o pior desvio que pode existir, descontaria
    0,83 de 15 pontos possíveis e o indicador viraria decoração no relatório.

    Por isso o teste fixa as âncoras da curva em vez de um número solto: na
    borda da faixa desconta zero, no extremo do eixo desconta o teto, e no
    meio do caminho desconta metade — em um profile largo, em um estreito e
    na exigência exata.
    """
    scorer = QualityScorer()

    def penalty(occupancy: float, **limits: object) -> float:
        _, penalties = scorer.score(
            QualityMetrics(foreground_occupancy=occupancy),
            (),
            _spec(64, 64, validation=limits),
        )
        return penalties.get("occupancy", 0.0)

    # Faixa padrão: 5 pontos percentuais de espaço para errar de cada lado.
    assert penalty(0.30) == 0.0
    assert penalty(0.05) == 0.0
    assert penalty(0.95) == 0.0
    assert penalty(0.0) == OCCUPANCY_PENALTY_MAX  # canvas vazio
    assert penalty(1.0) == OCCUPANCY_PENALTY_MAX  # canvas cheio
    assert penalty(0.025) == OCCUPANCY_PENALTY_MAX / 2
    assert penalty(0.975) == OCCUPANCY_PENALTY_MAX / 2

    # O tile do §66 vai de 50% a 100%: não existe lado de cima para violar, e
    # o de baixo é meio eixo — o mesmo 25% que seria irrelevante no profile
    # de personagem custa metade do teto aqui.
    tile = {"min_occupancy": 0.50, "max_occupancy": 1.0}
    assert penalty(1.0, **tile) == 0.0
    assert penalty(0.25, **tile) == OCCUPANCY_PENALTY_MAX / 2
    assert penalty(0.0, **tile) == OCCUPANCY_PENALTY_MAX

    # Faixa degenerada é exigência exata: qualquer desvio leva o teto.
    exact = {"min_occupancy": 0.40, "max_occupancy": 0.40}
    assert penalty(0.40, **exact) == 0.0
    assert penalty(0.39, **exact) == OCCUPANCY_PENALTY_MAX


def test_scorer_never_leaves_the_0_100_range():
    """A nota é uma escala fechada, mesmo com todos os indicadores no pior caso.

    Também é aqui que os tetos por indicador ficam visíveis: 50 pares de
    cores redundantes descontam o mesmo que os primeiros que estouraram o
    limite, senão um único sintoma decidiria a nota sozinho.
    """
    spec = _spec(64, 64)
    scorer = QualityScorer()

    healthy, penalties = scorer.score(QualityMetrics(foreground_occupancy=0.25), (), spec)
    assert healthy == 100
    assert penalties == {}

    worst, penalties = scorer.score(
        QualityMetrics(
            orphan_pixel_ratio=1.0,
            microcluster_ratio=1.0,
            foreground_occupancy=1.0,
            redundant_color_pairs=tuple(
                (f"#0000{index:02x}", f"#0100{index:02x}") for index in range(50)
            ),
            outline_fragmentation=1.0,
            rare_colors=tuple(f"#00ff{index:02x}" for index in range(50)),
        ),
        (),
        spec,
    )
    assert 0 <= worst <= 100
    assert penalties["redundancy"] == REDUNDANCY_PENALTY_MAX
    assert penalties["rare_colors"] == RARE_COLOR_PENALTY_MAX


# ---------------------------------------------------------------------------
# PixelAcceptancePolicy (§59 e §60)
# ---------------------------------------------------------------------------
def _report(
    *,
    pixel_exact: bool = True,
    score: int = 100,
    checks: tuple[HardCheckResult, ...] = (),
) -> PixelValidationReport:
    """Relatório sintético: a política é função pura de um relatório fechado.

    Montá-lo à mão é o ponto do §59 — nenhuma decisão da política depende de
    imagem, de check ou de analisador, só do que o relatório afirma.
    """
    return PixelValidationReport(
        pixel_exact=pixel_exact,
        hard_checks=checks,
        quality=QualityReport(score=score),
    )


def test_policy_rejects_a_hard_failure_with_the_62_diagnostic():
    """§60: falha dura reprova, e a nota alta não tem voz.

    A razão registrada segue o formato do §62 — código, o que era exigido e o
    que chegou —, para que o log responda sozinho *por que* o asset foi
    recusado.
    """
    failure = HardCheckResult(
        code="PX-COLOR-001",
        name="Maximum Colors",
        status=CheckStatus.FAIL,
        expected="<=16",
        actual="23",
    )

    decision = PixelAcceptancePolicy().decide(
        _report(pixel_exact=False, score=98, checks=(failure,))
    )

    assert decision.status is PixelAssetStatus.REJECTED
    assert decision.rejected
    assert not decision.accepted
    assert "PX-COLOR-001: esperado <=16, obtido 23" in decision.reasons
    assert decision.quality_score == 98
    assert decision.failures == (failure,)


def test_policy_separates_approved_from_quality_warning_by_the_threshold():
    """§60: acima do limiar aprova; abaixo, entrega com ressalva.

    QUALITY_WARNING não é reprovação — o asset continua entregável e vai para
    revisão manual. Confundir os dois estados transformaria um indicador
    estrutural em veredito técnico, que é o que o §47 proíbe.
    """
    policy = PixelAcceptancePolicy(quality_threshold=70)

    approved = policy.decide(_report(score=70))
    warned = policy.decide(_report(score=69))

    assert approved.status is PixelAssetStatus.APPROVED
    assert warned.status is PixelAssetStatus.QUALITY_WARNING
    assert warned.accepted
    assert warned.pixel_exact is True


def test_policy_threshold_argument_wins_over_the_constructor():
    """§60: quem conhece a exigência do asset é o profile, não a instância.

    O limiar do construtor é só o padrão de quem montou a política. Se o
    argumento não vencesse, um profile estrito seria julgado pela régua de
    quem instanciou o serviço — e o mesmo relatório precisa poder ser julgado
    por políticas diferentes (§59).
    """
    policy = PixelAcceptancePolicy(quality_threshold=10)
    report = _report(score=90)

    default = policy.decide(report)
    strict = policy.decide(report, threshold=95)

    assert default.status is PixelAssetStatus.APPROVED
    assert default.quality_threshold == 10
    assert strict.status is PixelAssetStatus.QUALITY_WARNING
    assert strict.quality_threshold == 95


# ---------------------------------------------------------------------------
# O teste central da separação (§57 e §107)
# ---------------------------------------------------------------------------
def _scattered_sprite() -> Image.Image:
    """Pixel Exact e estruturalmente péssimo.

    Um pixel opaco a cada dois, em ambos os eixos: 1024 pixels que não
    encostam em nenhum vizinho. Ocupação saudável (25% do canvas), quatro
    cores dentro do teto, alpha binário, resolução exata — passa em todos os
    requisitos obrigatórios e ainda assim não tem uma única superfície.
    """
    array = _blank(64, 64)
    palette = (
        (0x12, 0x15, 0x1C),
        (0xD9, 0x4F, 0x3A),
        (0x3A, 0x7B, 0xD9),
        (0xF0, 0xE6, 0xB0),
    )
    index = 0
    for y in range(0, 64, 2):
        for x in range(0, 64, 2):
            array[y, x] = (*palette[index % len(palette)], 255)
            index += 1
    return to_image(array)


def test_pixel_exact_and_quality_score_never_compensate_each_other():
    """§57 e §107: são dois eixos, e misturá-los apaga a informação útil.

    Caso A é tecnicamente correto e artisticamente problemático; caso B é o
    inverso — bonito e fora da especificação. Se as duas medidas virassem um
    número só, os dois receberiam vereditos parecidos, e o operador perderia
    justamente o que diz o que fazer com cada um: o A precisa de revisão
    artística, o B precisa voltar para o pipeline.
    """
    spec = _spec(64, 64)
    threshold = spec.validation.quality_threshold
    validator = PixelValidator()
    policy = PixelAcceptancePolicy()

    exact_but_ugly = validator.validate(_scattered_sprite(), spec)
    pretty_but_wrong = validator.validate(_clean_square(48, 24), spec)

    assert exact_but_ugly.pixel_exact is True
    assert exact_but_ugly.quality.score < threshold

    assert pretty_but_wrong.pixel_exact is False
    assert pretty_but_wrong.quality.score >= threshold
    assert pretty_but_wrong.quality.score > exact_but_ugly.quality.score

    ugly_decision = policy.decide(exact_but_ugly, threshold=threshold)
    wrong_decision = policy.decide(pretty_but_wrong, threshold=threshold)

    assert ugly_decision.status is PixelAssetStatus.QUALITY_WARNING
    assert ugly_decision.accepted, "nota baixa não reprova um asset correto"
    assert wrong_decision.status is PixelAssetStatus.REJECTED
    assert wrong_decision.quality_score == 100, "a nota alta é registrada, não usada"
