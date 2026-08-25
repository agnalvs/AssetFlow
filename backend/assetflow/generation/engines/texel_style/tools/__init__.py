"""As ferramentas de desenho do engine estilo Texel (plano de motores §9.3).

Um arquivo por ferramenta, como o plano de motores §23 desenha. O vocabulário é o mesmo
publicado pelo Texel Studio — ``draw_pixel``, ``draw_pixels``, ``fill_rect``,
``draw_line``, ``draw_circle``, ``draw_triangle``, ``noise_fill_rect``,
``view_canvas`` — porque é um vocabulário adequado ao problema, e não porque o
código seja o mesmo: a implementação aqui é do AssetFlow, escrita do zero.

Essa distinção é deliberada e está no plano de motores §2.4: o Texel Studio é
*source-available*, com restrição contra hospedagem como SaaS concorrente. O
AssetFlow se inspira na arquitetura tool-based dele e implementa a sua — não
incorpora nem revende o projeto.
"""

from .base import PixelTool, as_color, as_int
from .draw_circle import draw_circle
from .draw_line import draw_line
from .draw_pixel import draw_pixel
from .draw_pixels import draw_pixels
from .draw_triangle import draw_triangle
from .fill_rect import fill_rect
from .noise_fill import noise_fill_rect
from .view_canvas import view_canvas

#: Todas as ferramentas, na ordem em que o plano de motores §9.3 as lista.
ALL_TOOLS = (
    draw_pixel,
    draw_pixels,
    fill_rect,
    draw_line,
    draw_circle,
    draw_triangle,
    noise_fill_rect,
    view_canvas,
)

__all__ = [
    "ALL_TOOLS",
    "PixelTool",
    "as_color",
    "as_int",
    "draw_circle",
    "draw_line",
    "draw_pixel",
    "draw_pixels",
    "draw_triangle",
    "fill_rect",
    "noise_fill_rect",
    "view_canvas",
]
