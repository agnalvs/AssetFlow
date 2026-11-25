"""Seleção de motor: catálogo e governança (plano de motores).

Este arquivo cobre a parte da etapa que **não** é um motor novo: a
infraestrutura que faz um pedido poder nomear o motor e o sistema respeitar
essa escolha. A política do modo "Automático" saiu na Fase A do plano do app
(PLANO_APP_DESENHISTA.md); em ``auto``, quem decide é o roteamento por
capacidade, e o ``tests/test_gerador_unico.py`` cobra o que ele faz no app.

As quatro regras do §25 são o núcleo do que está testado aqui:

    regra 1  o motor escolhido é respeitado, ou o pedido falha dizendo por quê
    regra 2  fallback só em `auto`, ou quando alguém pediu explicitamente
    regra 3  a resposta mostra motor pedido, motor usado e modelo
    regra 4  o validador usa o spec, nunca defaults internos
"""

from __future__ import annotations

import pytest

from assetflow.bootstrap import AppContainer
from assetflow.generation.kernel.exceptions import (
    EngineDisabled,
    EngineNotFound,
    InvalidGenerationRequest,
)
from assetflow.generation.schemas import (
    AssetGenerationRequest,
    AssetOutputOverrides,
    EngineSelector,
    SpecOverrides,
    SpecSource,
)
from tests.conftest import process_next_job, run


def _request(container: AppContainer, **overrides) -> AssetGenerationRequest:
    payload = {
        "project_id": "project_test",
        "profile": "pixel_character_64",
        "prompt": "a small tree",
        "output": AssetOutputOverrides(variations=1),
    }
    payload.update(overrides)
    return AssetGenerationRequest.model_validate(payload)


# ---------------------------------------------------------------------------
# Catálogo (plano de motores §6)
# ---------------------------------------------------------------------------
def test_catalog_describes_every_registered_engine(container: AppContainer):
    """Toda gaveta registrada aparece no catálogo, com a vitrine dela."""
    entries = run(container.service.engine_catalog(include_hidden=True))
    ids = {entry.engine_id for entry in entries}

    assert ids == set(container.registry.ids())
    for entry in entries:
        assert entry.display_name, f"{entry.engine_id} sem nome de exibição"
        assert entry.capabilities, f"{entry.engine_id} sem capacidade no catálogo"


def test_catalog_hides_the_reference_engines_from_the_shop_window(
    container: AppContainer,
):
    """As gavetas mock existem, resolvem e não são oferecidas.

    Elas continuam na estante — o roteamento por capacidade as usa — mas
    oferecer "Mock Image Engine" a quem quer um sprite é ruído.
    """
    visible = {entry.engine_id for entry in run(container.service.engine_catalog())}
    hidden = {
        entry.engine_id
        for entry in run(container.service.engine_catalog(include_hidden=True))
    }

    assert "mock-image-v1" in hidden
    assert "mock-image-v1" not in visible


def test_catalog_says_why_an_engine_cannot_be_used(container: AppContainer):
    """Motor indisponível traz o motivo em português, não um código."""
    container.registry.disable("mock-image-v1")
    entries = run(container.service.engine_catalog(include_hidden=True))
    entry = next(item for item in entries if item.engine_id == "mock-image-v1")

    assert entry.available is False
    assert entry.status == "disabled"
    assert entry.unavailable_reason
    assert "desabilitado" in entry.unavailable_reason


def test_catalog_filters_by_capability(container: AppContainer):
    """Cada modo da tela vê só os motores que atendem aquele modo."""
    entries = run(
        container.service.engine_catalog(
            capability="character.2d", include_hidden=True
        )
    )
    for entry in entries:
        assert "character.2d" in entry.capabilities


# ---------------------------------------------------------------------------
# O campo `engine` no Final Resolved Spec (plano de motores §5)
# ---------------------------------------------------------------------------
def test_explicit_automatic_without_a_suggestion_is_nobody_choosing(
    container: AppContainer,
):
    spec = container.service.resolve_spec(
        _request(container, engine=EngineSelector(mode="auto"))
    )
    assert spec.engine.engine_id is None
    assert spec.source_of("engine") is SpecSource.GLOBAL_DEFAULT


def test_auto_leaves_the_engine_to_the_routing(container: AppContainer):
    """Em `auto`, o spec não inventa motor: o roteamento por capacidade
    decide, e o spec registra honestamente que ninguém escolheu."""
    spec = container.service.resolve_spec(_request(container))

    assert spec.engine.selection_mode == "auto"
    assert spec.engine.engine_id is None
    assert spec.source_of("engine") is SpecSource.GLOBAL_DEFAULT


def test_manual_selection_wins_and_is_recorded_as_a_user_choice(
    container: AppContainer,
):
    spec = container.service.resolve_spec(
        _request(
            container,
            engine=EngineSelector(mode="manual", engine_id="mock-pixel-alt-v1"),
        )
    )

    assert spec.engine.selection_mode == "manual"
    assert spec.engine.engine_id == "mock-pixel-alt-v1"
    assert spec.source_of("engine") is SpecSource.UI_SELECTION


