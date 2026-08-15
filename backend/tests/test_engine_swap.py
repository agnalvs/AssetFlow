"""Swap Engine Test — o critério de aceite arquitetural (planos §67 e §68).

Cenário:

    PixelCharacterPipeline -> Engine A -> asset gerado
    disable Engine A / enable Engine B
    PixelCharacterPipeline -> Engine B -> asset gerado

O teste só passa se **nenhuma linha de código de negócio** for tocada entre
as duas execuções. O que muda é exclusivamente estado de configuração.
"""

from __future__ import annotations

from assetflow.bootstrap import AppContainer
from assetflow.generation.schemas import JobStatus

from tests.conftest import process_next_job, run

ENGINE_A = "mock-image-v1"
ENGINE_B = "mock-pixel-alt-v1"


def _generate(container: AppContainer, make_request) -> tuple:
    """Executa o mesmo pedido de produto, seja lá qual for o motor ativo."""

    async def scenario():
        job = await container.service.submit(make_request())
        assert await process_next_job(container)
        return await container.service.get_job(job.id)

    job = run(scenario())
    assert job.status is JobStatus.COMPLETED, job.error
    return job, job.asset


def test_pipeline_survives_engine_replacement(container: AppContainer, make_request):
    # --- Engine A ------------------------------------------------------
    container.service.enable_engine(ENGINE_A)
    container.service.disable_engine(ENGINE_B)

    pipeline_before = container.pipelines.get("pixel.character")
    profile_before = container.profiles.get("pixel_character_64")

    job_a, asset_a = _generate(container, make_request)
    assert job_a.engine.id == ENGINE_A

    # --- Troca de gaveta (somente estado, nada de código) ---------------
    container.service.disable_engine(ENGINE_A)
    container.service.enable_engine(ENGINE_B)

    job_b, asset_b = _generate(container, make_request)
    assert job_b.engine.id == ENGINE_B

    # --- O que precisa ter permanecido idêntico -------------------------
    assert container.pipelines.get("pixel.character") is pipeline_before
    assert container.profiles.get("pixel_character_64") is profile_before

    assert asset_a.pipeline_id == asset_b.pipeline_id == "pixel.character"
    assert asset_a.profile_id == asset_b.profile_id == "pixel_character_64"
    assert asset_a.type == asset_b.type
    assert asset_a.mode == asset_b.mode
    assert len(asset_a.variants) == len(asset_b.variants)

    for variant_a, variant_b in zip(asset_a.variants, asset_b.variants):
        # Mesmo contrato de asset: 64x64 lógicos, paleta aplicada, URI válida.
        assert (variant_a.width, variant_a.height) == (variant_b.width, variant_b.height) == (64, 64)
        assert variant_a.logical_width == variant_b.logical_width == 64
        assert variant_a.palette and variant_b.palette
        assert variant_a.uri.startswith("assetflow-local://")
        assert variant_b.uri.startswith("assetflow-local://")

    # As imagens são diferentes — os motores são de fato distintos.
    assert asset_a.engine.id != asset_b.engine.id
    assert asset_a.engine.model_id != asset_b.engine.model_id


def test_capability_routing_switches_without_touching_the_pipeline(
    container: AppContainer, make_request
):
    """Reordenar `capabilities.yaml` em runtime muda o motor efetivo."""
    from assetflow.generation.kernel import RoutingPolicy
    from assetflow.generation.schemas import Capability

    container.service.enable_engine(ENGINE_A)
    container.service.enable_engine(ENGINE_B)
    pixel = Capability.parse("text_to_image.pixel")

    container.resolver.set_policy(RoutingPolicy(routing={pixel: (ENGINE_A, ENGINE_B)}))
    job_a, _ = _generate(container, make_request)
    assert job_a.engine.id == ENGINE_A

    container.resolver.set_policy(RoutingPolicy(routing={pixel: (ENGINE_B, ENGINE_A)}))
    job_b, _ = _generate(container, make_request)
    assert job_b.engine.id == ENGINE_B


def test_fallback_keeps_generation_alive_during_a_swap(
    container: AppContainer, make_request
):
    """Motor preferido quebrado: o usuário continua conseguindo gerar (§44)."""
    from assetflow.generation.kernel import RoutingPolicy
    from assetflow.generation.schemas import Capability

    container.service.enable_engine(ENGINE_A)
    container.service.enable_engine(ENGINE_B)
    container.resolver.set_policy(
        RoutingPolicy(routing={Capability.parse("text_to_image.pixel"): (ENGINE_A, ENGINE_B)})
    )

    request = make_request(engine_options={ENGINE_A: {"fail_always": True}})

    async def scenario():
        job = await container.service.submit(request)
        assert await process_next_job(container)
        return await container.service.get_job(job.id)

    job = run(scenario())
    assert job.status is JobStatus.COMPLETED, job.error
    assert job.engine.id == ENGINE_B
    assert job.fallback_used is True
    assert any("fallback" in warning for warning in job.warnings)
