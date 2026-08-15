"""Testes da gaveta `diffusers-sdxl-v1` que rodam **sem** GPU e sem torch.

O que se verifica aqui é a disciplina arquitetural do motor real:

- importar a gaveta não importa torch/diffusers;
- sem as dependências, ela se declara `unavailable` em vez de explodir;
- o resolver simplesmente a ignora e o sistema continua funcionando;
- o adapter de prompt específico do SDXL funciona isoladamente.

Os testes de geração de verdade ficam a cargo da suíte de contrato, que roda
automaticamente quando o extra `[diffusers]` estiver instalado.
"""

from __future__ import annotations

import importlib.util
import sys

import pytest

from assetflow.generation.engines.diffusers_sdxl.config import SDXLConfig
from assetflow.generation.engines.diffusers_sdxl.engine import DiffusersSDXLEngine
from assetflow.generation.engines.diffusers_sdxl.prompt_adapter import SDXLPromptAdapter
from assetflow.generation.schemas import (
    EngineDeviceConfig,
    EngineModelConfig,
    EnginePrecisionConfig,
    EngineRuntimeConfig,
    ImageGenerationRequest,
    PromptSpec,
    QualityLevel,
    SemanticPrompt,
    SemanticTechnical,
)

from tests.conftest import run

TORCH_INSTALLED = importlib.util.find_spec("torch") is not None


def test_importing_the_engine_does_not_import_torch():
    """Lazy import (plano §36): a API sobe sem pagar o custo do torch."""
    if TORCH_INSTALLED:
        pytest.skip("torch instalado neste ambiente")
    assert "torch" not in sys.modules
    assert "diffusers" not in sys.modules
    DiffusersSDXLEngine()  # instanciar também não pode importar nada pesado
    assert "torch" not in sys.modules


def test_manifest_is_readable_without_dependencies():
    manifest = DiffusersSDXLEngine().manifest()
    assert manifest.id == "diffusers-sdxl-v1"
    assert manifest.resources.gpu_required is True
    assert manifest.resources.recommended_vram_mb >= 8000
    assert manifest.limits.dimension_multiple_of == 8
    assert "torch" in manifest.requires
    # A gaveta já declara recursos previstos para fases futuras.
    assert manifest.supports.lora is True
    assert manifest.supports.controlnet is False


def test_health_check_reports_missing_dependencies_instead_of_crashing():
    engine = DiffusersSDXLEngine()
    health = run(engine.health_check())

    if TORCH_INSTALLED:
        assert health.status.value in {"healthy", "degraded"}
    else:
        assert health.status.value == "unavailable"
        assert "diffusers" in (health.detail or "")


def test_initialization_failure_is_normalized():
    """Sem dependências, `initialize` levanta erro do vocabulário do AssetFlow."""
    if TORCH_INSTALLED:
        pytest.skip("com torch instalado a inicialização tentaria baixar o modelo")

    from assetflow.generation.kernel.exceptions import EngineInitializationError

    engine = DiffusersSDXLEngine()
    with pytest.raises(EngineInitializationError):
        run(engine.initialize(EngineRuntimeConfig(engine_id="diffusers-sdxl-v1")))


def test_config_is_built_from_external_configuration():
    """Nada de device/precisão/steps hardcoded (plano §65)."""
    runtime = EngineRuntimeConfig(
        engine_id="diffusers-sdxl-v1",
        model=EngineModelConfig(id="org/modelo-x", revision="abc123", variant="fp16"),
        device=EngineDeviceConfig(type="cuda"),
        precision=EnginePrecisionConfig(type="bf16"),
        runtime={"enable_model_cpu_offload": True},
        options={"guidance_scale": 8.0, "quality_steps": {"high": 60}},
    )
    config = SDXLConfig.from_runtime(runtime)

    assert config.model_id == "org/modelo-x"
    assert config.revision == "abc123"
    assert config.device == "cuda"
    assert config.precision == "bf16"
    assert config.enable_model_cpu_offload is True
    assert config.guidance_scale == 8.0
    # O knob abstrato `quality` vira passos aqui dentro — e só aqui (plano §20).
    assert config.steps_for(QualityLevel.HIGH) == 60
    assert config.steps_for(QualityLevel.DRAFT) == 18


def test_prompt_adapter_translates_semantic_into_sdxl_dialect():
    """Plano §27: o adapter é da gaveta; a semântica é do AssetFlow."""
    semantic = SemanticPrompt(
        subject="young warrior",
        medium="pixel_art",
        view="side",
        pose="idle",
        appearance={"armor": "blue"},
        avoid=["modern clothes"],
        technical=SemanticTechnical(limited_palette=16),
    )
    request = ImageGenerationRequest(
        capability="text_to_image.pixel",
        prompt=PromptSpec(positive="ignored", semantic=semantic),
    )

    positive, negative = SDXLPromptAdapter().adapt(request)

    assert "young warrior" in positive
    assert "single game character" in positive  # reforço específico do SDXL
    assert "limited palette of 16 colors" in positive
    assert negative and "modern clothes" in negative
    assert "blurry" in negative  # negativo base do modelo
    # Contrapeso ao viés de folha de sprites, medido nesta gaveta.
    assert "sprite sheet" in negative


def test_real_engine_is_registered_in_the_shelf(container):
    """A gaveta real está instalada e compatível, ligada ou não."""
    record = container.registry.get("diffusers-sdxl-v1")
    assert record.manifest.is_api_compatible
    assert record.manifest.resources.gpu_required is True
    # Registrar jamais carrega modelo (plano §36) — é isso que permite deixar
    # a gaveta ligada no config sem penalizar o boot.
    assert record.handle.is_loaded is False


def test_test_suite_never_pulls_a_real_model(container):
    """Trava de segurança contra download acidental de modelo na suíte.

    Verificar só o motor *preferido* não basta — e isso já custou caro: um
    teste que derruba o motor primário para exercitar o retry fazia o kernel
    cair no fallback e, com as dependências instaladas, começar a baixar o
    SDXL de verdade no meio do `pytest`. O que precisa valer é que a gaveta
    pesada não esteja em **nenhuma** posição da cadeia.
    """
    from assetflow.generation.schemas import Capability

    heavy = {
        record.id
        for record in container.registry.list()
        if record.manifest.resources.gpu_required
    }
    assert heavy, "o teste perdeu o sentido: nenhuma gaveta pesada registrada"

    for capability in ("text_to_image.pixel", "text_to_image.general"):
        resolution = run(container.resolver.resolve(Capability.parse(capability)))
        chain = set(resolution.engine_ids)
        assert not (chain & heavy), (
            f"'{capability}' tem {chain & heavy} na cadeia de resolução; "
            "um fallback baixaria um modelo real durante os testes"
        )


def test_system_works_while_the_real_engine_is_unavailable(container):
    """O resolver ignora a gaveta indisponível e usa outra (plano §43/§44)."""
    from assetflow.generation.schemas import Capability

    container.service.enable_engine("diffusers-sdxl-v1")
    resolution = run(
        container.resolver.resolve(Capability.parse("text_to_image.general"))
    )

    if not TORCH_INSTALLED:
        assert "diffusers-sdxl-v1" not in resolution.engine_ids
        assert "diffusers-sdxl-v1" in dict(resolution.rejected)
    assert resolution.primary.engine_id == "mock-image-v1"
