"""As ferramentas de desenho do Pixel Agent (plano de correção §16 e §19).

Um arquivo por ferramenta, como o plano de correção §16 desenha. O
vocabulário — ``draw_pixel``, ``draw_pixels``, ``fill_rect``, ``draw_line``,
``draw_circle``, ``draw_ellipse``, ``draw_triangle``, ``noise_fill_rect``,
``inspect_canvas`` — descreve bem o problema, e é só isso que foi adotado: a
implementação é do AssetFlow, escrita do zero.

A distinção é deliberada (plano de motores §2.4): o Texel Studio é
*source-available*, com restrição contra hospedagem como SaaS concorrente. O
AssetFlow se inspira na arquitetura tool-based dele e implementa a sua — não
incorpora nem revende o projeto. Na interface, o nome é **AssetFlow Pixel
Agent** (plano de correção §33).
"""

from .base import PixelTool, as_color, as_int
from .draw_circle import draw_circle
from .draw_ellipse import draw_ellipse
from .draw_line import draw_line
from .draw_pixel import draw_pixel
from .draw_pixels import draw_pixels
from .draw_triangle import draw_triangle
from .fill_rect import fill_rect
from .noise_fill import noise_fill_rect
from .inspect_canvas import inspect_canvas

#: Todas as ferramentas, na ordem em que o plano de correção §16 as lista.
ALL_TOOLS = (
    draw_pixel,
    draw_pixels,
    fill_rect,
    draw_line,
    draw_circle,
    draw_ellipse,
    draw_triangle,
    noise_fill_rect,
    inspect_canvas,
)

__all__ = [
    "ALL_TOOLS",
    "PixelTool",
    "as_color",
    "as_int",
    "draw_circle",
    "draw_ellipse",
    "draw_line",
    "draw_pixel",
    "draw_pixels",
    "draw_triangle",
    "fill_rect",
    "inspect_canvas",
    "noise_fill_rect",
]
