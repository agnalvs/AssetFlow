"""CanvasNormalizer — enquadramento antes da redução (plano Pixel §13 e §14).

Este estágio existe por causa de uma conta simples: esticar 1024×768 até 64×64
achata o personagem em 25%. O plano §13 evita isso separando duas decisões que
costumam virar uma só — *enquadrar* e *reduzir*:

    CanvasNormalizer      recorta e preenche       nunca escala
    LogicalPixelReducer   escala                   sabe reduzir sem borrar

Por isso não existe uma única chamada de resize aqui. A saída é uma imagem cujo
aspect ratio já é o da resolução lógica; o tamanho absoluto continua sendo o da
origem, porque escolher o filtro de redução é problema do estágio seguinte
(§15 a §19). Os pixels que sobrevivem são copiados byte a byte — sem
reamostragem e sem composição.

Os modos de :class:`~assetflow.pixel.contracts.output_spec.CanvasSpec` (§14):

``contain``
    Só preenche, até o aspect alvo, com o conteúdo centralizado. É o padrão, e
    o único modo que não descarta pixel nenhum.
``cover``
    Só recorta, centralizado, até o aspect alvo — o excedente é descartado.
``center_crop``
    Recorta o centro no **tamanho lógico exato**, 1:1, sem escalar. É o modo de
    fontes que já estão na grade: cada pixel de origem vira um pixel lógico.
``transparent_pad``
    Centraliza no canvas de tamanho lógico exato e preenche a sobra. Mesma
    geometria de ``center_crop``, vista do outro lado (origem menor que o
    alvo); os dois nomes existem porque a intenção declarada no profile é
    diferente, e o relatório precisa dizer qual delas foi pedida.
``stretch``
    No-op aqui. A deformação é intencional e fica explicitamente a cargo do
    reducer, que é quem escala.

Sobre ``trim_transparent`` e a margem de 4%: quando o conteúdo opaco é recortado
pela sua bounding box e o modo é ``contain``, o estágio acrescenta uma folga de
4% (arredondada para cima, mínimo 1px) em cada lado depois do pad. Essa margem
**é** a correção automática prevista no plano §61 para a falha ``PX-BOUND-001``
(sprite encostando na borda): sem ela, recortar exatamente a caixa do conteúdo
devolveria um sprite colado nas quatro bordas — o próprio defeito que a segunda
tentativa deveria corrigir. Como o canvas já está no aspect lógico quando a
folga é somada, uma margem uniforme em pixels de origem vira a mesma margem em
pixels lógicos nos dois eixos.

O estágio nunca se desliga (``applies_to`` continua sempre verdadeiro), mesmo
em ``stretch``: ``trim_transparent`` é ortogonal ao modo, e o relatório precisa
registrar a geometria medida ainda que nada tenha sido alterado.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from ...contracts.output_spec import CanvasSpec
from ...imaging import bounding_box, hex_to_rgb, opaque_mask, to_array, to_image
from .base import PixelContext, PixelTransform

__all__ = ["CanvasNormalizer"]

#: Folga do plano §61 em porcentagem inteira. ``0.04 * 100`` em ponto flutuante
#: dá 4.000000000000001, e arredondar para cima devolveria 5 em um canvas de
#: 100px: determinismo byte a byte exige aritmética inteira.
_MARGIN_PERCENT = 4

#: Janela ``(x0, y0, x1, y1)`` com o fim **exclusivo**, em coordenadas da
#: imagem de origem. Ela pode cair fora da imagem — é assim que um primitivo só
#: resolve recorte e preenchimento.
_Box = tuple[int, int, int, int]
_Color = tuple[int, int, int, int]


class CanvasNormalizer(PixelTransform):
    """Ajusta o aspect ratio recortando e/ou preenchendo (§13 e §14)."""

    name = "pixel.canvas_normalizer"
    version = "1.0.0"

    def apply(self, image: Image.Image, context: PixelContext) -> Image.Image:
        canvas = context.spec.canvas
        target = context.spec.target_size
        source_size = image.size
        fill = _fill_color(canvas)

        array = to_array(image)
        padded = False
        cropped = False
        margin_px = 0

        # A caixa do conteúdo é medida na imagem que chegou, antes de qualquer
        # recorte ou pad, e é ela que decide se a margem do §61 se aplica.
        trimmed_box = self._content_box(array, canvas, context)
        if trimmed_box is not None:
            left, top, right, bottom = trimmed_box
            array, step_pad, step_crop = _place(
                array, (left, top, right + 1, bottom + 1), fill
            )
            padded = padded or step_pad
            cropped = cropped or step_crop

        if canvas.mode != "stretch":
            array, step_pad, step_crop = _place(
                array, _target_box(array, target, canvas.mode), fill
            )
            padded = padded or step_pad
            cropped = cropped or step_crop

        if canvas.mode == "contain" and trimmed_box is not None:
            height, width = _shape(array)
            margin_px = _margin(width, height)
            array, step_pad, _crop = _place(
                array,
                (-margin_px, -margin_px, width + margin_px, height + margin_px),
                fill,
            )
            padded = padded or step_pad
            # A folga uniforme empurra o aspect em direção a 1:1; um segundo
            # pad o traz de volta ao alvo somando margem no eixo mais curto —
            # nunca recortando o que acabou de ganhar folga.
            array, step_pad, _crop = _place(
                array, _target_box(array, target, "contain"), fill
            )
            padded = padded or step_pad

        result_height, result_width = _shape(array)
        result_size = (result_width, result_height)

        context.detail("mode", canvas.mode)
        context.detail("source_size", source_size)
        context.detail("result_size", result_size)
        context.detail("trimmed_box", trimmed_box)
        context.detail("padded", padded)
        context.detail("cropped", cropped)
        context.detail("margin_px", margin_px)
        context.detail("aspect_before", _aspect(source_size))
        context.detail("aspect_after", _aspect(result_size))

        return to_image(array)

    # ------------------------------------------------------------------
    def _content_box(
        self, array: np.ndarray, canvas: CanvasSpec, context: PixelContext
    ) -> _Box | None:
        """Bounding box **inclusiva** do conteúdo opaco, ou ``None``.

        Devolver ``None`` quando a imagem é 100% transparente é deliberado:
        recortar "nada" produziria uma janela degenerada, e o problema real
        (imagem vazia) pertence ao check ``PX-EMPTY-001`` — este estágio só
        avisa e segue sem recortar.
        """
        if not canvas.trim_transparent:
            return None
        box = bounding_box(opaque_mask(array))
        if box is None:
            context.warn("canvas: imagem 100% transparente, trim_transparent ignorado")
            return None
        return box


def _fill_color(canvas: CanvasSpec) -> _Color:
    """Cor do preenchimento: transparente puro ou a cor sólida do spec."""
    if canvas.pad == "solid":
        red, green, blue = hex_to_rgb(canvas.pad_color)
        return (red, green, blue, 255)
    return (0, 0, 0, 0)


def _target_box(array: np.ndarray, target: tuple[int, int], mode: str) -> _Box:
    """Janela centralizada que o modo pede, em coordenadas da origem."""
    height, width = _shape(array)
    target_w, target_h = target
    if mode == "contain":
        size = _aspect_size(width, height, target_w, target_h, grow=True)
    elif mode == "cover":
        size = _aspect_size(width, height, target_w, target_h, grow=False)
    else:
        # center_crop e transparent_pad: o tamanho lógico exato, 1:1.
        size = (target_w, target_h)
    return _centered_box(width, height, size[0], size[1])


def _aspect_size(
    width: int, height: int, target_w: int, target_h: int, *, grow: bool
) -> tuple[int, int]:
    """Canvas com o aspect alvo que envolve (``grow``) ou cabe na origem.

    A comparação é multiplicação cruzada de inteiros: dividir em ponto
    flutuante faria dois canvases equivalentes caírem em ramos diferentes por
    causa do último bit, e o módulo inteiro depende de determinismo (§103).
    """
    if width * target_h == height * target_w:
        return (width, height)
    wider = width * target_h > height * target_w
    if grow:
        if wider:
            return (width, _ceil_div(width * target_h, target_w))
        return (_ceil_div(height * target_w, target_h), height)
    if wider:
        return (max(1, height * target_w // target_h), height)
    return (width, max(1, width * target_h // target_w))


def _centered_box(width: int, height: int, out_w: int, out_h: int) -> _Box:
    """Centraliza uma janela ``out_w × out_h`` sobre um canvas ``width × height``.

    Com sobra ímpar o pixel extra fica sempre à direita e abaixo, porque a
    divisão inteira arredonda para baixo. A escolha é invisível no resultado e,
    principalmente, é sempre a mesma.
    """
    left = (width - out_w) // 2
    top = (height - out_h) // 2
    return (left, top, left + out_w, top + out_h)


def _place(array: np.ndarray, box: _Box, fill: _Color) -> tuple[np.ndarray, bool, bool]:
    """Recorta e/ou preenche ``array`` na janela ``box``.

    Devolve ``(resultado, preencheu, recortou)``. Concentrar as duas operações
    em um primitivo só é o que mantém a regra do estágio verificável em um
    lugar: o que sobrevive é copiado byte a byte e o que falta vira ``fill`` —
    em nenhum caminho existe interpolação.
    """
    x0, y0, x1, y1 = box
    height, width = _shape(array)
    out_w, out_h = x1 - x0, y1 - y0
    if out_w <= 0 or out_h <= 0:
        raise ValueError(f"janela de canvas degenerada: {out_w}x{out_h}")

    padded = x0 < 0 or y0 < 0 or x1 > width or y1 > height
    cropped = x0 > 0 or y0 > 0 or x1 < width or y1 < height
    if not padded and not cropped:
        return array, False, False

    result = np.empty((out_h, out_w, 4), dtype=np.uint8)
    result[:, :] = np.asarray(fill, dtype=np.uint8)
    src_x0, src_y0 = max(x0, 0), max(y0, 0)
    src_x1, src_y1 = min(x1, width), min(y1, height)
    if src_x1 > src_x0 and src_y1 > src_y0:
        result[src_y0 - y0 : src_y1 - y0, src_x0 - x0 : src_x1 - x0] = array[
            src_y0:src_y1, src_x0:src_x1
        ]
    return result, padded, cropped


def _margin(width: int, height: int) -> int:
    """Folga do plano §61: 4% do menor lado, para cima, nunca menor que 1px."""
    return max(1, _ceil_div(_MARGIN_PERCENT * min(width, height), 100))


def _ceil_div(dividend: int, divisor: int) -> int:
    return -(-dividend // divisor)


def _shape(array: np.ndarray) -> tuple[int, int]:
    """``(altura, largura)`` como ``int`` puro — o resto do módulo faz contas."""
    return (int(array.shape[0]), int(array.shape[1]))


def _aspect(size: tuple[int, int]) -> float:
    return round(size[0] / size[1], 4)
