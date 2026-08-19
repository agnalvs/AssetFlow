"""Registro dos valores concretos dos profiles Pixel (§64 e §65).

O plano Pixel §64 é categórico: resolução lógica, quantidade de cores, limiar
de alpha, escala de preview e limiar de qualidade são **configuração**. Um
profile novo (§66) precisa entrar editando ``config/pixel_profiles.yaml`` e
nada mais — se alguém precisar abrir um ``.py`` para acrescentar um tamanho de
sprite, a regra já foi quebrada.

Este registro é a porta de entrada desses valores:

    ``config/pixel_profiles.yaml``  ->  ``PixelProfileRegistry``  ->  ``PixelOutputSpec``

Ele também resolve o modo PROJECT de paleta (§11): um profile pede
``palette_id: forest_world_v1`` e sai daqui com uma paleta LOCKED concreta,
para que personagem, inimigo e tile do mesmo mundo compartilhem exatamente as
mesmas cores.

Um profile inválido é **ignorado com log de erro**, nunca derruba o boot — a
mesma decisão do ``ProfileRegistry`` de geração: um erro de digitação em um
profile experimental não pode impedir o backend inteiro de subir.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from ..contracts.output_spec import PixelOutputSpec, normalize_hex

__all__ = ["PixelProfileRegistry"]

_LOG = logging.getLogger("assetflow.pixel.profiles")


class PixelProfileRegistry:
    """Coleção de :class:`PixelOutputSpec` + a tabela de paletas do projeto."""

    def __init__(
        self,
        profiles: Iterable[PixelOutputSpec] = (),
        palettes: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self._profiles: dict[str, PixelOutputSpec] = {spec.id: spec for spec in profiles}
        self._palettes: dict[str, tuple[str, ...]] = {
            palette_id: tuple(colors)
            for palette_id, colors in sorted((palettes or {}).items())
        }

    @classmethod
    def from_config(cls, data: dict[str, Any]) -> PixelProfileRegistry:
        """Constrói a partir do dicionário lido de ``pixel_profiles.yaml``.

        As paletas são carregadas primeiro de propósito: ``resolve`` precisa
        delas para transformar um profile PROJECT em LOCKED ainda no boot, e
        não no meio de um job.
        """
        registry = cls(palettes=_load_palettes(data.get("palettes")))
        for profile_id, raw in (data.get("pixel_profiles") or {}).items():
            try:
                # O ``id`` vem depois do ``**raw``: a chave do YAML é a
                # identidade usada por ``get()``, e um campo ``id`` divergente
                # dentro do bloco tornaria o profile inalcançável.
                spec = PixelOutputSpec.model_validate({**raw, "id": profile_id})
            except (TypeError, ValidationError) as exc:
                _LOG.error("profile pixel '%s' inválido e ignorado: %s", profile_id, exc)
                continue
            registry.register(registry.resolve(spec))
        return registry

    # ------------------------------------------------------------------
    def register(self, spec: PixelOutputSpec) -> PixelOutputSpec:
        self._profiles[spec.id] = spec
        return spec

    def get(self, profile_id: str) -> PixelOutputSpec:
        spec = self._profiles.get(profile_id)
        if spec is None:
            disponiveis = ", ".join(self.ids()) or "(nenhum)"
            raise KeyError(
                f"profile pixel '{profile_id}' não existe; disponíveis: {disponiveis}"
            )
        return spec

    def find(self, profile_id: str) -> PixelOutputSpec | None:
        return self._profiles.get(profile_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._profiles))

    def list(self) -> list[PixelOutputSpec]:
        return [self._profiles[key] for key in sorted(self._profiles)]

    def palettes(self) -> dict[str, tuple[str, ...]]:
        """Tabela de paletas do projeto (§11), copiada para leitura."""
        return dict(self._palettes)

    # ------------------------------------------------------------------
    def resolve(self, spec: PixelOutputSpec) -> PixelOutputSpec:
        """Troca uma paleta PROJECT pela paleta LOCKED correspondente (§11).

        Um ``palette_id`` desconhecido devolve o spec **inalterado**, com um
        aviso. Inventar cores ou derrubar o boot seria pior: quem reprova o
        asset é o check PX-PALETTE-001, no lugar onde a falha aparece no
        relatório em vez de sumir em uma exceção de configuração.
        """
        if spec.palette.mode != "project_palette":
            return spec

        palette_id = spec.palette.palette_id or ""
        colors = self._palettes.get(palette_id)
        if not colors:
            _LOG.warning(
                "profile pixel '%s' pede a paleta de projeto '%s', que não existe",
                spec.id,
                palette_id,
            )
            return spec
        return spec.with_palette_colors(colors)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._profiles)


def _load_palettes(raw: Any) -> dict[str, tuple[str, ...]]:
    """Lê a chave ``palettes`` do YAML, normalizando as cores na entrada.

    Normalizar aqui (``#FFF`` e ``#ffffff`` viram a mesma string) é o que
    permite ao check de paleta comparar cores por igualdade textual depois.
    """
    palettes: dict[str, tuple[str, ...]] = {}
    for palette_id, colors in sorted((raw or {}).items()):
        try:
            palettes[str(palette_id)] = tuple(normalize_hex(color) for color in colors)
        except (AttributeError, TypeError, ValueError) as exc:
            _LOG.error("paleta de projeto '%s' inválida e ignorada: %s", palette_id, exc)
    return palettes
