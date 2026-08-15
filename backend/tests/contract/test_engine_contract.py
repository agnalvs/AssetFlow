"""EngineContractTest — a suíte que toda gaveta precisa passar (plano §66).

Qualquer motor novo é automaticamente incluído aqui: os casos são gerados a
partir dos manifestos descobertos em ``generation/engines``. Se a gaveta
declara dependências que não estão instaladas (ex.: torch), o caso é pulado
em vez de falhar — o contrato continua sendo cobrado quando o ambiente tiver
o necessário.

Checklist do plano:

    ✔ manifest válido      ✔ generate            ✔ erro normalizado
    ✔ capability válida    ✔ result válido       ✔ unload
    ✔ initialize           ✔ seed registrada     ✔ health check
"""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pytest
from PIL import Image

from assetflow.generation.kernel.contracts import (
    CancellationToken,
    EngineExecutionContext,
    ImageGenerationEngine,
)
from assetflow.generation.kernel.discovery import discover_manifests, load_engine_class
from assetflow.generation.kernel.exceptions import GenerationCancelled, GenerationError
from assetflow.generation.schemas import (
    SUPPORTED_ENGINE_API_VERSIONS,
    Capability,
    EngineHealth,
    EngineManifest,
    EngineRuntimeConfig,
    ImageGenerationRequest,
    OutputSpec,
    PromptSpec,
)

ENGINES_ROOT = Path(__file__).resolve().parents[2] / "assetflow" / "generation" / "engines"
DISCOVERED = discover_manifests([ENGINES_ROOT])


def _missing_requirements(manifest: EngineManifest) -> list[str]:
    return [name for name in manifest.requires if importlib.util.find_spec(name) is None]


def _make_engine(manifest: EngineManifest) -> ImageGenerationEngine:
    return load_engine_class(manifest.entrypoint)()


