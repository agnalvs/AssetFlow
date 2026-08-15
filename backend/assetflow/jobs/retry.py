"""Política de retry (plano §45).

Retry pertence ao Job System, **não** ao modelo. O motor apenas reporta um
erro normalizado dizendo se ele é transitório; quem decide tentar de novo,
quantas vezes e com qual ajuste é esta camada.

Erros determinísticos (request inválido, capacidade inexistente) não são
repetidos — repetir não mudaria o resultado.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..generation.kernel.exceptions import (
    EngineOutOfMemoryError,
    ErrorCode,
    GenerationError,
)
from ..generation.schemas import AssetGenerationRequest

__all__ = ["RetryPolicy", "RetryDecision"]

#: Erros que nunca devem ser repetidos, mesmo se marcados como retryable.
_NEVER_RETRY: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.INVALID_REQUEST,
        ErrorCode.CAPABILITY_NOT_SUPPORTED,
        ErrorCode.PROFILE_NOT_FOUND,
        ErrorCode.PIPELINE_NOT_FOUND,
        ErrorCode.ENGINE_NOT_FOUND,
        ErrorCode.ENGINE_DISABLED,
        ErrorCode.ENGINE_INCOMPATIBLE,
        ErrorCode.CANCELLED,
    }
)


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """O que fazer depois de uma falha."""

    retry: bool
    delay_s: float = 0.0
    reason: str = ""
    #: Se `True`, o motor deve ser descarregado antes da nova tentativa.
    unload_engine: bool = False


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Backoff exponencial simples com teto."""

    max_attempts: int = 2
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    multiplier: float = 2.0

    def decide(self, error: GenerationError, attempts: int) -> RetryDecision:
        """Decide se o job será reenfileirado.

        Args:
            error: erro normalizado da tentativa que falhou.
            attempts: quantas tentativas já foram consumidas.
        """
        if attempts >= self.max_attempts:
            return RetryDecision(False, reason="tentativas esgotadas")
        if error.code in _NEVER_RETRY:
            return RetryDecision(False, reason=f"erro determinístico ({error.code.value})")
        if not error.retryable:
            return RetryDecision(False, reason="erro marcado como não repetível")

        delay = min(self.max_delay_s, self.base_delay_s * (self.multiplier ** (attempts - 1)))
        return RetryDecision(
            True,
            delay_s=delay,
            reason=f"erro transitório ({error.code.value})",
            unload_engine=isinstance(error, EngineOutOfMemoryError),
        )

    def adjust_request(
        self, request: AssetGenerationRequest, error: GenerationError
    ) -> AssetGenerationRequest:
        """Ajusta o pedido para a próxima tentativa.

        Hoje cobre o caso clássico do plano §45: depois de um OOM, a nova
        tentativa reduz o lote pela metade em vez de repetir o mesmo pedido.
        """
        if not isinstance(error, EngineOutOfMemoryError):
            return request

        current = request.output.variations
        if current is None or current <= 1:
            return request
        reduced = max(1, current // 2)
        return request.model_copy(
            update={"output": request.output.model_copy(update={"variations": reduced})},
            deep=True,
        )
