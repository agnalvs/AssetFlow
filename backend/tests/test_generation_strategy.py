"""A separação entre método, motor e agente (plano de correção §44 a §46, §49).

Os cinco testes obrigatórios do §44, os dois de regressão do §45 e §46, e a
Definition of Done do §49 — cada um nomeado pela seção que o exige.

A regra que todos protegem, escrita no §51::

    STRATEGY   = como o asset será criado
    ENGINE     = qual tecnologia/modelo gera uma imagem
    AGENT      = sistema que toma decisões e usa ferramentas

Misturar os três foi o que pôs "Texel-style Agent" no mesmo seletor que "FLUX
Pixel". Estes testes existem para que isso não volte a acontecer sem que o
build reclame.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from assetflow.api import create_app
from assetflow.bootstrap import AppContainer, build_container
from assetflow.generation.kernel.exceptions import InvalidGenerationRequest
from assetflow.generation.pixel_agent import AGENT_ID
from assetflow.generation.pixel_agent.strategy import PixelAgentStrategy
from assetflow.generation.schemas import (
    AssetGenerationRequest,
    AssetOutputOverrides,
    ConceptReferenceSelection,
    EngineSelector,
    GenerationStrategySelection,
    GenerationStrategyType,
    PixelAgentSelection,
    SpecOverrides,
    SpecSource,
)
from assetflow.generation.strategies import (
    GenerationStrategyRegistry,
    ModelGenerationStrategy,
)
from assetflow.settings import AppEnvironment, load_settings
from tests.conftest import BACKEND_ROOT, process_next_job, run


def _request(container: AppContainer, **overrides) -> AssetGenerationRequest:
    payload = {
        "project_id": "project_test",
        "profile": "pixel_character_64",
        "prompt": "uma arvore pequena",
        "asset_type": "prop",
        "output": AssetOutputOverrides(
            variations=1, logical_width=32, logical_height=32, palette_size=16
        ),
    }
    payload.update(overrides)
    return AssetGenerationRequest.model_validate(payload)


def _spec(container: AppContainer, **overrides):
    return container.service.resolve_spec(_request(container, **overrides))


# ---------------------------------------------------------------------------
# §44 — os cinco testes obrigatórios
# ---------------------------------------------------------------------------
def test_44_1_choosing_a_model_and_an_engine(container: AppContainer):
    """Teste 1: "Modelo de imagem" + FLUX Pixel -> strategy=model, engine=flux."""
    container.registry.enable("flux-pixel-v1")
    spec = _spec(
        container,
        generation_strategy=GenerationStrategySelection(mode="model"),
        engine=EngineSelector(mode="manual", engine_id="flux-pixel-v1"),
    )

    assert spec.strategy.mode is GenerationStrategyType.MODEL
    assert spec.engine.engine_id == "flux-pixel-v1"
    assert spec.uses_engine is True


def test_44_2_choosing_the_pixel_agent_leaves_no_engine(container: AppContainer):
    """Teste 2: "Agente Pixel" -> strategy=pixel_agent, engine=null.

    O `null` é o ponto do plano inteiro: um asset desenhado pelo agente não
    tem motor, e o sistema precisa saber dizer isso em vez de preencher o
    campo com algo para satisfazer o formato.
    """
    spec = _spec(
        container, generation_strategy=GenerationStrategySelection(mode="pixel_agent")
    )

    assert spec.strategy.mode is GenerationStrategyType.PIXEL_AGENT
    assert spec.engine.engine_id is None
    assert spec.uses_engine is False


def test_44_3_the_agent_may_use_an_engine_as_concept_reference(
    container: AppContainer,
):
    """Teste 3: referência conceitual é a exceção do §38 (§26, §27 e §39).

    Um motor pode aparecer em um job de agente — como *supporting engine*,
    nunca como gerador. Por isso ele mora em um campo próprio: no mesmo campo
    do motor, "me ajudou a pensar" e "gerou isto" ficariam indistinguíveis.
    """
    spec = _spec(
        container,
        generation_strategy=GenerationStrategySelection(mode="pixel_agent"),
        concept_reference=ConceptReferenceSelection(
            enabled=True, engine_id="flux-pixel-v1"
        ),
    )

    assert spec.strategy.mode is GenerationStrategyType.PIXEL_AGENT
    assert spec.engine.engine_id is None, "a referência não é o motor do asset"
    assert spec.concept_reference.enabled is True
    assert spec.concept_reference.engine_id == "flux-pixel-v1"


def test_44_4_auto_resolves_a_small_sprite_to_a_supported_strategy(
    container: AppContainer,
):
    """Teste 4: `auto` com tree 16×16 resolve para uma estratégia suportada."""
    spec = _spec(
        container,
        output=AssetOutputOverrides(
            variations=1, logical_width=16, logical_height=16, palette_size=8
        ),
    )

    assert spec.strategy.requested is GenerationStrategyType.AUTO
    assert spec.strategy.mode in {
        GenerationStrategyType.MODEL,
        GenerationStrategyType.PIXEL_AGENT,
    }
    assert spec.strategy.mode in container.strategies
    # §41: a escolha automática nunca é muda.
    assert spec.strategy.reason


def test_44_5_mock_engines_are_absent_in_production():
    """Teste 5: em produção, as gavetas de referência não existem (§6 e §36).

    Não é "escondidas": elas não são registradas. Uma gaveta registrada
    continua resolvível por capacidade, e "invisível mas usável" deixaria um
    job de produção cair em um mock sem ninguém ver.
    """
    settings = load_settings(base_dir=BACKEND_ROOT)
    settings.app_env = AppEnvironment.PRODUCTION
    settings.worker.embedded = False

    production = build_container(settings)
    assert "mock-image-v1" not in production.registry.ids()
    assert "mock-pixel-alt-v1" not in production.registry.ids()
    # E os motores de verdade continuam lá.
    assert "flux-pixel-v1" in production.registry.ids()


def test_mock_engines_are_present_in_development(container: AppContainer):
    """O outro lado da regra: em desenvolvimento eles existem."""
    assert "mock-image-v1" in container.registry.ids()
    assert container.settings.show_mock_engines is True


# ---------------------------------------------------------------------------
# §45 e §46 — regressão da interface e do registro
# ---------------------------------------------------------------------------
def test_45_the_engine_selector_never_lists_the_pixel_agent(
    container: AppContainer,
):
    """§45: o seletor de MOTOR nunca pode listar o AssetFlow Pixel Agent."""
    container.settings.worker.embedded = True
    with TestClient(create_app(container=container)) as client:
        catalog = client.get("/api/generation/engines/catalog").json()

    nomes = {item["display_name"] for item in catalog["items"]}
    ids = {item["engine_id"] for item in catalog["items"]}

    assert "AssetFlow Pixel Agent" not in nomes
    assert "Texel-style Agent" not in nomes
    assert not any("texel" in item or "agent" in item for item in ids)


def test_46_the_agent_is_a_strategy_and_not_an_engine(container: AppContainer):
    """§46: fora do EngineRegistry, dentro do GenerationStrategyRegistry."""
    assert "texel-style-v1" not in container.registry.ids()
    assert AGENT_ID not in container.registry.ids()

    assert "pixel_agent" in container.strategies
    assert GenerationStrategyType.PIXEL_AGENT in container.strategies


def test_the_engine_registry_holds_only_real_engines(container: AppContainer):
    """§36: motores de verdade, e nada que seja outra categoria de coisa."""
    for record in container.registry.list():
        assert record.manifest.catalog.family.value != "agentic", (
            f"'{record.id}' é um agente registrado como motor"
        )


# ---------------------------------------------------------------------------
# §37 e §38 — tipos e combinações inválidas
# ---------------------------------------------------------------------------
def test_38_asking_for_an_engine_with_the_agent_is_refused(
    container: AppContainer,
):
    """§38: agente + motor principal é pedido contraditório, não preferência.

    Aceitar em silêncio produziria o pior resultado possível: o job roda,
    ignora o motor escolhido, e ninguém descobre.
    """
    with pytest.raises(InvalidGenerationRequest) as excinfo:
        _spec(
            container,
            generation_strategy=GenerationStrategySelection(mode="pixel_agent"),
            engine=EngineSelector(mode="manual", engine_id="mock-image-v1"),
        )
    assert "não usa motor" in str(excinfo.value)


def test_the_registry_refuses_to_register_auto():
    """`auto` é uma pergunta, não uma resposta (§35)."""

    class Auto(ModelGenerationStrategy):
        strategy_id = GenerationStrategyType.AUTO

    with pytest.raises(ValueError):
        GenerationStrategyRegistry([Auto()])


def test_the_agent_strategy_declines_art_without_a_grid(container: AppContainer):
    """Um agente que desenha pixel a pixel precisa saber quantos pixels são."""
    strategy = PixelAgentStrategy()
    pixel = _spec(container)
    studio = container.service.resolve_spec(
        _request(container, profile="studio_character", output=AssetOutputOverrides())
    )

    assert strategy.supports(pixel) is True
    assert strategy.supports(studio) is False


# ---------------------------------------------------------------------------
# §41 — a escolha automática fica registrada
# ---------------------------------------------------------------------------
def test_41_the_job_records_requested_and_resolved_strategy(
    container: AppContainer,
):
    job = run(
        container.service.submit(
            _request(
                container,
                generation_strategy=GenerationStrategySelection(mode="pixel_agent"),
            )
        )
    )
    run(process_next_job(container))
    finished = run(container.service.get_job(job.id))

    from assetflow.api.schemas import JobResponse

    view = JobResponse.from_job(finished).engine_selection
    assert view.requested_strategy is GenerationStrategyType.PIXEL_AGENT
    assert view.resolved_strategy is GenerationStrategyType.PIXEL_AGENT
    assert view.resolved_engine_id is None
    assert view.agent is not None and view.agent.id == AGENT_ID


def test_41_auto_records_what_it_chose_and_why(container: AppContainer):
    spec = _spec(container)

    assert spec.strategy.requested is GenerationStrategyType.AUTO
    assert spec.strategy.was_automatic is True
    assert spec.strategy.reason
    assert spec.source_of("strategy") is SpecSource.INFERENCE


def test_the_manual_override_beats_the_selector_for_the_method(
    container: AppContainer,
):
    """Precedência de sempre: o JSON corrigido à mão ganha do dropdown."""
    spec = _spec(
        container,
        generation_strategy=GenerationStrategySelection(mode="model"),
        spec_overrides=SpecOverrides(strategy="pixel_agent"),
    )

    assert spec.strategy.mode is GenerationStrategyType.PIXEL_AGENT
    assert spec.source_of("strategy") is SpecSource.MANUAL_OVERRIDE


# ---------------------------------------------------------------------------
# §10 e §25 — configuração do agente
# ---------------------------------------------------------------------------
def test_the_agent_configuration_reaches_the_spec(container: AppContainer):
    spec = _spec(
        container,
        generation_strategy=GenerationStrategySelection(mode="pixel_agent"),
        pixel_agent=PixelAgentSelection(
            quality_mode="detailed", max_iterations=3, auto_review=False
        ),
    )

    assert spec.pixel_agent.quality_mode.value == "detailed"
    assert spec.pixel_agent.max_iterations == 3
    assert spec.pixel_agent.auto_review is False


def test_auto_quality_follows_the_canvas_size():
    """Grades pequenas convergem rápido; gastar seis voltas nelas é só tempo."""
    from assetflow.generation.pixel_agent.strategy import _resolve_quality
    from assetflow.generation.pixel_agent.session import QualityMode

    assert _resolve_quality("auto", (16, 16)) is QualityMode.FAST
    assert _resolve_quality("auto", (32, 32)) is QualityMode.BALANCED
    assert _resolve_quality("auto", (128, 128)) is QualityMode.DETAILED
    # Um modo explícito ganha do tamanho.
    assert _resolve_quality("fast", (128, 128)) is QualityMode.FAST


# ---------------------------------------------------------------------------
# §49 — Definition of Done da arquitetura
# ---------------------------------------------------------------------------
def test_49_the_api_offers_methods_before_engines(container: AppContainer):
    """A interface tem "Método de criação", e o motor só aparece em `model`."""
    container.settings.worker.embedded = True
    with TestClient(create_app(container=container)) as client:
        payload = client.get("/api/generation/strategies").json()

    by_id = {item["id"]: item for item in payload["items"]}
    assert set(by_id) == {"auto", "model", "pixel_agent"}
    assert by_id["auto"]["display_name"] == "Automático"
    assert by_id["model"]["display_name"] == "Modelo de imagem"
    assert by_id["pixel_agent"]["display_name"] == "Agente Pixel"

    # §5: quem decide qual seletor aparece é o backend.
    assert by_id["model"]["selects_engine"] is True
    assert by_id["model"]["selects_agent"] is False
    assert by_id["pixel_agent"]["selects_engine"] is False
    assert by_id["pixel_agent"]["selects_agent"] is True
    assert by_id["auto"]["selects_engine"] is False

    # §33: o nome na interface é o do AssetFlow, não o do projeto que inspirou.
    assert payload["agents"][0]["display_name"] == "AssetFlow Pixel Agent"


def test_50_the_pixel_agent_delivers_a_validated_asset(container: AppContainer):
    """§50: prompt tree, 32×32, 16 cores, método Agente Pixel -> asset válido."""
    job = run(
        container.service.submit(
            _request(
                container,
                prompt="tree",
                generation_strategy=GenerationStrategySelection(mode="pixel_agent"),
            )
        )
    )
    run(process_next_job(container))
    finished = run(container.service.get_job(job.id))

    assert finished.status.value == "completed", finished.error
    variant = finished.asset.variants[0]
    assert (variant.logical_width, variant.logical_height) == (32, 32)
    assert variant.color_count is not None and variant.color_count <= 16
    # Passou pelo PixelValidator como qualquer outro método (§30).
    assert variant.pixel_exact is True
    assert variant.quality_score is not None
    assert finished.asset.agent is not None
    assert finished.asset.engine is None


# ---------------------------------------------------------------------------
# O agente não recebe o que não sabe desenhar
# ---------------------------------------------------------------------------
def test_auto_does_not_send_an_unknown_subject_to_the_agent(
    container: AppContainer,
):
    """A regra que faltava, e que entregou uma bolha como casa.

    O §40 escolhia o método por tamanho, tipo e paleta — e nada disso diz se o
    agente **sabe desenhar aquilo**. Um prop de 32×32 chamado "objeto
    misterioso" casava com a regra do sprite pequeno e ia para o agente, que
    caía na forma genérica.
    """
    conhecido = _spec(container, prompt="uma arvore pequena")
    desconhecido = _spec(container, prompt="objeto misterioso indescritivel")

    assert conhecido.strategy.mode is GenerationStrategyType.PIXEL_AGENT
    assert desconhecido.strategy.mode is GenerationStrategyType.MODEL


def test_a_house_is_a_subject_the_agent_knows(container: AppContainer):
    """E o caso que originou tudo continua indo para o agente — agora com
    uma receita de verdade por trás."""
    spec = _spec(container, prompt="small medieval house")
    assert spec.strategy.mode is GenerationStrategyType.PIXEL_AGENT


def test_manual_choice_still_reaches_the_agent_with_a_warning(
    container: AppContainer,
):
    """Escolha manual é respeitada — e explicada (§25, regra 1).

    Quem escolheu "Agente Pixel" recebe o agente mesmo para um sujeito fora do
    vocabulário. O que muda é que o job passa a **dizer** isso, em vez de
    entregar uma forma genérica sem explicação.
    """
    job = run(
        container.service.submit(
            _request(
                container,
                prompt="objeto misterioso indescritivel",
                generation_strategy=GenerationStrategySelection(mode="pixel_agent"),
            )
        )
    )
    run(process_next_job(container))
    finished = run(container.service.get_job(job.id))

    assert finished.status.value == "completed"
    assert finished.asset.agent is not None
    aviso = " ".join(finished.warnings)
    assert "não sabe desenhar" in aviso
    assert "Modelo de imagem" in aviso, "o aviso precisa dizer o que fazer"


def test_a_known_subject_generates_without_warnings(container: AppContainer):
    job = run(
        container.service.submit(
            _request(
                container,
                prompt="uma arvore",
                generation_strategy=GenerationStrategySelection(mode="pixel_agent"),
            )
        )
    )
    run(process_next_job(container))
    finished = run(container.service.get_job(job.id))

    assert not [w for w in finished.warnings if "não sabe desenhar" in w]
