"""Registros antigos do histórico continuam legíveis.

O histórico (``generations.jsonl``) foi escrito por todas as versões do
AssetFlow, e o modelo do registro mudou desde então. A era do STRATEGY deixou
campos de topo que o modelo não tem mais (``strategy``, ``requested_strategy``,
``agent_id``, ``agent_version``, ``planner_provider``, ``planner_model``), e o
modelo é estrito: com ``extra="forbid"``, cada uma dessas linhas falhava na
leitura, e o leitor a pulava em silêncio. O asset sumia para ``ver_asset`` e
para ``desenhar(base=...)``, sem erro nenhum.

A Fase A do plano do app tirou ainda profiles (Studio e Raw) e gavetas. Isso
não quebra a leitura — o registro guarda o id do profile e da gaveta como
texto, sem resolvê-los —, e um teste aqui confere.

O leitor passou a ignorar campo de topo que o modelo não conhece
(``GenerationRecord.do_historico``); os dados no arquivo não mudam. Os
registros abaixo são escritos à mão, no formato antigo: nada vem de
``backend/data/``.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pydantic import ValidationError

from assetflow.bootstrap import AppContainer
from assetflow.mcp.servico import MOTOR, ServicoDesenhista
from assetflow.storage import JsonLinesGenerationRecordRepository
from assetflow.storage.records import GenerationRecord
from tests.conftest import BACKEND_ROOT, run

POCAO = (
    BACKEND_ROOT / "assetflow" / "generation" / "engines" / "desenhista" / "exemplos" / "pocao_16x16.json"
)

#: Os campos de topo da era do STRATEGY, como uma linha antiga os trazia.
CAMPOS_DA_ERA_STRATEGY = {
    "strategy": "pixel_agent",
    "requested_strategy": "auto",
    "agent_id": "pixel-agent-v1",
    "agent_version": "0.3.0",
    "planner_provider": "none",
    "planner_model": None,
}


def _registro_antigo(**campos: Any) -> dict[str, Any]:
    """Uma linha do histórico no formato antigo, de um desenho da desenhista."""
    base: dict[str, Any] = {
        "id": "rec_antigo00001",
        "created_at": "2026-08-15T12:00:00+00:00",
        "job_id": "job_antigo00001",
        "project_id": "legado",
        "asset_id": "asset_antigo00001",
        "profile_id": "pixel_prop_64",
        "pipeline_id": "pixel.character",
        "capability": "text_to_image.pixel",
        "engine_id": MOTOR,
        "engine_selection_mode": "manual",
        "requested_engine_id": MOTOR,
        "user_prompt": "poção vermelha 16x16",
        "engine_options": {MOTOR: {"receita": json.loads(POCAO.read_text(encoding="utf-8"))}},
        "outputs": [
            {
                "index": 0,
                "uri": "assetflow-local://projects/legado/jobs/job_antigo00001/000.png",
                "width": 16,
                "height": 16,
                "logical_width": 16,
                "logical_height": 16,
                "status": "approved",
            }
        ],
        **CAMPOS_DA_ERA_STRATEGY,
    }
    base.update(campos)
    return base


#: Um registro de um motor e de um profile que não existem mais.
REGISTRO_DE_MOTOR_REMOVIDO = _registro_antigo(
    id="rec_antigo00002",
    job_id="job_antigo00002",
    asset_id="asset_antigo00002",
    profile_id="studio_character",
    pipeline_id="studio.character",
    capability="text_to_image.general",
    engine_id="diffusers-sdxl-v1",
    engine_selection_mode="auto",
    requested_engine_id=None,
    engine_options={},
    outputs=[
        {
            "index": 0,
            "uri": "assetflow-local://projects/legado/jobs/job_antigo00002/000.png",
            "width": 64,
            "height": 64,
        }
    ],
)


def _gravar_historico(caminho: Path, *registros: dict[str, Any]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        for registro in registros:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


@pytest.fixture
def servico(container: AppContainer) -> ServicoDesenhista:
    """O MCP sobre um histórico que já tem as duas linhas antigas."""
    settings = container.settings
    _gravar_historico(settings.history_path, _registro_antigo(), REGISTRO_DE_MOTOR_REMOVIDO)
    # O PNG de cada registro antigo, onde a URI dele aponta.
    for job, lado in (("job_antigo00001", 16), ("job_antigo00002", 64)):
        png = settings.storage_root / "projects" / "legado" / "jobs" / job / "000.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (lado, lado), (0xB0, 0x3A, 0x2E, 255)).save(png)
    container.registry.enable(MOTOR)
    return ServicoDesenhista(container)


def test_o_modelo_estrito_recusa_a_linha_antiga():
    """É o que fazia a linha sumir: gravar continua estrito, de propósito."""
    with pytest.raises(ValidationError, match="strategy"):
        GenerationRecord.model_validate(_registro_antigo())


def test_o_leitor_tolera_os_campos_que_sairam(tmp_path: Path):
    caminho = tmp_path / "generations.jsonl"
    _gravar_historico(caminho, _registro_antigo(), REGISTRO_DE_MOTOR_REMOVIDO)

    registros = {r.asset_id: r for r in run(JsonLinesGenerationRecordRepository(caminho).list())}

    assert set(registros) == {"asset_antigo00001", "asset_antigo00002"}
    antigo = registros["asset_antigo00001"]
    assert antigo.engine_id == MOTOR
    assert antigo.engine_options[MOTOR]["receita"]["grade"] == [16, 16]
    # Profile e gaveta que saíram são só texto no registro.
    removido = registros["asset_antigo00002"]
    assert (removido.profile_id, removido.engine_id) == ("studio_character", "diffusers-sdxl-v1")


def test_ler_nao_muda_o_arquivo(tmp_path: Path):
    caminho = tmp_path / "generations.jsonl"
    _gravar_historico(caminho, _registro_antigo(), REGISTRO_DE_MOTOR_REMOVIDO)
    antes = caminho.read_bytes()

    run(JsonLinesGenerationRecordRepository(caminho).list(limit=1_000_000))

    assert caminho.read_bytes() == antes


def test_ver_asset_num_registro_antigo(servico: ServicoDesenhista):
    png, legenda = run(servico.ver("asset_antigo00001"))

    assert legenda.startswith("asset_antigo00001 · 16×16 · ampliado 24×")
    assert Image.open(io.BytesIO(png)).size[0] > 16


def test_remendo_sobre_registro_antigo(servico: ServicoDesenhista):
    """``desenhar(base=...)`` acha a receita e o profile no registro antigo."""
    laudo = run(servico.desenhar(base="asset_antigo00001", receita={"paleta": {"r": "#2e8b57"}}))
    linhas = laudo.splitlines()

    assert linhas[0] == "remendo de asset_antigo00001: paleta r"
    assert linhas[1].startswith("APROVADO · asset_")
    assert linhas[1].endswith(" · poção vermelha 16x16")


def test_ver_asset_de_gaveta_e_profile_removidos(servico: ServicoDesenhista):
    """Antes, a linha era pulada e a resposta era "não há asset no histórico"."""
    _, legenda = run(servico.ver("asset_antigo00002"))

    assert legenda.startswith("asset_antigo00002 · 64×64 · ampliado 6×")