def _request(manifest: EngineManifest, *, seed: int | None = 1234) -> ImageGenerationRequest:
    """Pedido mínimo que respeita os limites declarados pela gaveta."""
    limits = manifest.limits
    width = max(limits.min_width, min(256, limits.max_width))
    height = max(limits.min_height, min(256, limits.max_height))
    if limits.dimension_multiple_of:
        step = limits.dimension_multiple_of
        width = max(limits.min_width, (width // step) * step)
        height = max(limits.min_height, (height // step) * step)

    return ImageGenerationRequest(
        capability=manifest.capabilities[0],
        prompt=PromptSpec(positive="contract test subject"),
        output=OutputSpec(width=width, height=height, variations=1),
        generation={"seed": seed} if seed is not None else {},
    )


def _context(job_id: str = "job_contract") -> EngineExecutionContext:
    return EngineExecutionContext(job_id=job_id, cancellation=CancellationToken())


def _params():
    params = []
    for entry in DISCOVERED:
        missing = _missing_requirements(entry.manifest)
        marks = (
            pytest.mark.skip(reason=f"dependências ausentes: {', '.join(missing)}"),
        ) if missing else ()
        params.append(pytest.param(entry.manifest, id=entry.manifest.id, marks=marks))
    return params


pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")


def test_at_least_one_engine_is_discovered():
    assert DISCOVERED, "nenhuma gaveta encontrada — a descoberta por manifesto quebrou"


@pytest.mark.parametrize("manifest", _params())
class TestEngineContract:
    """Contrato obrigatório, verificado gaveta por gaveta."""

    # -- Manifesto -------------------------------------------------------
    def test_manifest_is_valid(self, manifest: EngineManifest):
        assert manifest.id
        assert manifest.version
        assert manifest.engine_api_version in SUPPORTED_ENGINE_API_VERSIONS
        assert manifest.entrypoint.count(":") == 1
        assert manifest.limits.max_width >= manifest.limits.min_width
        assert manifest.limits.max_variations >= 1

    def test_capabilities_are_valid(self, manifest: EngineManifest):
        assert manifest.capabilities
        for capability in manifest.capabilities:
            assert isinstance(capability, Capability)
            assert manifest.declares(capability)

    def test_class_implements_the_contract(self, manifest: EngineManifest):
        engine_class = load_engine_class(manifest.entrypoint)
        assert issubclass(engine_class, ImageGenerationEngine)
        # Manifesto acessível sem inicializar (o registry depende disso).
        engine = engine_class()
        assert engine.manifest().id == manifest.id
        assert engine.capabilities() == manifest.capabilities

    # -- Ciclo de vida ---------------------------------------------------
    def test_initialize_health_and_unload(self, manifest: EngineManifest, run):
        engine = _make_engine(manifest)

        async def scenario():
            before = await engine.health_check()
            assert isinstance(before, EngineHealth)

            await engine.initialize(EngineRuntimeConfig(engine_id=manifest.id))
            after = await engine.health_check()
            assert isinstance(after, EngineHealth)

            await engine.unload()
            # unload precisa ser idempotente
            await engine.unload()

        run(scenario())

    # -- Execução --------------------------------------------------------
    def test_generate_returns_normalized_result(self, manifest: EngineManifest, run):
        engine = _make_engine(manifest)
        request = _request(manifest)

        async def scenario():
            await engine.initialize(EngineRuntimeConfig(engine_id=manifest.id))
            try:
                return await engine.generate(request, _context())
            finally:
                await engine.unload()

        result = run(scenario())

        assert result.engine.id == manifest.id
        assert result.engine.version == manifest.version
        assert len(result.artifacts) == request.output.variations

        for artifact in result.artifacts:
            assert artifact.data, "a gaveta devolveu um artefato vazio"
            assert artifact.width == request.output.width
            assert artifact.height == request.output.height
            image = Image.open(io.BytesIO(artifact.data))
            assert image.size == (request.output.width, request.output.height)

    def test_seed_is_registered_and_respected(self, manifest: EngineManifest, run):
        if not manifest.supports.seed:
            pytest.skip("gaveta declara que não suporta seed")

        async def generate(seed: int):
            engine = _make_engine(manifest)
            await engine.initialize(EngineRuntimeConfig(engine_id=manifest.id))
            try:
                return await engine.generate(_request(manifest, seed=seed), _context())
            finally:
                await engine.unload()

        first = run(generate(777))
        second = run(generate(777))
        third = run(generate(778))

        assert first.artifacts[0].seed == 777, "a seed usada precisa voltar no resultado"
        assert first.artifacts[0].data == second.artifacts[0].data, (
            "mesma seed deve produzir o mesmo resultado"
        )
        assert first.artifacts[0].data != third.artifacts[0].data, (
            "seeds diferentes devem produzir resultados diferentes"
        )

    def test_cancellation_is_cooperative(self, manifest: EngineManifest, run):
        if not manifest.supports.cancellation:
            pytest.skip("gaveta declara que não suporta cancelamento")

        engine = _make_engine(manifest)
        context = _context()
        context.cancellation.cancel("teste de contrato")

        async def scenario():
            await engine.initialize(EngineRuntimeConfig(engine_id=manifest.id))
            try:
                await engine.generate(_request(manifest), context)
            finally:
                await engine.unload()

        with pytest.raises(GenerationCancelled):
            run(scenario())

    def test_misuse_never_leaks_a_foreign_exception(self, manifest: EngineManifest, run):
        """Uso indevido (gerar sem inicializar) é tolerado **ou** normalizado.

        O que o contrato proíbe é vazar a exceção nativa da tecnologia: quem
        estiver acima só sabe lidar com :class:`GenerationError`.
        """
        engine = _make_engine(manifest)

        async def scenario():
            await engine.generate(_request(manifest), _context())

        try:
            run(scenario())
        except GenerationError as exc:
            assert exc.code is not None
            assert exc.message
        except Exception as exc:  # pragma: no cover - falha de contrato
            pytest.fail(
                f"gaveta '{manifest.id}' vazou uma exceção não normalizada: {exc!r}"
            )
