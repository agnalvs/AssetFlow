"""LogicalPixelReducer — a imagem chega à resolução lógica final (plano Pixel §15 a §20).

Este é o estágio que decide se o asset é Pixel Art de verdade. Antes dele a
imagem ainda é uma pintura grande com *aparência* de Pixel Art; depois dele
vale a regra de ouro nº 1 do plano Pixel §3: ``1 pixel lógico = 1 pixel do
PNG``, e o arquivo tem exatamente ``spec.logical_size``.

Por que ``BOX`` para reduzir e ``NEAREST`` só para ampliar (plano Pixel §16)
---------------------------------------------------------------------------
Reduzir 512→64 é resumir 64 pixels de origem em 1. Nearest faz isso da pior
maneira possível: copia o único pixel que calhou de cair sob o ponto
amostrado e descarta os outros 63. Um contorno de 2px some, um olho de 3px
some, e a silhueta — a única coisa que realmente importa em um sprite de
64×64 — passa a depender do alinhamento da grade, não do desenho. ``BOX``
faz média de área: todos os pixels da região contribuem com o mesmo peso, e
o que sobrevive é a forma.

Ao **ampliar** a regra se inverte. Não existe informação nova para inventar,
e qualquer filtro suavizado criaria pixels intermediários — justamente a
borda cinza esfumada que o Pixel Exact existe para não entregar. Ampliar é
replicar, e replicar é ``NEAREST``.

A fronteira do plano Pixel §20
------------------------------
Este estágio é o marco do pipeline: **depois daqui nenhum resampling
suavizado pode mais tocar no arquivo final**. Nada de ``BILINEAR``,
``BICUBIC``, ``LANCZOS``, blur, sharpen ou "suavização de borda" — qualquer
um deles reintroduziria as cores intermediárias que a paleta e o alpha
binário existem para eliminar, e o asset deixaria de ser Pixel Exact sem que
nenhum estágio posterior percebesse. A única ampliação permitida daí em
diante é a do preview: inteira, nearest, e que **não** é o asset
(plano Pixel §34).
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from ...imaging import RGBA, opaque_mask, resize_box, resize_nearest, to_array, to_image
from .base import PixelContext, PixelTransform

__all__ = ["LogicalPixelReducer"]


class LogicalPixelReducer(PixelTransform):
    """Leva a imagem à resolução lógica do spec, sem nunca suavizar."""

    name = "pixel.logical_reducer"
    version = "1.0.0"

    def apply(self, image: Image.Image, context: PixelContext) -> Image.Image:
        spec = context.spec
        source = (image.width, image.height)
        target = spec.target_size
        method = spec.logical_reduction.method

        fallback: str | None = None
        block_size: tuple[int, int] | None = None

        if method == "block_vote":
            block_size = _block_size(source, target)
            if block_size is None:
                # §18 exige múltiplos inteiros: sem isso não existe "o bloco de
                # origem deste pixel lógico", e qualquer arredondamento faria
                # blocos de larguras diferentes — o oposto de determinístico.
                fallback = "box"
                context.warn(
                    f"block_vote exige origem multipla inteira do alvo "
                    f"({source[0]}x{source[1]} -> {target[0]}x{target[1]}); "
                    f"usando reducao por media de area (box)"
                )

        if block_size is not None:
            result = _block_vote(
                to_array(image),
                target=target,
                block_size=block_size,
                alpha_threshold=spec.alpha.threshold,
                statistic=spec.logical_reduction.statistic,
                bins=spec.logical_reduction.vote_bins,
            )
            reduced = to_image(result)
            resample = "block_vote"
        elif source[0] < target[0] or source[1] < target[1]:
            # A origem é menor que o alvo em pelo menos um eixo. O
            # CanvasNormalizer já acertou o aspect ratio antes deste estágio,
            # então na prática ou os dois eixos crescem ou os dois encolhem —
            # e crescer só pode ser por replicação.
            reduced = resize_nearest(image, target)
            resample = "nearest"
        else:
            reduced = resize_box(image, target)
            resample = "box"

        context.detail("method", method)
        context.detail("source_size", source)
        context.detail("target_size", target)
        context.detail("resample", resample)
        context.detail("scale_x", round(source[0] / target[0], 6))
        context.detail("scale_y", round(source[1] / target[1], 6))
        context.detail("fallback", fallback)
        context.detail("block_size", block_size)

        # A partir daqui todo estágio posterior trabalha nesta grade. Guardar o
        # tamanho evita que alguém o recalcule a partir da imagem e discorde.
        context.shared["logical_size"] = (reduced.width, reduced.height)
        return reduced


# ---------------------------------------------------------------------------
# block_vote (plano Pixel §18)
# ---------------------------------------------------------------------------
def _block_size(
    source: tuple[int, int], target: tuple[int, int]
) -> tuple[int, int] | None:
    """Tamanho ``(largura, altura)`` do bloco, ou ``None`` se não for exato."""
    width, height = source
    target_width, target_height = target
    if width % target_width or height % target_height:
        return None
    return (width // target_width, height // target_height)


def _block_vote(
    array: RGBA,
    *,
    target: tuple[int, int],
    block_size: tuple[int, int],
    alpha_threshold: int,
    statistic: str,
    bins: int,
) -> RGBA:
    """Decide cada pixel lógico por votação dentro do seu bloco de origem.

    Toda a operação é vetorizada. Um laço em Python sobre os blocos seria um
    laço sobre os pixels do asset — 4096 iterações em um sprite 64×64 — e o
    ``reshape`` faz exatamente o mesmo trabalho de uma vez só.
    """
    target_width, target_height = target
    block_width, block_height = block_size
    samples = block_width * block_height

    # (H, W, 4) -> (linhas, bh, colunas, bw, 4) -> (blocos, amostras, 4).
    # O primeiro reshape só reinterpreta a memória: a origem é row-major, então
    # o pixel (i*bh + p, j*bw + q) já está exatamente onde o índice espera.
    blocks = array.reshape(
        target_height, block_height, target_width, block_width, 4
    ).transpose(0, 2, 1, 3, 4)
    blocks = blocks.reshape(target_height * target_width, samples, 4)

    opaque = opaque_mask(array, threshold=alpha_threshold)
    opaque = opaque.reshape(
        target_height, block_height, target_width, block_width
    ).transpose(0, 2, 1, 3)
    opaque = opaque.reshape(target_height * target_width, samples)

    # Alpha por maioria simples: o pixel lógico só é opaco se mais da metade do
    # bloco for opaca. Comparar `votos * 2 > amostras` mantém a conta inteira e
    # evita empate resolvido por ponto flutuante.
    alpha = np.where(opaque.sum(axis=1) * 2 > samples, 255, 0).astype(np.uint8)

    # A cor sai só dos pixels opacos — a franja transparente do gerador puxaria
    # a média para o fundo e sujaria o contorno. Bloco inteiramente
    # transparente não tem opção: usa todos os pixels.
    considered = opaque.copy()
    considered[~considered.any(axis=1)] = True

    rgb = blocks[:, :, :3].astype(np.int64)
    if statistic == "median":
        color = _median_color(rgb, considered)
    else:
        color = _dominant_color(rgb, considered, bins=bins)

    result = np.empty((target_height, target_width, 4), dtype=np.uint8)
    result[:, :, :3] = color.reshape(target_height, target_width, 3)
    result[:, :, 3] = alpha.reshape(target_height, target_width)
    return result


def _dominant_color(
    rgb: np.ndarray, considered: np.ndarray, *, bins: int
) -> np.ndarray:
    """Cor mais frequente do bloco, agrupada em ``bins`` níveis por canal.

    Sem o agrupamento a votação seria inútil: uma sombra pintada por um modelo
    tem centenas de tons quase idênticos e quase toda cor apareceria uma vez
    só. Com ``bins`` níveis, tons vizinhos caem no mesmo balde e a votação
    passa a medir *região de cor*, não valor exato.

    A cor devolvida é a **média dos pixels do balde vencedor**, não o centro do
    balde: quantizar serve para agrupar, e devolver o centro jogaria fora a
    fidelidade que o agrupamento não precisava perder.
    """
    total, samples, _ = rgb.shape
    binned = (rgb * bins) // 256
    # A chave é ((R*bins) + G)*bins + B: ordená-la é exatamente ordenar a cor
    # quantizada em ordem lexicográfica (R, G, B), que é o critério de desempate.
    keys = (binned[:, :, 0] * bins + binned[:, :, 1]) * bins + binned[:, :, 2]

    sentinel = bins**3
    masked = np.where(considered, keys, sentinel)
    ordered = np.sort(masked, axis=1)

    # Tamanho da sequência de chaves iguais a que cada posição pertence, obtido
    # pelos índices do início e do fim da sequência.
    positions = np.arange(samples, dtype=np.int64)
    starts = np.empty(ordered.shape, dtype=bool)
    starts[:, 0] = True
    starts[:, 1:] = ordered[:, 1:] != ordered[:, :-1]
    run_start = np.maximum.accumulate(np.where(starts, positions, -1), axis=1)
    ends = np.empty(ordered.shape, dtype=bool)
    ends[:, samples - 1] = True
    ends[:, : samples - 1] = starts[:, 1:]
    run_end = np.minimum.accumulate(
        np.where(ends, positions, samples)[:, ::-1], axis=1
    )[:, ::-1]
    run_size = np.where(ordered == sentinel, 0, run_end - run_start + 1)

    # `argmax` devolve a primeira posição do máximo e `ordered` é crescente:
    # em caso de empate vence a menor chave, ou seja, a menor cor em (R, G, B).
    winner = np.argmax(run_size, axis=1)
    winning_key = np.take_along_axis(ordered, winner[:, None], axis=1)

    member = masked == winning_key
    sums = np.sum(rgb * member[:, :, None], axis=1)
    counts = np.sum(member, axis=1)[:, None]
    # Arredondamento inteiro "meio para cima": floor(soma/n + 0.5) sem passar
    # por float, para que o resultado não dependa da FPU da máquina.
    color = (2 * sums + counts) // (2 * counts)
    return color.reshape(total, 3).astype(np.uint8)


def _median_color(rgb: np.ndarray, considered: np.ndarray) -> np.ndarray:
    """Mediana por canal dos pixels considerados, arredondada.

    Ao contrário da média, a mediana ignora um brilho isolado ou um pixel de
    fundo que tenha escapado da máscara — é a estatística indicada quando o
    bloco tem outlier, não gradiente.
    """
    total = rgb.shape[0]
    # 256 está fora da faixa de um canal: ordenar joga os não considerados para
    # o fim e a mediana só olha as `valid` primeiras posições.
    values = np.sort(np.where(considered[:, :, None], rgb, 256), axis=1)
    valid = np.sum(considered, axis=1)

    lower = np.repeat(((valid - 1) // 2)[:, None, None], 3, axis=2)
    upper = np.repeat((valid // 2)[:, None, None], 3, axis=2)
    low = np.take_along_axis(values, lower, axis=1)[:, 0, :]
    high = np.take_along_axis(values, upper, axis=1)[:, 0, :]

    # Contagem par: média dos dois centrais, também arredondada meio para cima.
    return ((low + high + 1) // 2).reshape(total, 3).astype(np.uint8)
