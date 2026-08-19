"""HARD CHECKS do PixelValidator e a separação do plano Pixel §38.

Aqui só se mede o **veredito técnico**: cada requisito obrigatório (PX-DIM-001
a PX-BOUND-001), o que ele escreve no relatório quando reprova e o efeito de
cada resultado sobre ``pixel_exact``.

A nota de qualidade, os analisadores estruturais e a política de aceitação
ficam em ``tests/pixel/test_quality.py``. A separação entre os dois arquivos é
a mesma que o plano Pixel §38 exige do código: erro fatal de um lado,
indicador estrutural do outro, sem que um dilua o outro.

As imagens são construídas pixel a pixel com numpy — nada de aleatório e nada
vindo do disco: cada número esperado neste arquivo pode ser conferido a partir
da figura desenhada logo acima dele.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from assetflow.pixel.acceptance import PixelAcceptancePolicy
from assetflow.pixel.contracts.output_spec import PixelOutputSpec
from assetflow.pixel.contracts.validation_report import (
    CheckStatus,
    HardCheckResult,
    PixelValidationReport,
)
from assetflow.pixel.imaging import to_array, to_image
from assetflow.pixel.validation import PixelValidator

#: Cor do corpo dos sprites de teste. Qualquer cor serve — ela só precisa ser
#: sempre a mesma para que a contagem de cores seja previsível.
_BODY = (0x3A, 0x5A, 0x40)


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
    """Quadrado sólido centralizado — o sprite estruturalmente perfeito.

    Sem pixel órfão, com um único bloco de cor e contorno inteiro: serve para
    isolar um defeito de cada vez, porque tudo o que ele pode errar é o que o
    teste mandou errar.
    """
    array = _blank(canvas, canvas)
    start = (canvas - side) // 2
    _fill(array, start, start, start + side - 1, start + side - 1, _BODY)
    return to_image(array)


def _spec(width: int = 64, height: int = 64, **overrides: object) -> PixelOutputSpec:
    """PixelOutputSpec inline: só a resolução lógica é obrigatória."""
    payload: dict[str, object] = {"logical_size": {"width": width, "height": height}}
    payload.update(overrides)
    return PixelOutputSpec.model_validate(payload)


def _check(report: PixelValidationReport, code: str) -> HardCheckResult:
    """Localiza um hard check pelo código — o relatório é uma tupla ordenada."""
    for check in report.hard_checks:
        if check.code == code:
            return check
    raise AssertionError(f"o check {code} não apareceu no relatório")


# ---------------------------------------------------------------------------
# Um teste por requisito obrigatório
# ---------------------------------------------------------------------------
def test_dimensions_check_demands_the_exact_logical_size():
    """PX-DIM-001: um asset 64×64 é um PNG de 64×64 (plano Pixel §40).

    É a regra de ouro nº 1 (§3): sem ela, todos os outros números do
    relatório teriam sido medidos na imagem errada. Por isso o check compara
    tamanho, não proporção — 48×48 é "quase" e "quase" reprova.
    """
    spec = _spec(64, 64)

    reproved = _check(PixelValidator().validate(_clean_square(48, 24), spec), "PX-DIM-001")
    assert reproved.status is CheckStatus.FAIL
    assert reproved.expected == "64x64"
    assert reproved.actual == "48x48"

    approved = _check(PixelValidator().validate(_clean_square(64, 32), spec), "PX-DIM-001")
    assert approved.status is CheckStatus.PASS
    assert approved.actual == "64x64"


def test_alpha_check_rejects_partial_transparency():
    """PX-ALPHA-001: no Pixel Exact o pixel existe ou não existe (§41).

    Um único pixel a 72 já é o rastro de redução interpolada que o §21 proíbe
    — e o relatório precisa dizer *qual* valor apareceu e em quantos pixels,
    porque é o que separa "uma franja de borda" de "o sprite inteiro saiu
    semitransparente" (§62).
    """
    array = _blank(8, 8)
    _fill(array, 1, 1, 6, 6, (200, 40, 40))
    array[3, 3, 3] = 72

    reproved = _check(PixelValidator().validate(to_image(array), _spec(8, 8)), "PX-ALPHA-001")
    assert reproved.status is CheckStatus.FAIL
    assert reproved.expected == "{0, 255}"
    assert reproved.detail["forbidden_values"] == [{"value": 72, "pixels": 1}]

    array[3, 3, 3] = 255
    approved = _check(PixelValidator().validate(to_image(array), _spec(8, 8)), "PX-ALPHA-001")
    assert approved.status is CheckStatus.PASS
    assert approved.actual == "{0, 255}"


def test_color_count_check_reports_expected_and_actual_for_the_diagnostic():
    """PX-COLOR-001 (§42) escrito no formato que o §62 exige.

    23 cores desenhadas à mão contra um teto de 16. O relatório não pode
    obrigar quem lê o log a abrir o JSON: ``expected``/``actual`` já saem
    prontos, e é deles que a política monta
    ``"PX-COLOR-001: esperado <=16, obtido 23"``.
    """
    array = _blank(8, 8)
    for index in range(23):
        y, x = divmod(index, 8)
        # Cores bem separadas entre si: o que está sob teste é a contagem, não
        # a proximidade (essa é a análise de redundância, do outro lado).
        array[y, x] = (11 * index, 255 - 11 * index, 128, 255)

    spec = _spec(8, 8, palette={"mode": "max_colors", "max_colors": 16})
    report = PixelValidator().validate(to_image(array), spec)

    check = _check(report, "PX-COLOR-001")
    assert check.status is CheckStatus.FAIL
    assert check.expected == "<=16"
    assert check.actual == "23"
    assert check.detail["excess"] == 7

    decision = PixelAcceptancePolicy().decide(report)
    assert "PX-COLOR-001: esperado <=16, obtido 23" in decision.reasons


def test_locked_palette_check_rejects_foreign_colors_and_skips_when_not_locked():
    """PX-PALETTE-001 (§43): paleta travada é travada mesmo.

    No modo LOCKED o usuário não pediu "mais ou menos estas cores" — uma
    única cor sobrevivente já quebra a coerência com o resto do projeto. E o
    mesmo check **não se aplica** quando o profile deriva a paleta da imagem:
    ali não existe paleta para violar.
    """
    array = _blank(8, 8)
    _fill(array, 0, 0, 7, 3, (0x12, 0x15, 0x1C))
    _fill(array, 0, 4, 7, 5, (0x3A, 0x5A, 0x40))
    _fill(array, 0, 6, 3, 7, (0xA3, 0xB1, 0x8A))
    _fill(array, 4, 6, 7, 7, (0x7F, 0x00, 0x7F))  # 8 pixels fora da paleta
    image = to_image(array)

    locked = _spec(
        8,
        8,
        palette={"mode": "locked", "colors": ["#12151c", "#3a5a40", "#a3b18a"]},
    )
    report = PixelValidator().validate(image, locked)
    check = _check(report, "PX-PALETTE-001")

    assert check.status is CheckStatus.FAIL
    assert check.detail["foreign_color_count"] == 1
    assert check.detail["foreign_colors"] == [{"color": "#7f007f", "pixels": 8}]
    assert report.pixel_exact is False

    auto = _spec(8, 8, palette={"mode": "max_colors", "max_colors": 16})
    skipped = _check(PixelValidator().validate(image, auto), "PX-PALETTE-001")
    assert skipped.status is CheckStatus.SKIPPED
    assert skipped.message


def test_locked_palette_check_rejects_an_unresolved_project_palette():
    """PX-PALETTE-001 (§43): paleta de projeto que não existe é reprovação.

    Quando o ``palette_id`` não está na tabela ``palettes:`` do YAML, o
    ``PixelProfileRegistry`` devolve o profile intacto e o quantizador cai
    para median cut — ou seja, o asset sai bonito e **sem** a paleta do
    projeto. Se o check apenas se pulasse, essa configuração quebrada viraria
    incoerência visual silenciosa entre personagem, inimigo e tile, meses
    depois. Reprovar aqui é o que a faz aparecer no relatório do asset.
    """
    array = _blank(8, 8)
    _fill(array, 0, 0, 7, 7, _BODY)

    spec = _spec(
        8, 8, palette={"mode": "project_palette", "palette_id": "mundo_inexistente"}
    )
    report = PixelValidator().validate(to_image(array), spec)
    check = _check(report, "PX-PALETTE-001")

    assert check.status is CheckStatus.FAIL
    assert check.detail["palette_id"] == "mundo_inexistente"
    assert report.pixel_exact is False, (
        "entregar como Pixel Exact um asset que ignorou a paleta pedida seria "
        "aprovar por ausência de evidência"
    )


def test_empty_image_check_is_the_only_one_that_catches_a_blank_canvas():
    """PX-EMPTY-001 (§44 e §88): o vazio passa em todos os outros requisitos.

    Um PNG 64×64 totalmente transparente tem a resolução exata, alpha
    perfeitamente binário e zero cores — ou seja, cabe em qualquer teto de
    paleta. Sem este check o pipeline entregaria um arquivo vazio com nota
    técnica impecável, que é exatamente o caso de borda do §88.
    """
    report = PixelValidator().validate(to_image(_blank(64, 64)), _spec(64, 64))

    assert _check(report, "PX-DIM-001").status is CheckStatus.PASS
    assert _check(report, "PX-ALPHA-001").status is CheckStatus.PASS
    assert _check(report, "PX-COLOR-001").status is CheckStatus.PASS

    empty = _check(report, "PX-EMPTY-001")
    assert empty.status is CheckStatus.FAIL
    assert empty.actual == "0"
    assert empty.detail["foreground_pixels"] == 0
    assert report.pixel_exact is False


def test_boundary_check_obeys_the_profile_policy():
    """PX-BOUND-001 (§45): o rigor é do profile, não do check.

    O mesmo sprite encostado na borda esquerda é um erro para um personagem e
    o comportamento correto para um tile. Por isso ``boundary_touch`` decide
    entre reprovar, aprovar registrando e nem rodar — e no modo ``warn`` o
    aviso visível sai do analisador, porque hard check não emite aviso (§38).
    """
    array = _blank(16, 16)
    _fill(array, 0, 4, 9, 11, (200, 180, 90))
    image = to_image(array)

    strict = PixelValidator().validate(
        image, _spec(16, 16, validation={"boundary_touch": "fail"})
    )
    reproved = _check(strict, "PX-BOUND-001")
    assert reproved.status is CheckStatus.FAIL
    assert reproved.detail["borders"] == ["left"]
    assert strict.pixel_exact is False

    tolerant = PixelValidator().validate(
        image, _spec(16, 16, validation={"boundary_touch": "warn"})
    )
    warned = _check(tolerant, "PX-BOUND-001")
    assert warned.status is CheckStatus.PASS
    assert warned.detail["touches_border"] is True
    assert tolerant.pixel_exact is True
    assert "PX-WARN-BORDER" in {warning.code for warning in tolerant.quality.warnings}

    ignored = PixelValidator().validate(
        image, _spec(16, 16, validation={"boundary_touch": "ignore"})
    )
    assert _check(ignored, "PX-BOUND-001").status is CheckStatus.SKIPPED
    assert not any(
        warning.code == "PX-WARN-BORDER" for warning in ignored.quality.warnings
    )


# ---------------------------------------------------------------------------
# Regras transversais do veredito
# ---------------------------------------------------------------------------
def test_a_skipped_check_is_not_an_approval_but_does_not_block_pixel_exact():
    """Requisito desligado pelo profile não vira aprovação (§38 e §65).

    A imagem tem um pixel a alpha 128 — ela **reprovaria** em PX-ALPHA-001.
    Com ``require_binary_alpha: false`` o check nem roda: o resultado é
    SKIPPED, e SKIPPED não é PASS. Ainda assim o asset continua Pixel Exact,
    porque o profile nunca exigiu esse requisito. Confundir as duas coisas
    faria um profile permissivo parecer um asset aprovado.
    """
    array = _blank(16, 16)
    _fill(array, 4, 4, 11, 11, (60, 120, 200))
    array[5, 5, 3] = 128
    image = to_image(array)

    relaxed = PixelValidator().validate(
        image, _spec(16, 16, validation={"require_binary_alpha": False})
    )
    skipped = _check(relaxed, "PX-ALPHA-001")
    assert skipped.status is CheckStatus.SKIPPED
    assert relaxed.hard_check_map["PX-ALPHA-001"] == "skipped"
    assert relaxed.failures == ()
    assert relaxed.pixel_exact is True

    # A prova de que o requisito reprovaria se o profile o tivesse exigido.
    strict = PixelValidator().validate(image, _spec(16, 16))
    assert _check(strict, "PX-ALPHA-001").status is CheckStatus.FAIL
    assert strict.pixel_exact is False


def test_validator_never_touches_a_single_pixel():
    """Regra fundamental do §37 e §104: quem mede não corrige.

    A imagem entra suja de propósito — pixels soltos, duas cores quase
    idênticas e conteúdo encostado na borda. É justamente esse material que
    tentaria um analisador a "consertar" alguma coisa, e é por isso que o
    teste compara os bytes do array antes e depois de ``validate()``: se um
    dia alguém limpar a imagem dentro do Validator, o defeito desaparece do
    relatório e ninguém fica sabendo que ele existiu.
    """
    array = _blank(32, 32)
    _fill(array, 0, 8, 20, 23, (0xAA, 0x62, 0x55))
    for step in range(6):
        array[2 + step * 4, 1 + step * 4] = (0xAB, 0x63, 0x56, 255)
    image = to_image(array)
    before = to_array(image).tobytes()

    report = PixelValidator().validate(image, _spec(32, 32))

    assert to_array(image).tobytes() == before
    assert image.size == (32, 32)
    assert image.mode == "RGBA"
    assert report.quality.warnings, "sem defeito medido o teste não prova nada"


def test_one_hard_failure_sinks_pixel_exact_even_with_a_perfect_score():
    """§39 e §57: não existe média que esconda um erro fatal.

    O sprite é estruturalmente impecável — quadrado sólido, nenhum órfão,
    contorno inteiro — e tira a nota máxima. Ele apenas saiu no tamanho
    errado, e isso basta: ``pixel_exact`` é o E lógico dos requisitos, não a
    média deles.
    """
    report = PixelValidator().validate(_clean_square(48, 24), _spec(64, 64))

    assert report.quality.score == 100
    assert report.quality.penalties == {}
    assert [check.code for check in report.failures] == ["PX-DIM-001"]
    assert report.pixel_exact is False

    decision = PixelAcceptancePolicy().decide(report)
    assert decision.rejected
    assert decision.quality_score == 100
