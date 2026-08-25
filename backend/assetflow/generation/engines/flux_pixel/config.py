"""Configuração tipada da gaveta `flux-pixel-v1` (plano §65; plano de motores §8.1).

Tudo que é específico do FLUX vive aqui: id do modelo, LoRA, escala da LoRA,
passos por nível de qualidade, guidance. Nada disso aparece no contrato
universal do AssetFlow — lá existe apenas ``quality``, e é este arquivo que o
traduz.

Sobre o id do modelo e o da LoRA
--------------------------------
Os padrões abaixo são os nomes que o plano cita. Eles ficam em
``config/engines.yaml``, e é lá que devem ser conferidos antes de habilitar a
gaveta: um repositório do HuggingFace pode mudar de nome ou de organização, e
um id errado aparece como falha de download no primeiro job, não no boot.
Por isso a mensagem de erro do loader diz exatamente qual id ele tentou.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ....generation.schemas import EngineRuntimeConfig, QualityLevel

__all__ = ["FluxPixelConfig", "DEFAULT_QUALITY_STEPS", "ADAPTER_VERSION"]

#: Versão do **adapter** — o código desta pasta, não o modelo (plano de motores §18).
#: Sobe quando a tradução AssetFlow → FLUX muda de comportamento, mesmo que o
#: modelo continue o mesmo: é o que permite explicar, meses depois, por que
#: duas gerações do mesmo modelo saíram diferentes.
ADAPTER_VERSION = "1.0.0"

#: FLUX-klein é destilado para poucos passos; 28 seria desperdício de tempo.
DEFAULT_QUALITY_STEPS: dict[str, int] = {
    QualityLevel.DRAFT.value: 4,
    QualityLevel.STANDARD.value: 8,
    QualityLevel.HIGH.value: 16,
}


@dataclass(frozen=True, slots=True)
class FluxPixelConfig:
    """Opções desta gaveta, derivadas de ``config/engines.yaml``."""

    model_id: str = "black-forest-labs/FLUX.2-klein-4B"
    revision: str | None = None
    variant: str | None = None
    device: str = "auto"
    precision: str = "bf16"
    cache_dir: str | None = None

    #: LoRA de Pixel Art aplicada sobre o modelo-base (plano de motores §2.1).
    lora_id: str | None = "Limbicnation/pixel-art-lora"
    #: Nome do arquivo de pesos dentro do repositório, quando ele tiver mais
    #: de um. ``None`` deixa o Diffusers escolher.
    lora_weight_name: str | None = None
    lora_scale: float = 1.0
    #: Palavra-chave de ativação da LoRA, quando ela tiver uma. Entra no
    #: prompt pelo adapter — nunca no contrato universal.
    lora_trigger: str | None = "pixel art"

    enable_attention_slicing: bool = True
    enable_vae_slicing: bool = True
    enable_model_cpu_offload: bool = False
    enable_sequential_cpu_offload: bool = False

    guidance_scale: float = 3.5
    max_sequence_length: int = 256
    quality_steps: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_QUALITY_STEPS)
    )

    @classmethod
    def from_runtime(cls, config: EngineRuntimeConfig) -> "FluxPixelConfig":
        options = config.options or {}
        runtime = config.runtime or {}
        steps = {**DEFAULT_QUALITY_STEPS, **(options.get("quality_steps") or {})}
        lora = options.get("lora") or {}

        return cls(
            model_id=config.model.id or cls.model_id,
            revision=config.model.revision,
            variant=config.model.variant,
            device=config.device.type or "auto",
            precision=config.precision.type or "bf16",
            cache_dir=config.workspace_dir,
            # `lora: {id: null}` é uma configuração válida e significativa:
            # rodar o FLUX cru, sem LoRA, para comparar o efeito dela.
            lora_id=lora.get("id", cls.lora_id),
            lora_weight_name=lora.get("weight_name"),
            lora_scale=float(lora.get("scale", 1.0)),
            lora_trigger=lora.get("trigger", cls.lora_trigger),
            enable_attention_slicing=bool(runtime.get("enable_attention_slicing", True)),
            enable_vae_slicing=bool(runtime.get("enable_vae_slicing", True)),
            enable_model_cpu_offload=bool(runtime.get("enable_model_cpu_offload", False)),
            enable_sequential_cpu_offload=bool(
                runtime.get("enable_sequential_cpu_offload", False)
            ),
            guidance_scale=float(options.get("guidance_scale", 3.5)),
            max_sequence_length=int(options.get("max_sequence_length", 256)),
            quality_steps={str(key): int(value) for key, value in steps.items()},
        )

    def steps_for(self, quality: QualityLevel | str) -> int:
        key = quality.value if isinstance(quality, QualityLevel) else str(quality)
        return int(self.quality_steps.get(key, DEFAULT_QUALITY_STEPS["standard"]))
