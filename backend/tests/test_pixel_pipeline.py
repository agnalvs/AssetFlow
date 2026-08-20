"""Testes do PixelCharacterPipeline e do pós-processamento de Pixel Art."""

from __future__ import annotations

import io

from PIL import Image

from assetflow.bootstrap import AppContainer
from assetflow.generation.postprocessing import (
    ImageBuffer,
    PostProcessContext,
    build_pixel_chain,
)
from assetflow.generation.schemas import AssetGenerationRequest, AssetOutputOverrides, JobStatus

from tests.conftest import process_next_job, run


def _completed_job(container: AppContainer, request):
    async def scenario():
        job = await container.service.submit(request)
        assert await process_next_job(container)
        return await container.service.get_job(job.id)

    job = run(scenario())
    assert job.status is JobStatus.COMPLETED, job.error
    return job


def test_pixel_pipeline_produces_logical_resolution(container: AppContainer, make_request):
    """O motor gera na resolução do profile; o asset é 64×64 — quem reduz é o AssetFlow.

    A resolução de render é uma decisão de qualidade do profile e já mudou uma
    vez (512 → 1024, porque o SDXL devolvia grade de tiles em 512). Por isso o
    valor esperado vem do próprio profile: o que este teste fixa é o contrato
    ``render ≠ lógico``, não o número.
    """
    request = make_request()
    profile = container.profiles.get(request.profile)
    render_size = [profile.output.render_width, profile.output.render_height]

    job = _completed_job(container, request)
    asset = job.asset

    assert render_size != [64, 64], "sem downscale o teste não prova nada"
    assert asset.variants
    for variant in asset.variants:
        assert (variant.width, variant.height) == (64, 64)
        assert (variant.logical_width, variant.logical_height) == (64, 64)
        assert variant.metadata["render_size"] == render_size


def test_pixel_pipeline_applies_palette_and_alpha_rules(
    container: AppContainer, make_request
):
    job = _completed_job(container, make_request())

    for variant in job.asset.variants:
        assert variant.palette, "a paleta precisa ser registrada no asset"
        assert variant.color_count is not None
        assert variant.color_count <= 16, "profile pixel_character_64 limita 16 cores"
        # A cadeia tem um elo só: o Pixel Exact inteiro (estágios, validação e
        # política de aceitação) mora em `assetflow.pixel` (plano Pixel §63).
        assert variant.metadata["postprocessing"] == ["pixel.exact"]
        assert variant.metadata["pixel_steps"] == [
            "pixel.input_normalizer",
            "pixel.canvas_normalizer",
            "pixel.logical_reducer",
            "pixel.alpha_normalizer",
            "pixel.palette_quantizer",
            "pixel.conservative_cleaner",
        ]
        assert variant.validation.ok


def test_pixel_assets_have_binary_alpha(container: AppContainer, make_request):
    job = _completed_job(container, make_request())

    async def read(uri: str) -> bytes:
        return await container.storage.read(uri)

    data = run(read(job.asset.variants[0].uri))
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    alpha_values = {value for value, count in enumerate(image.getchannel("A").histogram()) if count}
    assert alpha_values <= {0, 255}, "Pixel Art não pode ficar com alpha parcial"


def test_thumbnail_is_generated_and_scaled_up(container: AppContainer, make_request):
    job = _completed_job(container, make_request())
    variant = job.asset.variants[0]
    assert variant.thumbnail_uri

    async def read(uri: str) -> bytes:
        return await container.storage.read(uri)

    thumbnail = Image.open(io.BytesIO(run(read(variant.thumbnail_uri))))
    # thumbnail_scale=4 no profile pixel_character_64
    assert thumbnail.size == (256, 256)


def test_generation_history_is_persisted(container: AppContainer, make_request):
    job = _completed_job(container, make_request())

    records = run(container.service.history(project_id="project_test"))
    assert records, "toda geração precisa entrar no histórico (plano §41)"

    record = records[0]
    assert record.job_id == job.id
    assert record.engine_id == job.engine.id
    assert record.engine_version
    assert record.model_id, "nunca depender só do nome do motor (plano §42)"
    assert record.seed == 4242
    assert record.semantic_prompt is not None
    assert record.semantic_prompt.medium == "pixel_art"
    assert record.positive_prompt
    assert len(record.outputs) == len(job.asset.variants)
    assert record.timings.inference_ms is not None


