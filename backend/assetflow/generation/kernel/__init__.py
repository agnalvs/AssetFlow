"""Generation Kernel — a "estante" do AssetFlow.

Ordem de leitura recomendada:

1. :mod:`contracts`     — o Engine Contract (o encaixe da gaveta);
2. :mod:`capabilities`  — o catálogo de capacidades;
3. :mod:`lifecycle`     — estados e carregamento preguiçoso;
4. :mod:`discovery`     — como uma gaveta é encontrada e importada;
5. :mod:`registry`      — quais gavetas existem;
6. :mod:`resolver`      — qual gaveta atende cada capacidade;
7. :mod:`service`       — execução, fallback, timeout e normalização.

Nada neste pacote importa um engine concreto.
"""

from .capabilities import CATALOG, CapabilityCatalog, CapabilityInfo
from .contracts import (
    BaseImageGenerationEngine,
    CancellationToken,
    EngineExecutionContext,
    EngineFactory,
    ImageGenerationEngine,
    NullProgressReporter,
    ProgressReporter,
    SemanticPromptAdapter,
)
from .discovery import DiscoveredEngine, build_factory, discover_manifests, load_engine_class
from .exceptions import (
    CapabilityNotSupported,
    EngineDisabled,
    EngineExecutionError,
    EngineIncompatible,
    EngineInitializationError,
    EngineNotFound,
    EngineOutOfMemoryError,
    EngineTimeoutError,
    EngineUnavailable,
    ErrorCode,
    GenerationCancelled,
    GenerationError,
    InvalidGenerationRequest,
    JobNotFound,
    NoEngineAvailable,
    PipelineNotFound,
    PostProcessingError,
    ProfileNotFound,
    StorageError,
)
from .lifecycle import EngineHandle
from .registry import EngineRecord, EngineRegistry
from .resolver import EngineCandidate, EngineResolution, EngineResolver, RoutingPolicy
from .service import GenerationKernel

__all__ = [
    "CATALOG",
    "BaseImageGenerationEngine",
    "CancellationToken",
    "CapabilityCatalog",
    "CapabilityInfo",
    "CapabilityNotSupported",
    "DiscoveredEngine",
    "EngineCandidate",
    "EngineDisabled",
    "EngineExecutionContext",
    "EngineExecutionError",
    "EngineFactory",
    "EngineHandle",
    "EngineIncompatible",
    "EngineInitializationError",
    "EngineNotFound",
    "EngineOutOfMemoryError",
    "EngineRecord",
    "EngineRegistry",
    "EngineResolution",
    "EngineResolver",
    "EngineTimeoutError",
    "EngineUnavailable",
    "ErrorCode",
    "GenerationCancelled",
    "GenerationError",
    "GenerationKernel",
    "ImageGenerationEngine",
    "InvalidGenerationRequest",
    "JobNotFound",
    "NoEngineAvailable",
    "NullProgressReporter",
    "PipelineNotFound",
    "PostProcessingError",
    "ProfileNotFound",
    "ProgressReporter",
    "RoutingPolicy",
    "SemanticPromptAdapter",
    "StorageError",
    "build_factory",
    "discover_manifests",
    "load_engine_class",
]
