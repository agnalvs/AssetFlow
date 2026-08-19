"""Primitivas de imagem do módulo Pixel (plano Pixel §108).

Todo estágio e todo analisador falam com a imagem **por aqui**. Concentrar as
operações em um módulo só tem três efeitos práticos:

1. a proibição do plano Pixel §20 (nada de ``BILINEAR``/``BICUBIC``/``LANCZOS``
   depois da resolução lógica) fica verificável em um arquivo, não espalhada;
2. a representação interna é sempre a mesma — ``numpy.uint8`` no formato
   ``(altura, largura, 4)`` em RGBA;
3. troca de biblioteca no futuro é local.

Sobre connected components: o plano §49 sugere OpenCV. Aqui a análise roda em
imagens de 32×32 a 128×128 — a propagação vetorizada abaixo resolve o mesmo
problema em milissegundos, é determinística e evita somar ~90MB de dependência
ao backend por causa de uma função (plano Pixel §108, "evitar adicionar
bibliotecas maiores sem necessidade").
"""

from __future__ import annotations

import io
from collections.abc import Iterable

import numpy as np
from PIL import Image

__all__ = [
    "RGBA",
    "alpha_values",
    "bounding_box",
    "color_clusters",
    "color_counts",
    "color_distance",
    "connected_components",
    "count_colors",
    "decode",
    "encode_png",
    "ensure_rgba",
    "hex_to_rgb",
    "map_to_palette",
    "opaque_mask",
    "resize_box",
    "resize_nearest",
    "rgb_to_hex",
    "scale_nearest",
    "to_array",
    "to_image",
    "touches_border",
    "unique_colors",
]

#: Formato interno: ``(altura, largura, 4)``, ``uint8``.
RGBA = np.ndarray


# ---------------------------------------------------------------------------
# Conversões
# ---------------------------------------------------------------------------
def decode(data: bytes) -> Image.Image:
    """Bytes de imagem -> ``Image`` RGBA."""
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGBA")


def encode_png(image: Image.Image, *, optimize: bool = True) -> bytes:
    """``Image`` -> PNG lossless (plano Pixel §33).

    PNG sempre: nenhum formato com perda pode tocar em um asset Pixel Exact,
    porque um único pixel alterado quebra a paleta e o alpha binário.
    """
    buffer = io.BytesIO()
    image.convert("RGBA").save(buffer, format="PNG", optimize=optimize)
    return buffer.getvalue()


def ensure_rgba(image: Image.Image) -> Image.Image:
    return image if image.mode == "RGBA" else image.convert("RGBA")


def to_array(image: Image.Image) -> RGBA:
    """``Image`` -> array ``(h, w, 4)`` ``uint8``."""
    return np.array(ensure_rgba(image), dtype=np.uint8).reshape(
        image.height, image.width, 4
    )


def to_image(array: RGBA) -> Image.Image:
    """Array ``(h, w, 4)`` -> ``Image`` RGBA."""
    return Image.fromarray(np.ascontiguousarray(array, dtype=np.uint8), mode="RGBA")


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = value.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(char * 2 for char in raw)
    if len(raw) == 8:
        raw = raw[:6]
    if len(raw) != 6:
        raise ValueError(f"cor hexadecimal inválida: {value!r}")
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def rgb_to_hex(color: Iterable[int]) -> str:
    values = list(color)[:3]
    return "#" + "".join(f"{int(value) & 0xFF:02x}" for value in values)


# ---------------------------------------------------------------------------
# Máscaras e medidas
# ---------------------------------------------------------------------------
def opaque_mask(array: RGBA, *, threshold: int = 1) -> np.ndarray:
    """Máscara booleana do foreground (alpha >= ``threshold``)."""
    return array[:, :, 3] >= threshold


def alpha_values(array: RGBA) -> tuple[int, ...]:
    """Valores distintos presentes no canal alpha, ordenados."""
    return tuple(int(value) for value in np.unique(array[:, :, 3]))


def unique_colors(
    array: RGBA, *, ignore_transparent: bool = True
) -> tuple[np.ndarray, np.ndarray]:
    """Cores RGB distintas e suas contagens.

    ``numpy.unique`` com ``return_counts`` é exatamente a ferramenta indicada
    pelo plano Pixel §28 para calcular paleta e frequência de uma vez.
    """
    if ignore_transparent:
        pixels = array[opaque_mask(array)][:, :3]
    else:
        pixels = array.reshape(-1, 4)[:, :3]
    if pixels.size == 0:
        return np.empty((0, 3), dtype=np.uint8), np.empty((0,), dtype=np.int64)
    colors, counts = np.unique(pixels.reshape(-1, 3), axis=0, return_counts=True)
    return colors.astype(np.uint8), counts.astype(np.int64)


def color_counts(array: RGBA, *, ignore_transparent: bool = True) -> dict[str, int]:
    """``{"#12151c": 743, ...}`` — a frequência do plano Pixel §54."""
    colors, counts = unique_colors(array, ignore_transparent=ignore_transparent)
    pairs = sorted(
        ((rgb_to_hex(color), int(count)) for color, count in zip(colors, counts)),
        key=lambda item: (-item[1], item[0]),
    )
    return dict(pairs)


def count_colors(array: RGBA, *, ignore_transparent: bool = True) -> int:
    """Contagem de cores únicas — a medida do check PX-COLOR-001."""
    colors, _counts = unique_colors(array, ignore_transparent=ignore_transparent)
    return int(colors.shape[0])


