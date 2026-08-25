"""As ferramentas de reparo do Optimizer (plano Optimizer §13 e §40).

O conjunto inicial que o §40 pede, e nada além dele. A lista do §41 —
``move_region``, ``mirror_region``, ``palette_merge``, ``local_dither`` — fica
para depois, e a ordem não é arbitrária: as oito daqui cobrem os problemas que
o ``PixelValidator`` sabe medir hoje, e uma ferramenta sem problema medido
correspondente é uma ferramenta que ninguém saberia quando usar.

O vocabulário é de **reparo**, não de desenho. ``erase_pixel`` e
``repair_outline`` existem; ``draw_circle`` e ``draw_triangle``, não. A
diferença é a arquitetura inteira do plano: o Optimizer trabalha sobre o que
um motor gerou, e não no lugar dele (§79).
"""

from .base import as_color, as_int
from .connect_cluster import connect_cluster
from .draw_pixels import draw_pixels
from .erase_pixel import erase_pixel
from .inspect_canvas import inspect_canvas
from .inspect_region import inspect_region
from .repair_outline import repair_outline
from .replace_color import replace_color
from .set_pixel import set_pixel

#: Todas as ferramentas, na ordem em que o §40 as lista.
ALL_TOOLS = (
    set_pixel,
    erase_pixel,
    draw_pixels,
    replace_color,
    inspect_canvas,
    inspect_region,
    repair_outline,
    connect_cluster,
)

__all__ = [
    "ALL_TOOLS",
    "as_color",
    "as_int",
    "connect_cluster",
    "draw_pixels",
    "erase_pixel",
    "inspect_canvas",
    "inspect_region",
    "repair_outline",
    "replace_color",
    "set_pixel",
]
