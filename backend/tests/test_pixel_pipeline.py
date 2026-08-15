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
    """O motor gera 512×512; o asset é 64×64 — quem reduz é o AssetFlow."""
    job = _completed_job(container, make_request())
    asset = job.asset

    assert asset.variants
    for variant in asset.variants:
        assert (variant.width, variant.height) == (64, 64)
        assert (variant.logical_width, variant.logical_height) == (64, 64)
        assert variant.metadata["render_size"] == [512, 512]


def test_pixel_pipeline_applies_palette_and_alpha_rules(
    container: AppContainer, make_request
):
    job = _completed_job(container, make_request())

    for variant in job.asset.variants:
        assert variant.palette, "a paleta precisa ser registrada no asset"
        assert variant.color_count is not None
        assert variant.color_count <= 16, "profile pixel_character_64 limita 16 cores"
        assert variant.metadata["postprocessing"] == [
            "pixel.logical_resize",
            "pixel.palette_quantize",
            "pixel.alpha_cleanup",
            "pixel.validate_color_count",
            "pixel.validate_grid",
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


def test_grid_validator_reports_mismatch(container: AppContainer):
    """A validação anota o problema em vez de reprovar o asset."""
    from assetflow.generation.postprocessing.pixel import GridValidator

    profile = container.profiles.get("pixel_character_64")
    buffer = ImageBuffer(image=Image.new("RGBA", (48, 48), (10, 20, 30, 255)))
    result = GridValidator().process(buffer, PostProcessContext(profile=profile))

    codes = [issue.code for issue in result.issues]
    assert "grid_size_mismatch" in codes
    assert any(issue.severity == "error" for issue in result.issues)