def test_manual_override_beats_the_selector(container: AppContainer):
    """Editar o motor no JSON final ganha do dropdown (precedência nível 1)."""
    spec = container.service.resolve_spec(
        _request(
            container,
            engine=EngineSelector(mode="manual", engine_id="mock-image-v1"),
            spec_overrides=SpecOverrides(engine_id="mock-pixel-alt-v1"),
        )
    )

    assert spec.engine.engine_id == "mock-pixel-alt-v1"
    assert spec.source_of("engine") is SpecSource.MANUAL_OVERRIDE


def test_engine_changes_the_spec_hash_but_the_reason_does_not(
    container: AppContainer,
):
    """Dois specs iguais em tudo menos no motor são specs diferentes.

    O motivo da escolha, não: ele descreve **como** se chegou ao motor, e dois
    pedidos que resultam no mesmo motor produzem o mesmo asset.
    """
    a = container.service.resolve_spec(
        _request(container, engine=EngineSelector(mode="manual", engine_id="mock-image-v1"))
    )
    b = container.service.resolve_spec(
        _request(
            container,
            engine=EngineSelector(mode="manual", engine_id="mock-pixel-alt-v1"),
        )
    )
    assert a.spec_hash != b.spec_hash

    same = a.model_copy(
        update={"engine": a.engine.model_copy(update={"reason": "outro motivo"})}
    ).with_identity()
    assert same.spec_hash == a.spec_hash


# ---------------------------------------------------------------------------
# Governança (plano de motores §25)
# ---------------------------------------------------------------------------
def test_regra1_unknown_engine_fails_instead_of_being_replaced(
    container: AppContainer,
):
    """Regra 1: motor inexistente vira erro, nunca outro motor em silêncio."""
    job = run(
        container.service.submit(
            _request(
                container,
                engine=EngineSelector(mode="manual", engine_id="motor-que-nao-existe"),
            )
        )
    )
    run(process_next_job(container))
    finished = run(container.service.get_job(job.id))

    assert finished.status.value == "failed"
    assert finished.error is not None
    assert finished.error.code == "engine_not_found"
    assert "não existe" in finished.error.message


def test_regra1_disabled_engine_fails_with_an_actionable_message(
    container: AppContainer,
):
    container.registry.disable("mock-pixel-alt-v1")
    job = run(
        container.service.submit(
            _request(
                container,
                engine=EngineSelector(mode="manual", engine_id="mock-pixel-alt-v1"),
            )
        )
    )
    run(process_next_job(container))
    finished = run(container.service.get_job(job.id))

    assert finished.status.value == "failed"
    assert finished.error.code == "engine_disabled"
    # A mensagem precisa dizer o que fazer, não só o que houve.
    assert "escolha outro" in finished.error.message.lower()


def test_regra2_manual_selection_turns_fallback_off_by_default(
    container: AppContainer,
):
    """Regra 2: em `manual`, o padrão é **não** trocar de motor."""
    manual = container.service.resolve_spec(
        _request(
            container, engine=EngineSelector(mode="manual", engine_id="mock-image-v1")
        )
    )
    assert manual.engine.allow_fallback is False

    auto = container.service.resolve_spec(_request(container))
    assert auto.engine.allow_fallback is True


def test_regra2_fallback_can_be_asked_for_explicitly(container: AppContainer):
    """Quem quiser o contrário escreve — e aí a troca é decisão de quem pediu."""
    spec = container.service.resolve_spec(
        _request(
            container,
            engine=EngineSelector(
                mode="manual", engine_id="mock-image-v1", allow_fallback=True
            ),
        )
    )
    assert spec.engine.allow_fallback is True


def test_regra3_the_job_reports_requested_and_used_engine(container: AppContainer):
    """Regra 3: a resposta mostra o pedido, o usado e o modelo."""
    from assetflow.api.schemas import JobResponse

    job = run(
        container.service.submit(
            _request(
                container, engine=EngineSelector(mode="manual", engine_id="mock-image-v1")
            )
        )
    )
    run(process_next_job(container))
    finished = run(container.service.get_job(job.id))

    view = JobResponse.from_job(finished).engine_selection
    assert view.mode == "manual"
    assert view.requested_engine_id == "mock-image-v1"
    assert view.resolved_engine_id == "mock-image-v1"
    assert view.resolved_engine_version
    assert view.honored is True
    assert view.fallback_used is False


def test_manual_selection_without_an_id_is_refused_at_the_spec(
    container: AppContainer,
):
    """`engine_mode: manual` sem id é pedido incompleto, não padrão silencioso."""
    with pytest.raises(InvalidGenerationRequest):
        container.service.resolve_spec(
            _request(container, spec_overrides=SpecOverrides(engine_mode="manual"))
        )
