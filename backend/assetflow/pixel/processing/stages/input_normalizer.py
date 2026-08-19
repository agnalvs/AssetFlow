"""InputNormalizer — a porta de entrada do PixelPostProcessor (plano Pixel §12).

Todo o resto do módulo assume três coisas sobre a imagem: que a orientação já é
a final, que ela está em RGBA e que existe pelo menos um pixel para trabalhar.
Este estágio garante as três — e nada além disso.

O plano §12 lista principalmente o que é **proibido** aqui, e a proibição é o
ponto: nada de redução de paleta, resize, sharpening ou blur. Qualquer um deles
aconteceria antes de a resolução lógica existir, ou seja, em cima de pixels que
ainda vão ser reamostrados — o efeito visível seria imprevisível, e os estágios
que são de fato donos de enquadramento, resolução, alpha e paleta receberiam
uma imagem já adulterada, sem registro próprio no relatório.

Sobre fundo: com ``background.mode == "solid"`` a imagem é composta sobre um
canvas opaco da cor pedida. Com ``"transparent"`` este estágio não faz nada —
**remoção automática de fundo não faz parte do Pixel Exact 1.0**. Separar
sprite de fundo é segmentação, não normalização: exigiria um modelo próprio,
erraria em silhueta complexa e o erro só apareceria depois da redução lógica,
quando não há mais como voltar atrás. Quem precisa de fundo transparente pede
ao motor uma imagem que já venha com alpha.
"""

from __future__ import annotations

from PIL import Image, ImageOps

from ...imaging import ensure_rgba, hex_to_rgb
from .base import PixelContext, PixelTransform

__all__ = ["InputNormalizer"]

#: Tag EXIF ``Orientation`` (0x0112). É lida antes da transposição porque
#: ``exif_transpose`` remove a tag do resultado: depois dele não há mais como
#: dizer no relatório se a correção realmente aconteceu.
_EXIF_ORIENTATION = 0x0112


class InputNormalizer(PixelTransform):
    """Orientação EXIF, conversão para RGBA e aplicação de fundo (§12)."""

    name = "pixel.input_normalizer"
    version = "1.0.0"

    def apply(self, image: Image.Image, context: PixelContext) -> Image.Image:
        if image.width <= 0 or image.height <= 0:
            raise ValueError(
                "imagem de entrada degenerada: "
                f"{image.width}x{image.height} — largura e altura precisam ser "
                "maiores que zero"
            )

        context.detail("source_size", image.size)
        context.detail("source_mode", image.mode)

        orientation = _orientation(image)
        # `exif_transpose` só devolve `None` no modo `in_place`; o fallback
        # existe para o type checker, não para o runtime.
        result = ensure_rgba(ImageOps.exif_transpose(image) or image)
        exif_applied = orientation is not None and orientation != 1
        context.detail("exif_applied", exif_applied)

        background_applied = False
        background = context.spec.background
        if background.mode == "solid":
            red, green, blue = hex_to_rgb(background.color)
            canvas = Image.new("RGBA", result.size, (red, green, blue, 255))
            result = Image.alpha_composite(canvas, result)
            background_applied = True
        context.detail("background_applied", background_applied)

        return result


def _orientation(image: Image.Image) -> int | None:
    """Valor da tag EXIF de orientação, ou ``None`` quando ela não existe."""
    try:
        value = image.getexif().get(_EXIF_ORIENTATION)
    except (AttributeError, OSError, ValueError):  # pragma: no cover - EXIF quebrado
        # Bloco EXIF corrompido ou truncado não é motivo para derrubar o job:
        # sem orientação legível, a imagem já está na orientação final.
        return None
    return int(value) if isinstance(value, int) else None
