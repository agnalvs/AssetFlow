"""Erros normalizados do sistema de geração (plano §66).

Um motor pode falhar de mil formas diferentes — CUDA OOM, timeout de API,
arquivo corrompido, quota estourada. O AssetFlow enxerga **sempre** o mesmo
conjunto de erros, com o mesmo código e a mesma informação de retry.

É responsabilidade de cada gaveta traduzir as exceções da sua tecnologia para
estas classes. Nada acima do engine deve capturar `torch.cuda.OutOfMemoryError`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

__all__ = [
    "ErrorCode",
    "GenerationError",
    "InvalidGenerationRequest",
    "CapabilityNotSupported",
    "EngineNotFound",
    "EngineDisabled",
    "EngineIncompatible",
    "NoEngineAvailable",
    "EngineInitializationError",
    "EngineExecutionError",
    "EngineTimeoutError",
    "EngineOutOfMemoryError",
    "EngineUnavailable",
    "GenerationCancelled",
    "ProfileNotFound",
    "PipelineNotFound",
    "PostProcessingError",
    "StorageError",
    "JobNotFound",
]


class ErrorCode(str, Enum):
    """Códigos estáveis — o frontend pode reagir a eles."""

    INVALID_REQUEST = "invalid_request"
    CAPABILITY_NOT_SUPPORTED = "capability_not_supported"
    ENGINE_NOT_FOUND = "engine_not_found"
    ENGINE_DISABLED = "engine_disabled"
    ENGINE_INCOMPATIBLE = "engine_incompatible"
    NO_ENGINE_AVAILABLE = "no_engine_available"
    ENGINE_INITIALIZATION_FAILED = "engine_initialization_failed"
    ENGINE_EXECUTION_FAILED = "engine_execution_failed"
    ENGINE_TIMEOUT = "engine_timeout"
    ENGINE_OUT_OF_MEMORY = "engine_out_of_memory"
    ENGINE_UNAVAILABLE = "engine_unavailable"
    CANCELLED = "cancelled"
    PROFILE_NOT_FOUND = "profile_not_found"
    PIPELINE_NOT_FOUND = "pipeline_not_found"
    POSTPROCESSING_FAILED = "postprocessing_failed"
    STORAGE_FAILED = "storage_failed"
    JOB_NOT_FOUND = "job_not_found"
    INTERNAL = "internal_error"


class GenerationError(Exception):
    """Raiz de toda falha do sistema de geração.

    Args:
        message: mensagem legível.
        code: código normalizado.
        retryable: se o Job System pode tentar de novo (plano §45).
        engine_id: motor envolvido, quando houver.
        detail: contexto adicional para observabilidade.
    """

    code: ErrorCode = ErrorCode.INTERNAL
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        retryable: bool | None = None,
        engine_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.engine_id = engine_id
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "engine_id": self.engine_id,
            "detail": self.detail,
        }

    def __str__(self) -> str:  # pragma: no cover - trivial
        suffix = f" [engine={self.engine_id}]" if self.engine_id else ""
        return f"{self.code.value}: {self.message}{suffix}"


# ---------------------------------------------------------------------------
# Erros de request
# ---------------------------------------------------------------------------
class InvalidGenerationRequest(GenerationError):
    code = ErrorCode.INVALID_REQUEST


class CapabilityNotSupported(GenerationError):
    code = ErrorCode.CAPABILITY_NOT_SUPPORTED


class ProfileNotFound(GenerationError):
    code = ErrorCode.PROFILE_NOT_FOUND


class PipelineNotFound(GenerationError):
    code = ErrorCode.PIPELINE_NOT_FOUND


class JobNotFound(GenerationError):
    code = ErrorCode.JOB_NOT_FOUND


# ---------------------------------------------------------------------------
# Erros de registry/resolver
# ---------------------------------------------------------------------------
class EngineNotFound(GenerationError):
    code = ErrorCode.ENGINE_NOT_FOUND


class EngineDisabled(GenerationError):
    code = ErrorCode.ENGINE_DISABLED


class EngineIncompatible(GenerationError):
    """Motor declara uma Engine API que este backend não sabe operar (§10)."""

    code = ErrorCode.ENGINE_INCOMPATIBLE


class NoEngineAvailable(GenerationError):
    """Nenhuma gaveta atende a capacidade pedida — nem por fallback (§44)."""

    code = ErrorCode.NO_ENGINE_AVAILABLE


# ---------------------------------------------------------------------------
# Erros de execução
# ---------------------------------------------------------------------------
class EngineInitializationError(GenerationError):
    code = ErrorCode.ENGINE_INITIALIZATION_FAILED
    retryable = True


class EngineExecutionError(GenerationError):
    code = ErrorCode.ENGINE_EXECUTION_FAILED
    retryable = True


class EngineTimeoutError(GenerationError):
    code = ErrorCode.ENGINE_TIMEOUT
    retryable = True


class EngineOutOfMemoryError(GenerationError):
    """Sem VRAM. Retryable com batch reduzido (plano §45)."""

    code = ErrorCode.ENGINE_OUT_OF_MEMORY
    retryable = True


class EngineUnavailable(GenerationError):
    """O motor existe mas não está apto agora (health FAILED/DEGRADED)."""

    code = ErrorCode.ENGINE_UNAVAILABLE
    retryable = True


class GenerationCancelled(GenerationError):
    code = ErrorCode.CANCELLED
    retryable = False


class PostProcessingError(GenerationError):
    code = ErrorCode.POSTPROCESSING_FAILED


class StorageError(GenerationError):
    code = ErrorCode.STORAGE_FAILED
    retryable = True
