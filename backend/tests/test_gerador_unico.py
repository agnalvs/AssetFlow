"""O app tem um gerador só: a desenhista (Fase A do plano do app).

Antes desta fase, um mock podia gerar no lugar da desenhista por três portas:
o modo "Automático" preferia a desenhista e, quando ela recusava um pedido
sem receita, o fallback chamava o mock; o ``capabilities.yaml`` listava os
mocks nas rotas Pixel; e ``allow_unlisted_engines`` punha na cadeia qualquer
gaveta registrada que declarasse a capacidade. Fora de produção, os mocks
eram registrados.

As três foram fechadas, e cada uma tem teste aqui:

1. **registro** — os mocks só são registrados em ``AppEnvironment.TEST``, que
   nenhuma variável de ambiente liga;
2. **rotas** — as rotas Pixel listam só a desenhista, e motor fora da lista
   não entra na cadeia;
3. **fallback** — desligado na configuração.

Este arquivo **não** usa a fixture ``container`` do ``conftest``: ela monta o
ambiente de testes, com os mocks e o roteamento dos testes de mecanismo. Aqui
o container é montado como o app o monta, com a configuração versionada.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from assetflow.api.schemas import JobResponse
from assetflow.bootstrap import AppContainer, build_container
from assetflow.generation.engines.desenhista.engine import MENSAGEM_SEM_RECEITA
from assetflow.generation.kernel.exceptions import EngineNotFound, NoEngineAvailable
from assetflow.generation.schemas import AssetGenerationRequest, AssetOutputOverrides
from assetflow.mcp.servico import ServicoDesenhista
from assetflow.settings import AppEnvironment, load_settings
from tests.conftest import BACKEND_ROOT, process_next_job, run

DESENHISTA = "desenhista-v1"
ROTAS_PIXEL = ("text_to_image.pixel", "character.pixel", "prop.pixel")
POCAO = (
    BACKEND_ROOT / "assetflow" / "generation" / "engines" / "desenhista" / "exemplos" / "pocao_16x16.json"
)


def _app(tmp_path: Path, ambiente: AppEnvironment) -> AppContainer:
    """O container como o app o monta, com dados isolados em ``tmp_path``."""
    settings = load_settings(base_dir=BACKEND_ROOT, data_dir=tmp_path)
    settings.app_env = ambiente
    settings.worker.embedded = False
    settings.worker.retry_base_delay_s = 0.0
    return build_container(settings)


@pytest.fixture
def app(tmp_path: Path) -> AppContainer:
    return _app(tmp_path, AppEnvironment.DEVELOPMENT)


# ---------------------------------------------------------------------------
# Trava 1: registro
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ambiente", [AppEnvironment.DEVELOPMENT, AppEnvironment.PRODUCTION])
def test_o_app_registra_so_a_desenhista(tmp_path: Path, ambiente: AppEnvironment):
    """Em desenvolvimento e em produção, os mocks não existem para o app."""
    app = _app(tmp_path, ambiente)

    assert app.registry.ids() == (DESENHISTA,)


def test_so_o_ambiente_de_testes_registra_os_mocks(tmp_path: Path):
    """É o ambiente da fixture ``container`` — e só ele."""
    testes = _app(tmp_path, AppEnvironment.TEST)

    assert {"mock-image-v1", "mock-pixel-alt-v1"} <= set(testes.registry.ids())


@pytest.mark.parametrize("valor", ["test", "TEST", "testes", "qualquer"])
def test_o_ambiente_de_testes_nao_vem_de_variavel(monkeypatch: pytest.MonkeyPatch, valor: str):
    """``ASSETFLOW_APP_ENV=test`` esquecido no terminal não liga os mocks."""
    monkeypatch.setenv("ASSETFLOW_APP_ENV", valor)
    settings = load_settings(base_dir=BACKEND_ROOT)

    assert settings.app_env is AppEnvironment.DEVELOPMENT
    assert settings.show_mock_engines is False


def test_producao_continua_sendo_aceita_pela_variavel(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ASSETFLOW_APP_ENV", "production")
    assert load_settings(base_dir=BACKEND_ROOT).app_env is AppEnvironment.PRODUCTION


def test_um_mock_nao_pode_ser_ligado_pela_api(app: AppContainer):
    """As rotas de motor ficam para diagnóstico: habilitar uma gaveta que não
    foi registrada é "não existe", e não um mock voltando pela porta lateral."""
    with pytest.raises(EngineNotFound):
        app.service.enable_engine("mock-image-v1")


# ---------------------------------------------------------------------------
# Travas 2 e 3: rotas e fallback
# ---------------------------------------------------------------------------
def test_a_configuracao_versionada_nao_cita_mock_nem_liga_fallback():
    """O ``capabilities.yaml`` do repositório, lido cru."""
    with (BACKEND_ROOT / "config" / "capabilities.yaml").open(encoding="utf-8") as arquivo:
        config = yaml.safe_load(arquivo)

    motores = {motor for rota in config["routing"].values() for motor in rota["engines"]}
    assert motores == {DESENHISTA}
    assert set(config["routing"]) == set(ROTAS_PIXEL)
    assert config["fallback"]["enabled"] is False
    assert config["allow_unlisted_engines"] is False


@pytest.mark.parametrize("capacidade", ROTAS_PIXEL)
def test_as_rotas_pixel_levam_so_a_desenhista(app: AppContainer, capacidade: str):
    resolucao = run(app.resolver.resolve(capacidade))

    assert resolucao.engine_ids == (DESENHISTA,)
    assert resolucao.fallback_allowed is False
    assert [candidato.engine_id for candidato in resolucao.chain()] == [DESENHISTA]


def test_capacidade_que_nao_e_pixel_nao_tem_motor(app: AppContainer):
    with pytest.raises(NoEngineAvailable):
        run(app.resolver.resolve("text_to_image.general"))


def test_pedido_sem_receita_falha_sem_tentar_outra_gaveta(app: AppContainer):
    """O caso que a Fase A existe para fechar: em "Automático" e sem receita,
    a desenhista recusa — e antes o fallback entregava o desenho do mock."""
    pedido = AssetGenerationRequest(
        project_id="p",
        profile="pixel_character_32",
        prompt="cavaleiro de armadura",
        output=AssetOutputOverrides(variations=1),
    )
    job = run(app.service.submit(pedido))
    run(process_next_job(app))
    job = run(app.service.get_job(job.id))

    # Com um mock na cadeia, o job terminaria "completed", com o desenho dele.
    assert job.status.value == "failed"
    assert job.error.message == MENSAGEM_SEM_RECEITA
    assert job.asset is None
    assert JobResponse.from_job(job).engine_selection.fallback_used is False


# ---------------------------------------------------------------------------
# O caminho do desenhista continua igual
# ---------------------------------------------------------------------------
def test_um_desenho_pelo_mcp_continua_aprovado(app: AppContainer):
    """O MCP pede a desenhista pelo nome, sem fallback — como antes da Fase A."""
    receita = json.loads(POCAO.read_text(encoding="utf-8"))
    laudo = run(
        ServicoDesenhista(app).desenhar(
            pedido="poção vermelha 16x16", receita=receita, perfil="pixel_prop_64"
        )
    )

    assert laudo.splitlines()[0].startswith("APROVADO · asset_")
    assert "Pixel Exact ✓" in laudo
