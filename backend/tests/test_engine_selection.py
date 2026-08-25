"""Seleção de motor: catálogo, política e governança (plano de motores).

Este arquivo cobre a parte da etapa que **não** é um motor novo: a
infraestrutura que faz o usuário poder escolher, o AssetFlow poder escolher
por ele, e o sistema respeitar as duas coisas.

As quatro regras do §25 são o núcleo do que está testado aqui:

    regra 1  o motor escolhido é respeitado, ou o pedido falha dizendo por quê
    regra 2  fallback só em `auto`, ou quando alguém pediu explicitamente
    regra 3  a resposta mostra motor pedido, motor usado e modelo
    regra 4  o validador usa o spec, nunca defaults internos
"""

from __future__ import annotations

import pytest

from assetflow.bootstrap import AppContainer
from assetflow.generation.kernel.auto_policy import AutoEnginePolicy, EngineRule
from assetflow.generation.kernel.exceptions import (
    EngineDisabled,
    EngineNotFound,
    InvalidGenerationRequest,
)
from assetflow.generation.schemas import (
    AssetGenerationRequest,
    AssetOutputOverrides,
    EngineAdvice,
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
def test_spec_carries_the_engine_decision(container: AppContainer):
    """Em `auto`, a política do projeto responde — e sempre explica.

    O teste habilita `texel-style-v1` porque a suíte roda com as gavetas de
    referência, e as regras de `engine_policy.yaml` falam dos motores de
    produção. Habilitar um deles é o que faz este caso exercitar a
    configuração **entregue**, e não uma política montada no teste.
    """
    container.registry.enable("texel-style-v1")
    spec = container.service.resolve_spec(_request(container))

    assert spec.engine.selection_mode == "auto"
    assert spec.engine.engine_id == "texel-style-v1"
    # O motivo não é enfeite: é o que a tela mostra no "Motor resolvido" (§17).
    assert spec.engine.reason
    assert spec.source_of("engine") is SpecSource.INFERENCE


def test_choosing_automatic_is_not_choosing_an_engine(container: AppContainer):
    """"Automático" no seletor não torna o motor uma escolha da pessoa.

    A origem descreve de onde veio o **valor** de `engine_id`, e em `auto` ele
    vem sempre da política. Registrar `ui_selection` faria a aba
    "Interpretação" mostrar "escolhido na tela" ao lado de um motor que
    ninguém escolheu — e a origem existe justamente para separar essas duas
    coisas (plano T→J §16).
    """
    container.registry.enable("texel-style-v1")
    spec = container.service.resolve_spec(
        _request(container, engine=EngineSelector(mode="auto"))
    )

    assert spec.engine.selection_mode == "auto"
    assert spec.source_of("engine") is SpecSource.INFERENCE


def test_explicit_automatic_without_a_suggestion_is_nobody_choosing(
    container: AppContainer,
):
    spec = container.service.resolve_spec(
        _request(container, engine=EngineSelector(mode="auto"))
    )
    assert spec.engine.engine_id is None
    assert spec.source_of("engine") is SpecSource.GLOBAL_DEFAULT


def test_auto_stays_silent_when_no_preferred_engine_is_up(container: AppContainer):
    """Sem nenhum motor das regras de pé, `auto` não inventa preferência.

    O roteamento por capacidade decide, como decidia antes de a política
    existir — e o spec registra honestamente que ninguém escolheu.
    """
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


# ---------------------------------------------------------------------------
# A política automática (plano de motores §16 e §17)
# ---------------------------------------------------------------------------
def test_policy_prefers_the_first_usable_engine_of_a_matching_rule(
    container: AppContainer,
):
    policy = AutoEnginePolicy(
        registry=container.registry,
        rules=(
            EngineRule(
                id="props_pequenos",
                reason="prop pequeno pede motor especializado",
                prefer=("motor-inexistente", "mock-image-v1"),
                asset_types=frozenset({"prop"}),
                max_logical=32,
            ),
        ),
    )
    advice = EngineAdvice(
        capability="text_to_image.pixel",
        asset_type="prop",
        mode="pixel",
        logical_width=32,
        logical_height=32,
    )

    suggestion = policy.suggest(advice)
    # O primeiro da lista não existe: a política pula, e não sugere fantasma.
    assert suggestion is not None
    assert suggestion.engine_id == "mock-image-v1"
    assert suggestion.reason == "prop pequeno pede motor especializado"
    assert suggestion.rule_id == "props_pequenos"


def test_policy_skips_a_rule_whose_engines_are_all_down(container: AppContainer):
    """Regra que casou mas não tem motor de pé cede a vez à próxima."""
    policy = AutoEnginePolicy(
        registry=container.registry,
        rules=(
            EngineRule(id="primeira", prefer=("motor-inexistente",), reason="a"),
            EngineRule(id="segunda", prefer=("mock-image-v1",), reason="b"),
        ),
    )
    suggestion = policy.suggest(
        EngineAdvice(capability="text_to_image.pixel", asset_type="prop", mode="pixel")
    )
    assert suggestion.rule_id == "segunda"


def test_policy_is_silent_when_nothing_matches(container: AppContainer):
    """Sem regra aplicável, a política se cala e o roteamento decide."""
    policy = AutoEnginePolicy(
        registry=container.registry,
        rules=(
            EngineRule(
                id="so_personagem",
                prefer=("mock-image-v1",),
                asset_types=frozenset({"character"}),
            ),
        ),
    )
    suggestion = policy.suggest(
        EngineAdvice(capability="text_to_image.pixel", asset_type="prop", mode="pixel")
    )
    assert suggestion is None


def test_policy_rules_ignore_size_when_there_is_no_logical_grid():
    """Uma regra que fala de tamanho não se aplica a arte sem grid.

    Tratar "não existe grid" como tamanho 0 faria a regra casar com tudo —
    exatamente o contrário do que uma faixa de tamanho quer dizer.
    """
    rule = EngineRule(id="pequeno", max_logical=32)
    assert not rule.matches(
        EngineAdvice(capability="text_to_image.general", asset_type="prop", mode="studio")
    )


def test_a_broken_policy_never_breaks_a_generation(container: AppContainer):
    """Política que estoura vira ausência de sugestão, não job perdido."""

    class Explodindo:
        def suggest(self, advice):
            raise RuntimeError("política quebrada")

    from assetflow.generation.spec import AssetTypeClassifier, ConstraintResolver

    resolver = ConstraintResolver(
        AssetTypeClassifier(container.taxonomy), advisor=Explodindo()
    )
    profile = container.profiles.get("pixel_character_64")
    spec = resolver.resolve(_request(container), profile).spec

    assert spec.engine.engine_id is None
    assert spec.engine.selection_mode == "auto"


def test_auto_hint_is_a_preference_and_not_a_requirement(container: AppContainer):
    """Um motor sugerido que não pode atender perde a vez, sem erro.

    É a diferença entre sugerir e exigir: em `manual`, um motor indisponível
    faz o job falhar; em `auto`, o roteamento simplesmente segue adiante.
    """
    policy = AutoEnginePolicy(
        registry=container.registry,
        rules=(EngineRule(id="tudo", prefer=("mock-pixel-alt-v1",), reason="teste"),),
    )
    from assetflow.generation.spec import AssetTypeClassifier, ConstraintResolver

    resolver = ConstraintResolver(
        AssetTypeClassifier(container.taxonomy), advisor=policy
    )
    container.service._constraints = resolver  # noqa: SLF001 - injeção de teste

    # A gaveta sugerida existe e está habilitada no momento da resolução...
    container.registry.enable("mock-pixel-alt-v1")
    job = run(container.service.submit(_request(container)))
    spec = job.resolved_spec
    assert spec.engine.engine_id == "mock-pixel-alt-v1"

    # ...mas cai antes de o worker rodar. O job continua, com outro motor.
    container.registry.disable("mock-pixel-alt-v1")
    run(process_next_job(container))
    finished = run(container.service.get_job(job.id))

    assert finished.status.value == "completed"
    assert finished.engine.id == "mock-image-v1"
