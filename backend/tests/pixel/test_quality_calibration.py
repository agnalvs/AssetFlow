"""Calibração da nota: blocos pequenos e cores raras em ``config/quality.yaml``.

O que estes testes fixam:

- a configuração real carrega sem problema, e todo número dela é
  ``a_calibrar`` (nenhum tem fonte externa: saíram das referências);
- sem configuração, valem os números do plano §60;
- detalhe dentro do que as referências mostram não avisa nem desconta, e o
  que passa do limiar continua avisando e descontando;
- **a calibração não toca nenhum hard check**: dimensão, alpha e paleta dão o
  mesmo veredito com e sem ela;
- o pipeline, o laço do Optimizer e o relatório usam a mesma calibração.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

from assetflow.bootstrap import AppContainer
from assetflow.generation.postprocessing import ImageBuffer, PostProcessContext
from assetflow.pixel import PixelOutputSpec, PixelValidator, QualityCalibration
from assetflow.pixel.validation.calibration import (
    MICROCLUSTER_FREE_RATIO,
    MICROCLUSTER_WARNING_RATIO,
    PLANO,
    RARE_COLOR_FREE_COUNT,
    RARE_COLOR_WARNING_COUNT,
)

QUALITY_YAML = Path(__file__).resolve().parents[2] / "config" / "quality.yaml"

FUNDO = (40, 80, 160)
PONTOS = [(200, 30, 30), (30, 200, 30), (230, 230, 40), (240, 240, 240), (120, 40, 160), (250, 140, 20)]


def _calibrada() -> QualityCalibration:
    return QualityCalibration.from_config(yaml.safe_load(QUALITY_YAML.read_text(encoding="utf-8")))


def _sprite(pontos: int, *, alpha: int = 255) -> Image.Image:
    """Um bloco 10×10 e ``pontos`` pixels soltos de cores próprias dentro dele.

    Cada ponto é um bloco de 1 px e uma cor de 1 px: com ``n`` pontos, a fração
    de blocos pequenos é n / (n + 1) e há n cores raras.
    """
    rgba = np.zeros((16, 16, 4), dtype=np.uint8)
    rgba[3:13, 3:13, :3] = FUNDO
    rgba[3:13, 3:13, 3] = alpha
    for i, cor in enumerate(PONTOS[:pontos]):
        y, x = 5 + 2 * (i // 3), 5 + 2 * (i % 3)
        rgba[y, x, :3] = cor
    return Image.fromarray(rgba, "RGBA")


def _spec(lado: int = 16, cores: int = 16) -> PixelOutputSpec:
    return PixelOutputSpec(
        logical_size={"width": lado, "height": lado},
        palette={"mode": "max_colors", "max_colors": cores},
    )


def _codigos(relatorio) -> set[str]:
    return {aviso.code for aviso in relatorio.quality.warnings}


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def test_a_configuracao_real_carrega_sem_problema_e_tudo_e_a_calibrar():
    bruto = yaml.safe_load(QUALITY_YAML.read_text(encoding="utf-8"))
    calibracao = _calibrada()

    assert calibracao.problems == ()
    assert calibracao.microcluster.warning_ratio == 0.84
    assert calibracao.microcluster.free_ratio == 0.84
    assert calibracao.rare_colors.warning_count == 3
    assert calibracao.rare_colors.free_count == 3
    numeros = [item for secao in bruto.values() for item in secao.values()]
    assert numeros and all(item.get("a_calibrar") is True for item in numeros)


def test_sem_configuracao_valem_os_numeros_do_plano():
    for vazio in (None, {}):
        calibracao = QualityCalibration.from_config(vazio)
        assert calibracao == QualityCalibration()
        assert calibracao.source == PLANO
    padrao = QualityCalibration()
    assert padrao.microcluster.warning_ratio == MICROCLUSTER_WARNING_RATIO == 0.25
    assert padrao.microcluster.free_ratio == MICROCLUSTER_FREE_RATIO == 0.20
    assert padrao.rare_colors.warning_count == RARE_COLOR_WARNING_COUNT == 0
    assert padrao.rare_colors.free_count == RARE_COLOR_FREE_COUNT == 0


@pytest.mark.parametrize(
    ("bruto", "trecho"),
    [
        ({"blocos_pequenos": {"aviso": {"valor": 0.5}}}, "a_calibrar"),
        ({"blocos_pequenos": {"aviso": 0.5}}, "{valor: N, a_calibrar: true}"),
        ({"blocos_pequenos": {"aviso": {"valor": 1.5, "a_calibrar": True}}}, "fora da faixa"),
        ({"cores_raras": {"aviso": {"valor": 2.5, "a_calibrar": True}}}, "inteiro"),
        ({"cores_raras": {"limite": {"valor": 2, "a_calibrar": True}}}, "chave desconhecida"),
        ({"orfaos": {}}, "chave desconhecida"),
    ],
)
def test_numero_recusado_fica_o_do_plano(bruto, trecho):
    calibracao = QualityCalibration.from_config(bruto)

    assert any(trecho in problema for problema in calibracao.problems), calibracao.problems
    assert calibracao.microcluster == QualityCalibration().microcluster
    assert calibracao.rare_colors == QualityCalibration().rare_colors


def test_numero_com_fonte_dispensa_a_calibrar():
    calibracao = QualityCalibration.from_config(
        {"blocos_pequenos": {"aviso": {"valor": 0.5, "fonte": "medição X"}}}
    )
    assert calibracao.problems == ()
    assert calibracao.microcluster.warning_ratio == 0.5


# ---------------------------------------------------------------------------
# O efeito na nota
# ---------------------------------------------------------------------------
def test_detalhe_dentro_do_que_as_referencias_mostram_nao_avisa_nem_desconta():
    """3 pontos: 75% de blocos pequenos e 3 cores de 1 px — o que um pacote profissional tem."""
    imagem = _sprite(3)

    plano = PixelValidator().validate(imagem, _spec())
    calibrado = PixelValidator(calibration=_calibrada()).validate(imagem, _spec())

    assert plano.quality.metrics.microcluster_ratio == 0.75
    assert len(plano.quality.metrics.rare_colors) == 3
    assert {"PX-WARN-MICROCLUSTER", "PX-WARN-PALETTE-RARE"} <= _codigos(plano)
    assert {"microcluster", "rare_colors"} <= set(plano.quality.penalties)

    assert not {"PX-WARN-MICROCLUSTER", "PX-WARN-PALETTE-RARE"} & _codigos(calibrado)
    assert not {"microcluster", "rare_colors"} & set(calibrado.quality.penalties)
    assert calibrado.quality.score > plano.quality.score
    assert calibrado.quality.metrics == plano.quality.metrics, "a métrica não muda; só o limiar"


def test_a_quarta_cor_rara_avisa_e_desconta_um_ponto():
    calibrado = PixelValidator(calibration=_calibrada()).validate(_sprite(4), _spec())

    assert "PX-WARN-PALETTE-RARE" in _codigos(calibrado)
    assert calibrado.quality.penalties["rare_colors"] == 1.0
    assert "PX-WARN-MICROCLUSTER" not in _codigos(calibrado), "4 de 5 blocos: 80%, abaixo de 84%"


def test_acima_do_limiar_de_blocos_pequenos_continua_avisando():
    calibrado = PixelValidator(calibration=_calibrada()).validate(_sprite(6), _spec())

    assert calibrado.quality.metrics.microcluster_ratio == pytest.approx(6 / 7, abs=1e-6)
    assert "PX-WARN-MICROCLUSTER" in _codigos(calibrado)
    assert calibrado.quality.penalties["microcluster"] == pytest.approx((6 / 7 - 0.84) * 100, abs=0.01)
    assert calibrado.quality.penalties["rare_colors"] == 3.0, "6 cores raras, 3 de franquia"


def test_ruido_continua_com_aviso():
    gerador = np.random.default_rng(0)
    paleta = gerador.integers(0, 256, (16, 3))
    rgb = paleta[gerador.integers(0, 16, (32, 32))]
    imagem = Image.fromarray(np.dstack([rgb, np.full((32, 32), 255)]).astype(np.uint8), "RGBA")

    calibrado = PixelValidator(calibration=_calibrada()).validate(imagem, _spec(32))

    assert calibrado.quality.metrics.microcluster_ratio > 0.9
    assert "PX-WARN-MICROCLUSTER" in _codigos(calibrado)


@pytest.mark.parametrize(
    ("imagem", "spec"),
    [
        (_sprite(3), _spec()),
        (_sprite(3), _spec(32)),  # dimensão errada
        (_sprite(6), _spec(cores=4)),  # paleta estourada
        (_sprite(3, alpha=128), _spec()),  # alpha não binário
    ],
    ids=["ok", "dimensao", "paleta", "alpha"],
)
def test_a_calibracao_nao_toca_os_hard_checks(imagem, spec):
    plano = PixelValidator().validate(imagem, spec)
    calibrado = PixelValidator(calibration=_calibrada()).validate(imagem, spec)

    assert calibrado.pixel_exact == plano.pixel_exact
    assert calibrado.hard_checks == plano.hard_checks


def test_o_relatorio_grava_a_calibracao_que_valeu():
    plano = PixelValidator().validate(_sprite(3), _spec())
    calibrado = PixelValidator(calibration=_calibrada()).validate(_sprite(3), _spec())

    assert plano.quality.calibration.startswith(PLANO)
    assert calibrado.quality.calibration.startswith("config/quality.yaml")
    assert "0.84" in calibrado.quality.calibration


# ---------------------------------------------------------------------------
# Ligação: a mesma régua no pipeline, no Optimizer e no relatório
# ---------------------------------------------------------------------------
def test_o_container_usa_a_calibracao_de_quality_yaml_no_pipeline_e_no_optimizer(
    container: AppContainer,
):
    assert container.pixel_validator.calibration == _calibrada()
    assert container.optimizer.validator is container.pixel_validator

    pipeline = container.pipelines.get("pixel.character")
    cadeia = pipeline.build_postprocessing_chain(None)
    profile = container.profiles.get("pixel_character_32")
    resultado = cadeia.run(
        ImageBuffer(image=_sprite(3).resize((32, 32), Image.NEAREST)),
        PostProcessContext(profile=profile),
    )

    validacao = json.loads(resultado.artifacts["validation.json"])
    assert validacao["quality"]["calibration"].startswith("config/quality.yaml")
