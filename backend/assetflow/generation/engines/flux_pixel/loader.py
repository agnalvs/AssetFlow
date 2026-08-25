"""Carregamento do pipeline FLUX + LoRA.

**Único módulo desta gaveta autorizado a importar ``torch`` e ``diffusers``**
— e, mesmo aqui, os imports são tardios, dentro das funções. O backend precisa
subir, listar motores e responder health check em uma máquina que não tem
nenhuma dessas bibliotecas instaladas.

O mesmo desenho da gaveta SDXL, e de propósito: as duas resolvem o mesmo
problema (carregar um pipeline pesado sem penalizar o boot) e a semelhança
torna a comparação entre elas legível. O que **não** acontece é uma importar a
outra — cada gaveta é independente, e o teste de fronteiras cobra isso.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from typing import Any

from ....generation.kernel.exceptions import EngineInitializationError
from .config import FluxPixelConfig

__all__ = [
    "LoadedFluxPipeline",
    "dependencies_available",
    "describe_runtime",
    "load_pipeline",
    "release",
]

_LOG = logging.getLogger("assetflow.engine.flux_pixel")
_ENGINE_ID = "flux-pixel-v1"

_REQUIRED_MODULES = ("torch", "diffusers", "transformers")


@dataclass(slots=True)
class LoadedFluxPipeline:
    """Pipeline carregado + o que precisa ir para o relatório."""

    pipeline: Any
    device: str
    dtype: str
    offloaded: bool
    #: LoRA efetivamente aplicada. ``None`` quando não havia ou quando falhou
    #: de forma tolerável — e nesse caso ``lora_error`` diz o que aconteceu.
    lora_id: str | None = None
    lora_error: str | None = None


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
    """Informação de hardware para o health check (plano §43)."""
    available, detail = dependencies_available()
    if not available:
        return {"available": False, "detail": detail, "gpu_available": False}

    try:
        import torch
    except Exception as exc:  # pragma: no cover - ambiente quebrado
        return {
            "available": False,
            "detail": f"falha ao importar torch: {exc}",
            "gpu_available": False,
        }

    cuda = bool(torch.cuda.is_available())
    info: dict[str, Any] = {
        "available": True,
        "detail": None,
        "gpu_available": cuda,
        "torch_version": torch.__version__,
        "peft_installed": importlib.util.find_spec("peft") is not None,
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
    """Precisão efetiva. CPU sempre em fp32; o padrão do FLUX é bf16."""
    import torch

    if device == "cpu":
        return torch.float32
    return {
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
        "fp32": torch.float32,
    }.get(precision, torch.bfloat16)


def load_pipeline(config: FluxPixelConfig) -> LoadedFluxPipeline:
    """Carrega o FLUX e aplica a LoRA de Pixel Art.

    Raises:
        EngineInitializationError: dependência ausente ou falha ao carregar o
            **modelo-base** — sempre traduzido para o vocabulário de erros do
            AssetFlow, com o id que foi tentado.

    Falha ao aplicar a **LoRA** não derruba a inicialização: o motor continua
    utilizável, o erro fica registrado em ``lora_error`` e vira aviso no
    resultado. A alternativa — recusar o motor inteiro porque um adaptador de
    algumas dezenas de MB não baixou — trocaria uma degradação visível por uma
    indisponibilidade total.
    """
    available, detail = dependencies_available()
    if not available:
        raise EngineInitializationError(
            detail or "dependências ausentes", engine_id=_ENGINE_ID
        )

    try:
        import torch  # noqa: F401  (usado por resolve_device/resolve_dtype)
        from diffusers import FluxPipeline
    except Exception as exc:  # pragma: no cover - ambiente quebrado
        raise EngineInitializationError(
            f"falha ao importar diffusers: {exc}", engine_id=_ENGINE_ID
        ) from exc

    device = resolve_device(config.device)
    dtype = resolve_dtype(config.precision, device)

    kwargs: dict[str, Any] = {"torch_dtype": dtype}
    if config.revision:
        kwargs["revision"] = config.revision
    if config.variant and device != "cpu":
        kwargs["variant"] = config.variant
    if config.cache_dir:
        kwargs["cache_dir"] = config.cache_dir

    _LOG.info(
        "carregando FLUX '%s' (device=%s, dtype=%s)", config.model_id, device, dtype
    )
    try:
        pipeline = FluxPipeline.from_pretrained(config.model_id, **kwargs)
    except Exception as exc:
        raise EngineInitializationError(
            f"não foi possível carregar '{config.model_id}': {exc} — confira "
            "`engines.yaml > flux-pixel-v1 > model.id`",
            engine_id=_ENGINE_ID,
            detail={"model_id": config.model_id, "cause": repr(exc)},
        ) from exc

    lora_id, lora_error = _apply_lora(pipeline, config)

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

        if config.enable_attention_slicing and hasattr(pipeline, "enable_attention_slicing"):
            pipeline.enable_attention_slicing()
        if config.enable_vae_slicing and hasattr(pipeline, "enable_vae_slicing"):
            pipeline.enable_vae_slicing()
        pipeline.set_progress_bar_config(disable=True)
    except Exception as exc:  # pragma: no cover - depende de hardware
        raise EngineInitializationError(
            f"falha ao preparar o pipeline FLUX: {exc}", engine_id=_ENGINE_ID
        ) from exc

    return LoadedFluxPipeline(
        pipeline=pipeline,
        device=device,
        dtype=str(dtype),
        offloaded=offloaded,
        lora_id=lora_id,
        lora_error=lora_error,
    )


def _apply_lora(pipeline: Any, config: FluxPixelConfig) -> tuple[str | None, str | None]:
    """Aplica a LoRA, devolvendo ``(lora_aplicada, erro)``."""
    if not config.lora_id:
        return None, None

    kwargs: dict[str, Any] = {}
    if config.lora_weight_name:
        kwargs["weight_name"] = config.lora_weight_name
    if config.cache_dir:
        kwargs["cache_dir"] = config.cache_dir

    try:
        pipeline.load_lora_weights(config.lora_id, **kwargs)
        if config.lora_scale != 1.0 and hasattr(pipeline, "fuse_lora"):
            pipeline.fuse_lora(lora_scale=config.lora_scale)
        _LOG.info("LoRA '%s' aplicada (escala=%s)", config.lora_id, config.lora_scale)
        return config.lora_id, None
    except Exception as exc:
        message = f"não foi possível aplicar a LoRA '{config.lora_id}': {exc}"
        _LOG.warning("%s — seguindo com o modelo-base", message)
        return None, message


def release(loaded: LoadedFluxPipeline | None) -> None:
    """Libera VRAM (plano §37 e §38)."""
    if loaded is None:
        return
    try:
        import torch

        del loaded.pipeline
        if torch.cuda.is_available():  # pragma: no cover - depende de hardware
            torch.cuda.empty_cache()
    except Exception:  # pragma: no cover - defensivo
        _LOG.debug("falha ao liberar recursos do FLUX", exc_info=True)