def bounding_box(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Caixa ``(x0, y0, x1, y1)`` inclusiva do conteúdo, ou ``None`` se vazio."""
    if not mask.any():
        return None
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    return (int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1]))


def touches_border(mask: np.ndarray) -> bool:
    """Diz se o conteúdo encosta em alguma borda do canvas (plano Pixel §45)."""
    if not mask.any():
        return False
    return bool(
        mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any()
    )


# ---------------------------------------------------------------------------
# Connected components
# ---------------------------------------------------------------------------
_OFFSETS_8 = (
    (0, 0), (0, 1), (0, 2),
    (1, 0), (1, 1), (1, 2),
    (2, 0), (2, 1), (2, 2),
)
_OFFSETS_4 = ((0, 1), (1, 0), (1, 1), (1, 2), (2, 1))


def connected_components(
    mask: np.ndarray, *, connectivity: int = 8
) -> tuple[np.ndarray, int]:
    """Rotula os componentes conexos de uma máscara booleana.

    Devolve ``(labels, total)`` com rótulos ``1..total`` e ``0`` fora da
    máscara. O algoritmo é propagação de máximo até estabilizar: totalmente
    vetorizado, determinístico e independente da ordem de varredura.
    """
    if mask.ndim != 2:
        raise ValueError("connected_components espera uma máscara 2D")
    if not mask.any():
        return np.zeros(mask.shape, dtype=np.int64), 0

    height, width = mask.shape
    offsets = _OFFSETS_8 if connectivity == 8 else _OFFSETS_4
    labels = np.where(
        mask, np.arange(1, height * width + 1, dtype=np.int64).reshape(height, width), 0
    )

    padded = np.zeros((height + 2, width + 2), dtype=np.int64)
    while True:
        padded[1 : height + 1, 1 : width + 1] = labels
        neighbourhood = np.maximum.reduce(
            [padded[row : row + height, col : col + width] for row, col in offsets]
        )
        propagated = np.where(mask, neighbourhood, 0)
        if np.array_equal(propagated, labels):
            break
        labels = propagated

    # Rótulos contíguos e estáveis: 1, 2, 3... na ordem de varredura.
    present = np.unique(labels[labels > 0])
    remap = np.zeros(int(labels.max()) + 1, dtype=np.int64)
    remap[present] = np.arange(1, present.size + 1, dtype=np.int64)
    return remap[labels], int(present.size)


def color_clusters(
    array: RGBA, *, connectivity: int = 8
) -> list[tuple[str, int, tuple[int, int, int, int]]]:
    """Agrupa pixels conectados **da mesma cor** (plano Pixel §49).

    Devolve ``[(cor_hex, area, bounding_box), ...]``, que é o material do
    MicroClusterAnalyzer: clusters de 1, 2 e 3 pixels.
    """
    clusters: list[tuple[str, int, tuple[int, int, int, int]]] = []
    colors, _counts = unique_colors(array)
    opaque = opaque_mask(array)
    rgb = array[:, :, :3]

    for color in colors:
        mask = opaque & np.all(rgb == color.reshape(1, 1, 3), axis=2)
        labels, total = connected_components(mask, connectivity=connectivity)
        if total == 0:
            continue
        hex_color = rgb_to_hex(color)
        for index in range(1, total + 1):
            component = labels == index
            box = bounding_box(component)
            clusters.append((hex_color, int(component.sum()), box or (0, 0, 0, 0)))
    return clusters


# ---------------------------------------------------------------------------
# Paleta
# ---------------------------------------------------------------------------
def color_distance(colors: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Matriz de distâncias euclidianas ao quadrado ``(n_cores, n_paleta)``."""
    diff = colors.astype(np.int32)[:, None, :] - palette.astype(np.int32)[None, :, :]
    return np.sum(diff * diff, axis=2)


def map_to_palette(array: RGBA, palette: np.ndarray) -> RGBA:
    """Mapeia cada pixel para a cor mais próxima da paleta (plano Pixel §27).

    Usado pelo modo LOCKED: depois disto, nenhuma cor fora da paleta pode
    sobreviver — é a condição exata que o check PX-PALETTE-001 confere.
    """
    if palette.size == 0:
        return array.copy()

    result = array.copy()
    rgb = result[:, :, :3].reshape(-1, 3)
    unique, inverse = np.unique(rgb, axis=0, return_inverse=True)
    nearest = np.argmin(color_distance(unique, palette), axis=1)
    result[:, :, :3] = palette[nearest][inverse].reshape(result.shape[0], result.shape[1], 3)
    return result


# ---------------------------------------------------------------------------
# Redimensionamento
# ---------------------------------------------------------------------------
def resize_box(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Redução por média de área (plano Pixel §16 e §17).

    ``BOX`` faz todos os pixels da região de origem contribuírem com peso
    igual. Nearest, ao reduzir 512→64, ficaria com 1 de cada 64 pixels e
    destruiria a silhueta.
    """
    if image.size == size:
        return ensure_rgba(image).copy()
    return ensure_rgba(image).resize(size, Image.Resampling.BOX)


def resize_nearest(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Redimensionamento sem interpolação — o único permitido para ampliar."""
    if image.size == size:
        return ensure_rgba(image).copy()
    return ensure_rgba(image).resize(size, Image.Resampling.NEAREST)


def scale_nearest(image: Image.Image, scale: int) -> Image.Image:
    """Ampliação inteira do preview (plano Pixel §34, §80 e §81).

    Escala inteira e nearest-neighbor: cada pixel lógico vira um bloco
    ``scale × scale`` idêntico. Com escala fracionária os blocos sairiam com
    larguras diferentes e o sprite pareceria defeituoso.
    """
    if scale <= 1:
        return ensure_rgba(image).copy()
    return resize_nearest(image, (image.width * scale, image.height * scale))
