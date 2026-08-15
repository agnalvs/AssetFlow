"""Schemas do sistema de geração do AssetFlow.

Este pacote é a **linguagem comum** entre API, kernel, pipelines, storage e
gavetas. Nenhum módulo aqui pode importar um engine concreto nem uma
biblioteca de IA.
"""

from .asset import AssetVariant, GeneratedAsset, ValidationIssue, ValidationReport
from .asset_request import AssetGenerationRequest, AssetOutputOverrides
from .capability import Capability, CapabilityParseError
from .common import (
    AssetFlowModel,
    AssetMode,
    AssetType,
    FrozenModel,
    QualityLevel,
    StageTimings,
    Stopwatch,
    new_id,
    utcnow,
)
from .engine import (
    ENGINE_API_VERSION,
    SUPPORTED_ENGINE_API_VERSIONS,
    EngineDescriptor,
    EngineDeviceConfig,
    EngineHealth,
    EngineHealthStatus,
    EngineLimits,
    EngineManifest,
    EngineModelConfig,
    EnginePrecisionConfig,
    EngineRef,
    EngineResources,
    EngineRuntimeConfig,
    EngineState,
    EngineSupports,
    EngineTimeouts,
    EngineType,
)
from .job import TERMINAL_JOB_STATUSES, Job, JobErrorInfo, JobEvent, JobStatus
from .request import (
    AssetSpec,
    EngineSelector,
    GenerationParams,
    ImageGenerationRequest,
    OutputSpec,
    PromptSpec,
    ReferenceImage,
    StructuralControl,
)
from .result import (
    EngineGenerationResult,
    GenerationOutput,
    GenerationResult,
    GenerationStatus,
    ImageArtifact,
)
from .semantic_prompt import SemanticComposition, SemanticPrompt, SemanticTechnical

__all__ = [
    "ENGINE_API_VERSION",
    "SUPPORTED_ENGINE_API_VERSIONS",
    "TERMINAL_JOB_STATUSES",
    "AssetFlowModel",
    "AssetGenerationRequest",
    "AssetMode",
    "AssetOutputOverrides",
    "AssetSpec",
    "AssetType",
    "AssetVariant",
    "Capability",
    "CapabilityParseError",
    "EngineDescriptor",
    "EngineDeviceConfig",
    "EngineGenerationResult",
    "EngineHealth",
    "EngineHealthStatus",
    "EngineLimits",
    "EngineManifest",
    "EngineModelConfig",
    "EnginePrecisionConfig",
    "EngineRef",
    "EngineResources",
    "EngineRuntimeConfig",
    "EngineSelector",
    "EngineState",
    "EngineSupports",
    "EngineTimeouts",
    "EngineType",
    "FrozenModel",
    "GeneratedAsset",
    "GenerationOutput",
    "GenerationParams",
    "GenerationResult",
    "GenerationStatus",
    "ImageArtifact",
    "ImageGenerationRequest",
    "Job",
    "JobErrorInfo",
    "JobEvent",
    "JobStatus",
    "OutputSpec",
    "PromptSpec",
    "QualityLevel",
    "ReferenceImage",
    "SemanticComposition",
    "SemanticPrompt",
    "SemanticTechnical",
    "StageTimings",
    "Stopwatch",
    "StructuralControl",
    "ValidationIssue",
    "ValidationReport",
    "new_id",
    "utcnow",
]
