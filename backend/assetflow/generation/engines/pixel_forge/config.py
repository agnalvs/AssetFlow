"""Configuração da ponte para o Pixel Forge (plano §65; plano de motores §8.3).

O Pixel Forge é um gerador de sprites em **Rust**, com três modelos de
difusão embutidos, que roda localmente e produz sprites 32×32. O plano de motores §8.3 é
explícito sobre a consequência arquitetural disso: *"o AssetFlow não deve
acoplar backend principal ao runtime Rust"*.

Então a integração é um binário invocado como processo, com o caminho e os
argumentos vindos de ``config/engines.yaml``. Não existe FFI, não existe
biblioteca compilada dentro do venv, e o backend continua subindo em uma
máquina que nunca ouviu falar de Rust.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ....generation.schemas import EngineRuntimeConfig

__all__ = ["PixelForgeConfig", "ADAPTER_VERSION", "NATIVE_SIZE"]

#: Versão do adapter — o código desta pasta (plano de motores §18).
ADAPTER_VERSION = "1.0.0"

#: Resolução nativa do projeto (plano de motores §2.3). Não é um limite arbitrário nosso:
#: é o tamanho em que os modelos dele foram treinados, e pedir outro é pedir
#: um upscale disfarçado.
NATIVE_SIZE = 32


@dataclass(frozen=True, slots=True)
class PixelForgeConfig:
    """Como invocar o Pixel Forge nesta máquina."""

    #: Caminho do binário. Vazio = gaveta não configurada.
    binary: str = ""
    #: Argumentos com placeholders, aplicados depois do binário.
    args: tuple[str, ...] = ()
    working_dir: str | None = None
    output_glob: str = "*.png"
    output_dir: str | None = None
    process_timeout_s: float = 300.0
    env: dict[str, str] = field(default_factory=dict)
    #: Qual dos modelos do projeto usar, quando a CLI aceitar escolher.
    model_id: str = "pixel-forge"

    @property
    def configured(self) -> bool:
        return bool(self.binary)

    @property
    def command(self) -> tuple[str, ...]:
        return (self.binary, *self.args) if self.binary else ()

    @classmethod
    def from_runtime(cls, config: EngineRuntimeConfig) -> "PixelForgeConfig":
        options: dict[str, Any] = config.options or {}
        raw_args = options.get("args") or ()
        if isinstance(raw_args, str):
            raw_args = [raw_args]

        return cls(
            binary=str(options.get("binary") or config.model.path or ""),
            args=tuple(str(item) for item in raw_args),
            working_dir=options.get("working_dir"),
            output_glob=str(options.get("output_glob", "*.png")),
            output_dir=options.get("output_dir"),
            process_timeout_s=float(options.get("process_timeout_s", 300.0)),
            env={str(k): str(v) for k, v in (options.get("env") or {}).items()},
            model_id=str(config.model.id or "pixel-forge"),
        )
