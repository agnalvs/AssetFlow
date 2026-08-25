"""Configuração da ponte para o SD-πXL (plano §65; plano de motores §8.2).

O SD-πXL não é uma biblioteca que se importa: é um projeto que se executa. Ele
otimiza cada imagem iterativamente, pode levar **horas** e recomenda 24 GB de
VRAM — números do próprio repositório, e é por causa deles que esta gaveta
nasce desabilitada e marcada como experimental.

Por isso a integração é por **linha de comando**, e o comando inteiro é
configuração::

    command: ["python", "main.py", "--prompt", "{prompt}", "--size", "{logical_width}"]

Nada aqui adivinha a interface do projeto. Se ela mudar, muda o YAML. O
AssetFlow não pode ficar acoplado à CLI de um projeto de terceiros, e a forma
de não ficar é nunca ter escrito essa CLI em código.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ....generation.schemas import EngineRuntimeConfig, QualityLevel

__all__ = ["SDPiXLConfig", "ADAPTER_VERSION"]

#: Versão do adapter — o código desta pasta (plano de motores §18).
ADAPTER_VERSION = "1.0.0"

#: Passos de otimização por nível de qualidade. Os números são altos porque a
#: técnica é otimização, não difusão: aqui "standard" já é caro.
DEFAULT_QUALITY_STEPS: dict[str, int] = {
    QualityLevel.DRAFT.value: 200,
    QualityLevel.STANDARD.value: 500,
    QualityLevel.HIGH.value: 1000,
}


@dataclass(frozen=True, slots=True)
class SDPiXLConfig:
    """Como invocar o SD-πXL nesta máquina."""

    #: Comando completo, com placeholders. Vazio = gaveta não configurada, e
    #: o health check diz isso em vez de tentar e falhar no meio de um job.
    command: tuple[str, ...] = ()
    #: Diretório de trabalho do processo. Normalmente o clone do projeto.
    working_dir: str | None = None
    #: Onde procurar o PNG produzido, relativo ao diretório de saída.
    output_glob: str = "*.png"
    #: Diretório de saída entregue ao processo via ``{output_dir}``. Vazio usa
    #: uma pasta temporária por job — o padrão, e o mais seguro.
    output_dir: str | None = None
    #: Teto do processo externo, em segundos. Generoso de propósito: o projeto
    #: avisa que pode levar horas.
    process_timeout_s: float = 7200.0
    #: Variáveis de ambiente extras para o processo.
    env: dict[str, str] = field(default_factory=dict)
    quality_steps: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_QUALITY_STEPS)
    )
    model_id: str = "sd-pixl"

    @property
    def configured(self) -> bool:
        return bool(self.command)

    @classmethod
    def from_runtime(cls, config: EngineRuntimeConfig) -> "SDPiXLConfig":
        options: dict[str, Any] = config.options or {}
        steps = {**DEFAULT_QUALITY_STEPS, **(options.get("quality_steps") or {})}
        raw_command = options.get("command") or ()
        if isinstance(raw_command, str):
            # Uma string vira lista de um elemento só, e não é dividida por
            # espaço: dividir quebraria caminhos do Windows com espaço no meio
            # ("C:/Program Files/..."), que é o caso mais comum de erro aqui.
            raw_command = [raw_command]

        return cls(
            command=tuple(str(item) for item in raw_command),
            working_dir=options.get("working_dir"),
            output_glob=str(options.get("output_glob", "*.png")),
            output_dir=options.get("output_dir"),
            process_timeout_s=float(options.get("process_timeout_s", 7200.0)),
            env={str(k): str(v) for k, v in (options.get("env") or {}).items()},
            quality_steps={str(key): int(value) for key, value in steps.items()},
            model_id=str(config.model.id or "sd-pixl"),
        )

    def steps_for(self, quality: QualityLevel | str) -> int:
        key = quality.value if isinstance(quality, QualityLevel) else str(quality)
        return int(self.quality_steps.get(key, DEFAULT_QUALITY_STEPS["standard"]))
