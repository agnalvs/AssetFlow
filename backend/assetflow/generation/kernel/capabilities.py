"""Catálogo de capacidades do AssetFlow (plano §7).

O catálogo é **descritivo, não restritivo**: ele documenta as capacidades que
o produto já conhece e alimenta a API (`GET /api/generation/capabilities`),
mas um motor novo pode declarar uma capacidade inédita sem alterar código do
kernel — ela apenas aparece como "não catalogada".

Essa escolha é deliberada: uma lista fechada aqui viraria acoplamento na
direção contrária (o kernel ditando o que gavetas futuras podem fazer).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import AssetMode, Capability

__all__ = ["CapabilityInfo", "CapabilityCatalog", "CATALOG"]


@dataclass(frozen=True, slots=True)
class CapabilityInfo:
    """Descrição legível de uma capacidade."""

    capability: Capability
    description: str
    mode: AssetMode | None = None
    experimental: bool = False


def _cap(value: str) -> Capability:
    return Capability.parse(value)


_KNOWN: tuple[CapabilityInfo, ...] = (
    # --- Geração a partir de texto -----------------------------------------
    CapabilityInfo(
        _cap("text_to_image.general"),
        "Geração de imagem a partir de texto para arte 2D convencional.",
        AssetMode.STUDIO,
    ),
    CapabilityInfo(
        _cap("text_to_image.pixel"),
        "Geração de imagem a partir de texto orientada a Pixel Art.",
        AssetMode.PIXEL,
    ),
    # --- Geração a partir de imagem ----------------------------------------
    CapabilityInfo(
        _cap("image_to_image.general"),
        "Transformação de uma imagem existente (arte 2D convencional).",
        AssetMode.STUDIO,
        experimental=True,
    ),
    CapabilityInfo(
        _cap("image_to_image.pixel"),
        "Transformação de uma imagem existente preservando Pixel Art.",
        AssetMode.PIXEL,
        experimental=True,
    ),
    # --- Edição ------------------------------------------------------------
    CapabilityInfo(
        _cap("inpainting.general"),
        "Edição por máscara em arte 2D convencional.",
        AssetMode.STUDIO,
        experimental=True,
    ),
    CapabilityInfo(
        _cap("inpainting.pixel"),
        "Edição por máscara em Pixel Art.",
        AssetMode.PIXEL,
        experimental=True,
    ),
    # --- Capacidades orientadas a tipo de asset ----------------------------
    CapabilityInfo(_cap("character.pixel"), "Personagens em Pixel Art.", AssetMode.PIXEL),
    CapabilityInfo(_cap("character.2d"), "Personagens em arte 2D convencional.", AssetMode.STUDIO),
    CapabilityInfo(_cap("prop.pixel"), "Props e objetos em Pixel Art.", AssetMode.PIXEL),
    CapabilityInfo(_cap("prop.2d"), "Props e objetos em arte 2D convencional.", AssetMode.STUDIO),
    CapabilityInfo(_cap("background.pixel"), "Cenários e fundos em Pixel Art.", AssetMode.PIXEL),
    CapabilityInfo(_cap("background.2d"), "Cenários e fundos em arte 2D.", AssetMode.STUDIO),
    # --- Fases futuras -----------------------------------------------------
    CapabilityInfo(
        _cap("tileset.pixel"), "Tiles e tilesets em Pixel Art.", AssetMode.PIXEL, experimental=True
    ),
    CapabilityInfo(
        _cap("spritesheet.pixel"),
        "Montagem de spritesheets em Pixel Art.",
        AssetMode.PIXEL,
        experimental=True,
    ),
    CapabilityInfo(
        _cap("animation.pixel"),
        "Sequências animadas em Pixel Art.",
        AssetMode.PIXEL,
        experimental=True,
    ),
    CapabilityInfo(
        _cap("upscale.general"), "Ampliação de imagem.", None, experimental=True
    ),
)


class CapabilityCatalog:
    """Consulta às capacidades conhecidas pelo produto."""

    def __init__(self, entries: tuple[CapabilityInfo, ...] = _KNOWN) -> None:
        self._entries = {info.capability: info for info in entries}

    def all(self) -> tuple[CapabilityInfo, ...]:
        return tuple(self._entries.values())

    def get(self, capability: Capability | str) -> CapabilityInfo | None:
        return self._entries.get(Capability.parse(capability))

    def is_known(self, capability: Capability | str) -> bool:
        return Capability.parse(capability) in self._entries

    def describe(self, capability: Capability | str) -> str:
        info = self.get(capability)
        return info.description if info else "Capacidade não catalogada."

    def for_mode(self, mode: AssetMode) -> tuple[CapabilityInfo, ...]:
        return tuple(info for info in self._entries.values() if info.mode is mode)


#: Catálogo padrão do processo.
CATALOG = CapabilityCatalog()
