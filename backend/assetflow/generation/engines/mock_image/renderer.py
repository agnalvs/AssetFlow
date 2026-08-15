"""Renderizador determinístico da gaveta mock.

Não há IA aqui: dada a mesma seed e o mesmo tamanho, a imagem é sempre a
mesma. Isso é justamente o que torna a gaveta útil para testar a arquitetura
(e para rodar a suíte inteira em CI sem GPU).
"""

from __future__ import annotations

import colorsys
import io
import random

from PIL import Image, ImageDraw

__all__ = ["render_placeholder", "PALETTES"]

PALETTES = ("spectrum", "mono", "duotone")


def _palette_colors(rng: random.Random, palette: str, count: int) -> list[tuple[int, int, int]]:
    base_hue = rng.random()
    colors: list[tuple[int, int, int]] = []
    for index in range(count):
        if palette == "mono":
            hue = base_hue
            saturation = 0.15
            value = 0.25 + 0.65 * (index / max(1, count - 1))
        elif palette == "duotone":
            hue = base_hue if index % 2 == 0 else (base_hue + 0.5) % 1.0
            saturation = 0.55
            value = 0.35 + 0.5 * (index / max(1, count - 1))
        else:  # spectrum
            hue = (base_hue + index / max(1, count)) % 1.0
            saturation = 0.62
            value = 0.85
        r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
        colors.append((int(r * 255), int(g * 255), int(b * 255)))
    return colors


def render_placeholder(
    *,
    width: int,
    height: int,
    seed: int,
    label: str,
    palette: str = "spectrum",
    transparent: bool = False,
    watermark: bool = True,
) -> bytes:
    """Desenha um "asset" placeholder e devolve os bytes PNG.

    A figura tem silhueta reconhecível (cabeça, corpo, base) para que o
    pós-processamento de Pixel Art tenha algo real para reduzir, quantizar e
    validar.
    """
    rng = random.Random(seed)
    colors = _palette_colors(rng, palette if palette in PALETTES else "spectrum", 6)

    background = (0, 0, 0, 0) if transparent else (*colors[0], 255)
    image = Image.new("RGBA", (width, height), background)
    draw = ImageDraw.Draw(image)

    if not transparent:
        # Fundo em faixas, para gerar variedade de cor mensurável.
        band_height = max(1, height // 8)
        for index in range(0, height, band_height):
            shade = colors[(index // band_height) % len(colors)]
            draw.rectangle([0, index, width, index + band_height], fill=(*shade, 255))

    unit_w = width / 16.0
    unit_h = height / 16.0

    body_color = (*colors[3], 255)
    accent_color = (*colors[4], 255)
    outline_color = (*colors[5], 255)

    # Corpo
    draw.rounded_rectangle(
        [unit_w * 5, unit_h * 6, unit_w * 11, unit_h * 13],
        radius=max(1, int(unit_w)),
        fill=body_color,
        outline=outline_color,
        width=max(1, int(min(unit_w, unit_h) / 2)),
    )
    # Cabeça
    draw.ellipse(
        [unit_w * 6, unit_h * 2, unit_w * 10, unit_h * 6.5],
        fill=accent_color,
        outline=outline_color,
        width=max(1, int(min(unit_w, unit_h) / 2)),
    )
    # Base / sombra
    draw.ellipse(
        [unit_w * 4.5, unit_h * 12.5, unit_w * 11.5, unit_h * 14],
        fill=(*colors[2], 200),
    )
    # Detalhe variável pela seed (garante variações distintas entre si)
    for _ in range(rng.randint(2, 5)):
        x = rng.uniform(unit_w * 5.5, unit_w * 10.5)
        y = rng.uniform(unit_h * 7, unit_h * 12)
        size = rng.uniform(unit_w * 0.5, unit_w * 1.5)
        draw.rectangle([x, y, x + size, y + size], fill=(*colors[1], 255))

    if watermark and width >= 96 and height >= 48:
        text = f"{label} · seed {seed}"
        draw.text((max(2, unit_w * 0.3), height - max(12, unit_h)), text, fill=outline_color)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
