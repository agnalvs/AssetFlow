"""Descoberta e carregamento de gavetas (planos §63 e §64).

Uma gaveta é encontrada pelo seu ``manifest.json``, não por um ``import``
escrito à mão em algum lugar do sistema. É isso que permite acrescentar ou
remover motores sem tocar no código do AssetFlow.

Segurança (plano §64): a instalação dinâmica de plugins ainda não existe, mas
o carregamento já é restrito por:

- *allowlist* de ``engine_id`` vinda da configuração;
- prefixo de módulo permitido para o ``entrypoint``;
- validação estrita do manifesto antes de qualquer import.

Nenhum código arbitrário enviado por usuário é executado.
"""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from ..schemas import EngineManifest
from .contracts import EngineFactory, ImageGenerationEngine
from .exceptions import EngineIncompatible, EngineNotFound

__all__ = [
    "DiscoveredEngine",
    "DEFAULT_ENTRYPOINT_PREFIXES",
    "discover_manifests",
    "load_engine_class",
    "build_factory",
]

_LOG = logging.getLogger("assetflow.generation.discovery")

#: Prefixos de módulo aceitos para o ``entrypoint`` de um manifesto.
DEFAULT_ENTRYPOINT_PREFIXES: tuple[str, ...] = ("assetflow.generation.engines.",)


@dataclass(frozen=True, slots=True)
class DiscoveredEngine:
    """Um manifesto encontrado no disco, ainda não registrado."""

    manifest: EngineManifest
    source: Path


def discover_manifests(
    paths: Iterable[Path],
    *,
    allowlist: Sequence[str] | None = None,
    manifest_name: str = "manifest.json",
) -> list[DiscoveredEngine]:
    """Varre diretórios em busca de manifestos de gaveta.

    Args:
        paths: diretórios raiz (ex.: ``assetflow/generation/engines``).
        allowlist: se informado, apenas estes ``engine_id`` são aceitos.
        manifest_name: nome do arquivo de manifesto.

    Returns:
        Lista ordenada por ``engine_id``. Manifestos inválidos são ignorados
        com log de aviso — uma gaveta quebrada nunca derruba o sistema.
    """
    allowed = set(allowlist) if allowlist is not None else None
    found: dict[str, DiscoveredEngine] = {}

    for root in paths:
        root = Path(root)
        if not root.exists():
            _LOG.warning("caminho de descoberta inexistente: %s", root)
            continue

        for manifest_path in sorted(root.rglob(manifest_name)):
            try:
                with manifest_path.open("r", encoding="utf-8") as handle:
                    manifest = EngineManifest.model_validate(json.load(handle))
            except Exception as exc:
                _LOG.error("manifesto inválido em %s: %s", manifest_path, exc)
                continue

            if allowed is not None and manifest.id not in allowed:
                _LOG.info(
                    "gaveta '%s' ignorada: fora da allowlist de segurança", manifest.id
                )
                continue

            if manifest.id in found:
                _LOG.warning(
                    "gaveta '%s' duplicada; mantendo %s e ignorando %s",
                    manifest.id,
                    found[manifest.id].source,
                    manifest_path,
                )
                continue

            found[manifest.id] = DiscoveredEngine(manifest=manifest, source=manifest_path)

    return [found[key] for key in sorted(found)]


def load_engine_class(
    entrypoint: str,
    *,
    allowed_prefixes: Sequence[str] = DEFAULT_ENTRYPOINT_PREFIXES,
) -> type[ImageGenerationEngine]:
    """Importa a classe da gaveta a partir de ``pacote.modulo:Classe``.

    Este é o **único** lugar do sistema autorizado a importar um engine
    concreto. Todas as demais camadas passam pelo registry/resolver.
    """
    module_name, _, class_name = entrypoint.partition(":")
    if not module_name or not class_name:
        raise EngineNotFound(f"entrypoint inválido: {entrypoint!r}")

    if allowed_prefixes and not any(
        module_name.startswith(prefix) for prefix in allowed_prefixes
    ):
        raise EngineIncompatible(
            f"entrypoint {entrypoint!r} fora dos prefixos permitidos {tuple(allowed_prefixes)}"
        )

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise EngineNotFound(
            f"não foi possível importar o módulo '{module_name}': {exc}",
            detail={"entrypoint": entrypoint},
        ) from exc

    engine_class = getattr(module, class_name, None)
    if engine_class is None:
        raise EngineNotFound(f"classe '{class_name}' não encontrada em '{module_name}'")

    if not (isinstance(engine_class, type) and issubclass(engine_class, ImageGenerationEngine)):
        raise EngineIncompatible(
            f"'{entrypoint}' não implementa ImageGenerationEngine — "
            "toda gaveta precisa obedecer ao Engine Contract"
        )

    return engine_class


def build_factory(
    manifest: EngineManifest,
    *,
    allowed_prefixes: Sequence[str] = DEFAULT_ENTRYPOINT_PREFIXES,
) -> EngineFactory:
    """Cria a factory preguiçosa usada pelo registry.

    O import só acontece na primeira instanciação: um motor pesado que exija
    ``torch`` não penaliza o boot da API nem quebra a listagem de engines
    quando a dependência não está instalada.
    """

    def factory() -> ImageGenerationEngine:
        engine_class = load_engine_class(manifest.entrypoint, allowed_prefixes=allowed_prefixes)
        return engine_class()

    return factory
