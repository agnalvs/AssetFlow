"""Carregamento do pipeline Diffusers.

**Este é o único módulo do AssetFlow autorizado a importar ``torch`` e
``diffusers``** — e mesmo aqui os imports são tardios, dentro das funções.

Motivos:

- o backend sobe (e lista motores) mesmo sem as dependências pesadas;
- a API não paga o custo de importar torch;
- lazy loading de verdade: o modelo só entra na GPU no primeiro job (§36).
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from typing import Any

from ....generation.kernel.exceptions import EngineInitializationError
from .config import SDXLConfig

__all__ = ["LoadedPipeline", "dependencies_available", "describe_runtime", "load_pipeline"]

_LOG = logging.getLogger("assetflow.engine.diffusers_sdxl")

_REQUIRED_MODULES = ("torch", "diffusers", "transformers")


@dataclass(slots=True)
class LoadedPipeline:
    """Pipeline carregado + informação de runtime para observabilidade."""

    pipeline: Any
    device: str
    dtype: str
    offloaded: bool


def dependencies_available() -> tuple[bool, str | None]:
    """Verifica as dependências **sem importá-las**."""
    missing = [name for name in _REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if missing:
        return False, (
            "dependências ausentes: "
            + ", ".join(missing)
            + " — instale com `pip install -e .[diffusers]`"
        )
    return True, None


def describe_runtime() -> dict[str, Any]:
    """Informação de hardware para o health check (importa torch se existir)."""
    available, detail = dependencies_available()
    if not available:
        return {"available": False, "detail": detail, "gpu_available": False}

    try:
        import torch
    except Exception as exc:  # pragma: no cover - ambiente quebrado
        return {"available": False, "detail": f"falha ao importar torch: {exc}", "gpu_available": False}

    cuda = bool(torch.cuda.is_available())
    info: dict[str, Any] = {
        "available": True,
        "detail": None,
        "gpu_available": cuda,
        "torch_version": torch.__version__,
    }
    if cuda:  # pragma: no cover - depende de hardware
        index = torch.cuda.current_device()
        info["gpu_name"] = torch.cuda.get_device_name(index)
        info["vram_total_mb"] = int(
            torch.cuda.get_device_properties(index).total_memory / (1024 * 1024)
        )
    return info


def resolve_device(requested: str) -> str:
    """``auto`` -> melhor dispositivo disponível."""
    import torch

    if requested and requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def resolve_dtype(precision: str, device: str):
    """Precisão efetiva; CPU sempre roda em fp32."""
    import torch

    if device == "cpu":
        return torch.float32
    return {
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
        "fp32": torch.float32,
    }.get(precision, torch.float16)


def load_pipeline(config: SDXLConfig) -> LoadedPipeline:
    """Carrega o SDXL conforme a configuração externa.

    Raises:
        EngineInitializationError: dependências ausentes ou falha de carga —
            sempre traduzido para o vocabulário de erros do AssetFlow.
    """
    available, detail = dependencies_available()
    if not available:
        raise EngineInitializationError(detail or "dependências ausentes", engine_id="diffusers-sdxl-v1")

    try:
        import torch  # noqa: F401  (usado por resolve_device/resolve_dtype)
        from diffusers import StableDiffusionXLPipeline
    except Exception as exc:  # pragma: no cover - ambiente quebrado
        raise EngineInitializationError(
            f"falha ao importar diffusers: {exc}", engine_id="diffusers-sdxl-v1"
        ) from exc

    device = resolve_device(config.device)
    dtype = resolve_dtype(config.precision, device)

    kwargs: dict[str, Any] = {"torch_dtype": dtype, "use_safetensors": True}
    if config.revision:
        kwargs["revision"] = config.revision
    if config.variant and device != "cpu":
        kwargs["variant"] = config.variant
    if config.cache_dir:
        kwargs["cache_dir"] = config.cache_dir

    _LOG.info(
        "carregando SDXL '%s' (device=%s, dtype=%s)", config.model_id, device, dtype
    )
    try:
        pipeline = StableDiffusionXLPipeline.from_pretrained(config.model_id, **kwargs)
    except Exception as exc:
        raise EngineInitializationError(
            f"não foi possível carregar '{config.model_id}': {exc}",
            engine_id="diffusers-sdxl-v1",
            detail={"cause": repr(exc)},
        ) from exc

    offloaded = False
    try:
        if config.enable_sequential_cpu_offload:
            pipeline.enable_sequential_cpu_offload()
            offloaded = True
        elif config.enable_model_cpu_offload:
            pipeline.enable_model_cpu_offload()
            offloaded = True
        else:
            pipeline.to(device)

        if config.enable_attention_slicing:
            pipeline.enable_attention_slicing()
        if config.enable_vae_slicing and hasattr(pipeline, "enable_vae_slicing"):
            pipeline.enable_vae_slicing()
        pipeline.set_progress_bar_config(disable=True)
    except Exception as exc:  # pragma: no cover - depende de hardware
        raise EngineInitializationError(
            f"falha ao preparar o pipeline: {exc}", engine_id="diffusers-sdxl-v1"
        ) from exc

    return LoadedPipeline(
        pipeline=pipeline, device=device, dtype=str(dtype), offloaded=offloaded
    )


def release(loaded: LoadedPipeline | None) -> None:
    """Libera VRAM (plano §37/§38)."""
    if loaded is None:
        return
    try:
        import torch

        del loaded.pipeline
        if torch.cuda.is_available():  # pragma: no cover - depende de hardware
            torch.cuda.empty_cache()
    except Exception:  # pragma: no cover - defensivo
        _LOG.debug("falha ao liberar recursos do SDXL", exc_info=True)
