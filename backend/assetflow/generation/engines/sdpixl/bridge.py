"""Execução do processo externo do SD-πXL.

Este módulo é a fronteira: acima dele o AssetFlow, abaixo dele um processo de
terceiro que pode demorar horas, escrever em disco e falhar de formas que não
temos como prever. Tudo que ele produz é traduzido para o vocabulário de erros
do AssetFlow antes de subir.

Três cuidados que não são opcionais aqui:

* **``create_subprocess_exec``, nunca ``shell=True``.** O prompt vem de quem
  usa o sistema; passá-lo por um shell seria injeção de comando com passos
  extras (plano §64).
* **Cancelamento mata o processo.** Um job cancelado que deixa um processo de
  duas horas rodando na máquina não foi cancelado.
* **Nada de reencode.** Os PNGs voltam como o projeto os escreveu; comparar
  motores exige comparar a saída real deles (plano Pixel §71).
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

__all__ = ["BridgeResult", "command_available", "render_command", "run_command"]

_LOG = logging.getLogger("assetflow.engine.sdpixl")
_ENGINE_ID = "sdpixl-v1"

#: Quanto esperar o processo morrer depois do pedido educado, antes de matar.
_TERMINATE_GRACE_S = 5.0


@dataclass(slots=True)
class BridgeResult:
    """O que o processo externo produziu."""

    images: tuple[bytes, ...]
    stdout: str
    stderr: str
    duration_ms: float


def command_available(command: tuple[str, ...], working_dir: str | None) -> str | None:
    """Diz por que o comando não roda, ou ``None`` se ele roda.

    Verifica **sem executar**: o health check é chamado com frequência e
    precisa ser barato. Executar o SD-πXL para saber se ele existe custaria
    horas por consulta.
    """
    if not command:
        return (
            "SD-πXL não configurado: defina `options.command` em engines.yaml "
            "apontando para a CLI do projeto"
        )
    if working_dir and not Path(working_dir).is_dir():
        return f"diretório de trabalho inexistente: {working_dir}"

    executable = command[0]
    if Path(executable).is_absolute():
        if not Path(executable).exists():
            return f"executável não encontrado: {executable}"
        return None
    if shutil.which(executable) is None:
        return f"executável '{executable}' não está no PATH"
    return None


def render_command(
    command: tuple[str, ...], values: Mapping[str, object]
) -> list[str]:
    """Substitui os placeholders de cada argumento, um a um.

    A substituição é feita **por argumento já separado**, e é isso que a torna
    segura: um prompt com espaços, aspas ou ``;`` continua sendo um único
    argumento do ``argv``, porque nunca passa por um shell.

    Um placeholder desconhecido é deixado como está, em vez de estourar: o
    comando é escrito por quem administra a instalação, e uma chave a mais no
    template não deve derrubar o backend.
    """
    rendered: list[str] = []
    for argument in command:
        text = argument
        for key, value in values.items():
            token = "{" + key + "}"
            if token in text:
                text = text.replace(token, "" if value is None else str(value))
        rendered.append(text)
    return rendered


async def run_command(
    command: list[str],
    *,
    working_dir: str | None,
    output_dir: Path,
    output_glob: str,
    timeout_s: float,
    env: Mapping[str, str],
    cancellation,
) -> BridgeResult:
    """Roda o processo, aguarda e recolhe os PNGs produzidos."""
    loop = asyncio.get_running_loop()
    started = loop.time()

    process_env = {**os.environ, **env}
    _LOG.info("SD-πXL: executando %s", " ".join(command))

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
            f"não foi possível executar '{command[0]}': {exc}",
            engine_id=_ENGINE_ID,
        ) from exc
    except OSError as exc:
        raise EngineExecutionError(
            f"falha ao iniciar o SD-πXL: {exc}", engine_id=_ENGINE_ID
        ) from exc

    waiter = asyncio.ensure_future(process.communicate())
    try:
        stdout, stderr = await _wait_with_cancellation(
            waiter, process, timeout_s=timeout_s, cancellation=cancellation
        )
    finally:
        if not waiter.done():  # pragma: no cover - só em cancelamento
            waiter.cancel()

    duration_ms = (loop.time() - started) * 1000.0
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")

    if process.returncode != 0:
        raise EngineExecutionError(
            f"SD-πXL terminou com código {process.returncode}",
            engine_id=_ENGINE_ID,
            # O stderr é cortado: ele pode ter megabytes de barra de progresso,
            # e o que interessa para diagnosticar está sempre no fim.
            detail={"stderr": err[-2000:], "command": command},
        )

    images = _collect_images(output_dir, output_glob)
    if not images:
        raise EngineExecutionError(
            f"SD-πXL terminou sem produzir imagem em {output_dir} "
            f"(padrão '{output_glob}')",
            engine_id=_ENGINE_ID,
            detail={"stdout": out[-2000:], "stderr": err[-2000:]},
        )

    return BridgeResult(
        images=images, stdout=out, stderr=err, duration_ms=duration_ms
    )


async def _wait_with_cancellation(
    waiter, process, *, timeout_s: float, cancellation
) -> tuple[bytes, bytes]:
    """Aguarda o processo, checando cancelamento e teto de tempo.

    O laço acorda de segundo em segundo em vez de simplesmente aguardar o
    processo: é o que permite reagir a um cancelamento pedido no meio de uma
    execução de horas, em vez de descobrir o pedido só quando ela terminar.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s

    while True:
        if cancellation is not None and cancellation.is_cancelled:
            await _kill(process)
            raise GenerationCancelled("cancelamento solicitado durante o SD-πXL")

        remaining = deadline - loop.time()
        if remaining <= 0:
            await _kill(process)
            raise EngineTimeoutError(
                f"SD-πXL excedeu {timeout_s:.0f}s", engine_id=_ENGINE_ID
            )

        try:
            return await asyncio.wait_for(
                asyncio.shield(waiter), timeout=min(1.0, remaining)
            )
        except asyncio.TimeoutError:
            continue


async def _kill(process) -> None:
    """Encerra o processo externo, com um pedido educado antes do tiro."""
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
        _LOG.debug("falha ao encerrar o processo do SD-πXL", exc_info=True)


def _collect_images(output_dir: Path, pattern: str) -> tuple[bytes, ...]:
    """Lê os PNGs produzidos, na ordem do nome do arquivo."""
    if not output_dir.is_dir():
        return ()
    images: list[bytes] = []
    for path in sorted(output_dir.glob(pattern)):
        try:
            images.append(path.read_bytes())
        except OSError as exc:  # pragma: no cover - defensivo
            _LOG.warning("não foi possível ler %s: %s", path, exc)
    return tuple(images)