def test_same_seed_produces_identical_assets(container: AppContainer, make_request):
    first = _completed_job(container, make_request())
    second = _completed_job(container, make_request())

    async def read(uri: str) -> bytes:
        return await container.storage.read(uri)

    assert run(read(first.asset.variants[0].uri)) == run(read(second.asset.variants[0].uri))


def test_studio_pipeline_uses_the_same_kernel(container: AppContainer):
    """Plano §60: acrescentar o modo Studio não muda o Kernel."""
    job = _completed_job(
        container,
        AssetGenerationRequest(
            project_id="project_test",
            profile="studio_character",
            prompt="cartoon knight",
            output=AssetOutputOverrides(variations=1),
        ),
    )
    variant = job.asset.variants[0]
    assert (variant.width, variant.height) == (1024, 1024)
    assert variant.logical_width is None, "arte 2D não tem grid lógico"
    assert job.asset.pipeline_id == "studio.character"


# ---------------------------------------------------------------------------
# Pós-processamento isolado
# ---------------------------------------------------------------------------
def _gradient(width: int, height: int) -> Image.Image:
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    for x in range(width):
        for y in range(height):
            pixels[x, y] = (x % 256, y % 256, (x * y) % 256, 255 if x > 4 else 100)
    return image


def test_pixel_chain_reduces_resolution_and_colors(container: AppContainer):
    profile = container.profiles.get("pixel_character_32")
    chain = build_pixel_chain()
    buffer = ImageBuffer(image=_gradient(512, 512))

    result = chain.run(buffer, PostProcessContext(profile=profile))

    assert result.image.size == (32, 32)
    assert result.logical_size == (32, 32)
    assert result.metadata["color_count"] <= profile.palette.size
    alpha_values = {
        value for value, count in enumerate(result.image.getchannel("A").histogram()) if count
    }
    assert alpha_values <= {0, 255}


def test_pixel_chain_records_the_pixel_exact_verdict(container: AppContainer):
    """O veredito técnico chega ao asset, não fica preso no módulo Pixel."""
    profile = container.profiles.get("pixel_character_64")
    chain = build_pixel_chain(container.pixel_profiles)
    buffer = ImageBuffer(image=_gradient(512, 512))

    result = chain.run(buffer, PostProcessContext(profile=profile))

    assert result.metadata["pixel_exact"] is True
    assert result.metadata["status"] in {"approved", "quality_warning"}
    assert 0 <= result.metadata["quality_score"] <= 100
    assert result.metadata["hard_checks"]["PX-DIM-001"] == "pass"
    # Plano Pixel §70: o asset não vem sozinho — os arquivos de diagnóstico
    # acompanham a variação.
    assert {"preview.png", "palette.json", "processing.json", "validation.json"} <= set(
        result.artifacts
    )


def test_pixel_variant_carries_the_pixel_exact_seal(container: AppContainer, make_request):
    """Plano Pixel §79: a interface precisa poder dizer "PIXEL EXACT ✓"."""
    job = _completed_job(container, make_request())

    for variant in job.asset.variants:
        assert variant.pixel_exact is True
        assert variant.quality_score is not None
        assert variant.status in {"approved", "quality_warning"}
        assert variant.preview_uri, "o preview ampliado precisa ser persistido"
        assert "raw.png" in variant.artifacts, "o bruto do motor fica guardado (§71)"


def test_studio_asset_has_no_pixel_verdict(container: AppContainer):
    """Arte 2D não tem grid lógico — perguntar se é Pixel Exact não faz sentido."""
    job = _completed_job(
        container,
        AssetGenerationRequest(
            project_id="project_test",
            profile="studio_character",
            prompt="cartoon knight",
            output=AssetOutputOverrides(variations=1),
        ),
    )
    variant = job.asset.variants[0]
    assert variant.pixel_exact is None
    assert variant.status is None
    # `resolved_spec.json` acompanha toda geração, inclusive esta (plano T→J
    # §35): é o contrato que produziu o arquivo, e depurar arte 2D também
    # precisa dele. O que não pode existir aqui é artefato do Pixel Exact.
    assert set(variant.artifacts) == {"resolved_spec.json"}
