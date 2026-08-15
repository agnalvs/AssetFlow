"""Configuração tipada da gaveta `diffusers-sdxl-v1` (plano §65).

Tudo que é específico desta tecnologia — dtype, offloading, passos de
inferência, guidance — vive aqui dentro. Nenhuma dessas chaves aparece no
contrato universal do AssetFlow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ....generation.schemas import EngineRuntimeConfig, QualityLevel

__all__ = ["SDXLConfig", "DEFAULT_QUALITY_STEPS"]

#: Tradução do knob abstrato `quality` para passos de inferência (plano §20).
DEFAULT_QUALITY_STEPS: dict[str, int] = {
    QualityLevel.DRAFT.value: 18,
    QualityLevel.STANDARD.value: 30,
    QualityLevel.HIGH.value: 45,
}


@dataclass(frozen=True, slots=True)
class SDXLConfig:
    """Opções desta gaveta, derivadas de ``config/engines.yaml``."""

    model_id: str = "stabilityai/stable-diffusion-xl-base-1.0"
    revision: str | None = None
    variant: str | None = "fp16"
    device: str = "auto"
    precision: str = "fp16"
    cache_dir: str | None = None

    enable_attention_slicing: bool = True
    enable_vae_slicing: bool = True
    enable_model_cpu_offload: bool = False
    enable_sequential_cpu_offload: bool = False

    guidance_scale: float = 6.5
    quality_steps: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_QUALITY_STEPS))

    @classmethod
    def from_runtime(cls, config: EngineRuntimeConfig) -> "SDXLConfig":
        options = config.options or {}
        runtime = config.runtime or {}
        steps = {**DEFAULT_QUALITY_STEPS, **(options.get("quality_steps") or {})}

        return cls(
            model_id=config.model.id or cls.model_id,
            revision=config.model.revision,
            variant=config.model.variant,
            device=config.device.type or "auto",
            precision=config.precision.type or "fp16",
            cache_dir=config.workspace_dir,
            enable_attention_slicing=bool(runtime.get("enable_attention_slicing", True)),
            enable_vae_slicing=bool(runtime.get("enable_vae_slicing", True)),
            enable_model_cpu_offload=bool(runtime.get("enable_model_cpu_offload", False)),
            enable_sequential_cpu_offload=bool(
                runtime.get("enable_sequential_cpu_offload", False)
            ),
            guidance_scale=float(options.get("guidance_scale", 6.5)),
            quality_steps={str(key): int(value) for key, value in steps.items()},
        )

    def steps_for(self, quality: QualityLevel | str) -> int:
        key = quality.value if isinstance(quality, QualityLevel) else str(quality)
        return int(self.quality_steps.get(key, DEFAULT_QUALITY_STEPS["standard"]))
