"""Execução do binário Rust do Pixel Forge.

Uma nota sobre a duplicação com ``sdpixl/bridge.py``: as duas pontes fazem
coisas parecidas — rodar um processo, esperar, ler PNGs — e mesmo assim são
arquivos separados, sem nada compartilhado entre elas.

Isso é a regra 3 do teste de fronteiras (``tests/test_architecture_boundaries``):
**uma gaveta não importa outra gaveta**. Um módulo comum entre as duas as
acorrentaria: mudar o tratamento de timeout do SD-πXL, que pode levar horas,
passaria a mexer no Pixel Forge, que responde em segundos. O custo de repetir
umas dezenas de linhas é menor do que o de acoplar duas tecnologias que não
têm nada a ver uma com a outra.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ....generation.kernel.exceptions import (
    EngineExecutionError,
    EngineTimeoutError,
    GenerationCancelled,
)

__all__ = ["ForgeResult", "binary_available", "render_args", "run_forge"]

_LOG = logging.getLogger("assetflow.engine.pixel_forge")
_ENGINE_ID = "pixel-forge-v1"
_TERMINATE_GRACE_S = 3.0


@dataclass(slots=True)
class ForgeResult:
    """O que o binário produziu."""

    images: tuple[bytes, ...]
    stdout: str
    stderr: str
    duration_ms: float


def binary_available(binary: str, working_dir: str | None) -> str | None:
    """Diz por que o binário não roda, ou ``None`` se ele roda."""
    if not binary:
        return (
            "Pixel Forge não configurado: aponte `options.binary` em "
            "engines.yaml para o executável compilado do projeto"
        )
    if working_dir and not Path(working_dir).is_dir():
        return f"diretório de trabalho inexistente: {working_dir}"

    path = Path(binary)
    if path.is_absolute() or path.parent != Path("."):
        if not path.exists():
            return f"binário não encontrado: {binary}"
        return None
    if shutil.which(binary) is None:
        return f"binário '{binary}' não está no PATH"
    return None


def render_args(args: tuple[str, ...], values: Mapping[str, object]) -> list[str]:
    """Substitui placeholders por argumento já separado.

    Como na outra ponte, a substituição acontece depois de o ``argv`` estar
    separado — nunca antes, e nunca através de um shell. Um prompt com aspas é
    um argumento com aspas, e não um comando novo (plano §64).
    """
    rendered: list[str] = []
    for argument in args:
        text = argument
        for key, value in values.items():
            token = "{" + key + "}"
            if token in text:
                text = text.replace(token, "" if value is None else str(value))
        rendered.append(text)
    return rendered


async def run_forge(
    command: list[str],
    *,
    working_dir: str | None,
    output_dir: Path,
    output_glob: str,
    timeout_s: float,
    env: Mapping[str, str],
    cancellation,
) -> ForgeResult:
    """Roda o binário, aguarda e recolhe os PNGs produzidos."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    process_env = {**os.environ, **env}

    _LOG.info("Pixel Forge: executando %s", " ".join(command))
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=working_dir,
            env=process_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise EngineExecutionError(
            f"não foi possível executar '{command[0]}': {exc}", engine_id=_ENGINE_ID
        ) from exc
    except OSError as exc:
        raise EngineExecutionError(
            f"falha ao iniciar o Pixel Forge: {exc}", engine_id=_ENGINE_ID
        ) from exc

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout_s
        )
    except asyncio.TimeoutError as exc:
        await _kill(process)
        raise EngineTimeoutError(
            f"Pixel Forge excedeu {timeout_s:.0f}s", engine_id=_ENGINE_ID
        ) from exc
    except asyncio.CancelledError:  # pragma: no cover - shutdown
        await _kill(process)
        raise

    if cancellation is not None and cancellation.is_cancelled:
        raise GenerationCancelled("cancelamento solicitado durante o Pixel Forge")

    duration_ms = (loop.time() - started) * 1000.0
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")

    if process.returncode != 0:
        raise EngineExecutionError(
            f"Pixel Forge terminou com código {process.returncode}",
            engine_id=_ENGINE_ID,
            detail={"stderr": err[-2000:], "command": command},
        )

    images = _collect_images(output_dir, output_glob)
    if not images:
        raise EngineExecutionError(
            f"Pixel Forge terminou sem produzir imagem em {output_dir} "
            f"(padrão '{output_glob}')",
            engine_id=_ENGINE_ID,
            detail={"stdout": out[-2000:], "stderr": err[-2000:]},
        )

    return ForgeResult(images=images, stdout=out, stderr=err, duration_ms=duration_ms)


async def _kill(process) -> None:
    if process.returncode is not None:
        return
    try:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=_TERMINATE_GRACE_S)
    except (asyncio.TimeoutError, ProcessLookupError):  # pragma: no cover
        try:
            process.kill()
        except ProcessLookupError:
            pass
    except Exception:  # pragma: no cover - defensivo
        _LOG.debug("falha ao encerrar o Pixel Forge", exc_info=True)


def _collect_images(output_dir: Path, pattern: str) -> tuple[bytes, ...]:
    if not output_dir.is_dir():
        return ()
    images: list[bytes] = []
    for path in sorted(output_dir.glob(pattern)):
        try:
            images.append(path.read_bytes())
        except OSError as exc:  # pragma: no cover - defensivo
            _LOG.warning("não foi possível ler %s: %s", path, exc)
    return tuple(images)
