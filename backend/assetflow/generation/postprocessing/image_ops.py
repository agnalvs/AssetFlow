"""Operações de imagem de baixo nível compartilhadas.

Pillow é uma biblioteca de imagem genérica, não uma tecnologia de geração —
usá-la aqui não fere a regra das gavetas.
"""

from __future__ import annotations

import io
from typing import Iterable

from PIL import Image

__all__ = [
    "decode_image",
    "encode_png",
    "unique_colors",
    "to_hex",
    "from_hex",
    "build_thumbnail",
]


def decode_image(data: bytes) -> Image.Image:
    """Decodifica bytes para RGBA."""
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGBA")


def encode_png(image: Image.Image, *, optimize: bool = True) -> bytes:
    """Codifica em PNG (formato-base de todo asset do AssetFlow)."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=optimize)
    return buffer.getvalue()


def unique_colors(image: Image.Image, *, ignore_transparent: bool = True) -> list[tuple[int, ...]]:
    """Lista as cores distintas da imagem.

    Base da validação de contagem de cores em Pixel Art (plano §59).
    """
    rgba = image.convert("RGBA")
    colors = rgba.getcolors(maxcolors=rgba.width * rgba.height) or []
    result = []
    for _count, color in colors:
        if ignore_transparent and len(color) == 4 and color[3] == 0:
            continue
        result.append(tuple(color))
    return result


def to_hex(color: Iterable[int]) -> str:
    """``(255, 128, 0, 255)`` -> ``'#ff8000'``."""
    values = list(color)[:3]
    return "#" + "".join(f"{int(value):02x}" for value in values)


def from_hex(value: str) -> tuple[int, int, int]:
    """``'#ff8000'`` -> ``(255, 128, 0)``."""
    raw = value.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(char * 2 for char in raw)
    if len(raw) != 6:
        raise ValueError(f"cor hexadecimal inválida: {value!r}")
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def build_thumbnail(image: Image.Image, scale: float) -> Image.Image | None:
    """Gera o thumbnail.

    ``scale > 1`` amplia com nearest-neighbor (Pixel Art precisa de blocos
    nítidos); ``scale < 1`` reduz com LANCZOS (arte 2D convencional).
    """
    if scale <= 0:
        return None

    width = max(1, int(round(image.width * scale)))
    height = max(1, int(round(image.height * scale)))
    if (width, height) == image.size:
        return image.copy()

    resample = Image.NEAREST if scale > 1 else Image.LANCZOS
    return image.resize((width, height), resample)
