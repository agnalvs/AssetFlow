"""Configuração tipada da gaveta `mock-image-v1`.

Cada gaveta interpreta o bloco ``options`` de ``config/engines.yaml`` do seu
próprio jeito. O AssetFlow não conhece nenhuma destas chaves.
"""

from __future__ import annotations

from dataclasses import dataclass

from ....generation.schemas import EngineRuntimeConfig

__all__ = ["MockImageConfig"]


@dataclass(frozen=True, slots=True)
class MockImageConfig:
    """Opções da gaveta mock."""

    #: Latência artificial por variação, para exercitar progresso/cancelamento.
    simulated_latency_ms: float = 0.0
    #: Esquema de cor do placeholder: ``spectrum`` | ``mono`` | ``duotone``.
    palette: str = "spectrum"
    #: Se `True`, falha propositalmente — usado em testes de fallback.
    fail_always: bool = False
    #: Texto adicional desenhado na imagem (debug).
    watermark: bool = True

    @classmethod
    def from_runtime(cls, config: EngineRuntimeConfig) -> "MockImageConfig":
        options = config.options or {}
        return cls(
            simulated_latency_ms=float(options.get("simulated_latency_ms", 0.0)),
            palette=str(options.get("palette", "spectrum")),
            fail_always=bool(options.get("fail_always", False)),
            watermark=bool(options.get("watermark", True)),
        )
