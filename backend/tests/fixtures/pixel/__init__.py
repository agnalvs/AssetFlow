"""Fixtures de imagem do módulo Pixel, construídas por código (plano Pixel §90).

Nenhum PNG binário é versionado aqui, e isso é decisão de projeto, não
economia de espaço:

* um golden test precisa poder dizer **por que** a entrada é o que é — um
  arquivo `.png` no repositório não explica que ele tem 300 cores e alpha
  suave de propósito, o código explica;
* um PNG gravado por uma versão do Pillow e lido por outra pode voltar
  diferente; um array construído por aritmética inteira volta sempre igual;
* a entrada precisa ser **derivável**: se amanhã o golden test de 64×64
  precisar da mesma cena em 128×128, é um argumento, não um arquivo novo.

Tudo aqui é determinístico por construção: só ``numpy.mgrid``, aritmética e
tabelas literais. Não existe ``random`` — nem semeado —, para que o resultado
não dependa da versão do gerador de números aleatórios do numpy.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

__all__ = [
    "SPRITE_PALETTE",
    "SPRITE_ROWS",
    "fake_pixel_art",
    "pixel_perfect_sprite",
    "upscale_nearest",
]


# ---------------------------------------------------------------------------
# (a) A "falsa Pixel Art" do plano Pixel §91
# ---------------------------------------------------------------------------
def fake_pixel_art(size: int = 512) -> Image.Image:
    """A imagem que um gerador de imagens devolve quando se pede "pixel art".

    Ela tem exatamente os três defeitos que o plano Pixel §91 usa como caso
    de teste, e cada um vem de uma parte diferente da construção:

    ``centenas de cores``
        os canais R e G variam continuamente com a posição e o B com a
        distância ao centro. Nenhum patamar, nenhuma paleta — o oposto de
        Pixel Art.
    ``alpha suave``
        o alpha é uma rampa linear sobre uma faixa de vários pixels em volta
        da silhueta, e não um corte. É a "franja" translúcida que aparece ao
        ampliar o sprite no jogo.
    ``bordas interpoladas``
        a borda da elipse e a do detalhe interno caem por rampa, então
        existem pixels de transição que não pertencem nem ao sprite nem ao
        fundo — a marca de uma imagem que foi *pintada*, não desenhada em uma
        grade.

    O tamanho é parâmetro porque a resolução de render do profile já mudou
    uma vez (512 → 1024) e a fixture não pode ser a razão para não mudar de
    novo.
    """
    if size < 8:
        raise ValueError("fake_pixel_art precisa de pelo menos 8 pixels de lado")

    rows, cols = np.mgrid[0:size, 0:size].astype(np.float64)
    center = (size - 1) / 2.0

    # Elipse levemente mais alta que larga: um "personagem", não um círculo.
    normal_x = (cols - center) / (size * 0.34)
    normal_y = (rows - center * 1.05) / (size * 0.42)
    distance = np.sqrt(normal_x**2 + normal_y**2)

    # A rampa de alpha cobre ~1/12 do raio: larga o bastante para produzir
    # dezenas de valores parciais distintos, estreita o bastante para a
    # silhueta continuar reconhecível.
    alpha = np.clip((1.0 - distance) * 12.0, 0.0, 1.0) * 255.0

    # Um detalhe interno mais claro, também com borda interpolada: garante que
    # a imagem tenha estrutura, e não só um degradê radial.
    detail = np.clip(
        1.0
        - np.sqrt(
            ((cols - center * 0.78) / (size * 0.11)) ** 2
            + ((rows - center * 0.72) / (size * 0.11)) ** 2
        ),
        0.0,
        1.0,
    )

    red = 40.0 + 170.0 * (cols / (size - 1)) + 45.0 * detail
    green = 30.0 + 150.0 * (rows / (size - 1)) + 70.0 * detail
    blue = 70.0 + 130.0 * np.clip(1.0 - distance, 0.0, 1.0) + 30.0 * detail

    array = np.empty((size, size, 4), dtype=np.uint8)
    array[:, :, 0] = np.clip(red, 0, 255).astype(np.uint8)
    array[:, :, 1] = np.clip(green, 0, 255).astype(np.uint8)
    array[:, :, 2] = np.clip(blue, 0, 255).astype(np.uint8)
    array[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return Image.fromarray(array, mode="RGBA")


# ---------------------------------------------------------------------------
# (b) O sprite que já é Pixel Art de verdade
# ---------------------------------------------------------------------------
#: Cores do sprite. Há pares deliberadamente próximos (``corpo``/``corpo_luz``,
#: ``contorno``/``pupila``, ``metal``/``metal_sombra``): é o que faz uma
#: quantização com orçamento apertado ter de escolher, em vez de caber sem
#: mexer em nada.
SPRITE_PALETTE: dict[str, tuple[int, int, int, int]] = {
    ".": (0, 0, 0, 0),          # fundo — transparente puro
    "o": (20, 18, 31, 255),     # contorno
    "p": (32, 28, 46, 255),     # pupila (quase o contorno)
    "b": (79, 121, 66, 255),    # corpo
    "B": (61, 95, 52, 255),     # corpo, sombra
    "h": (109, 154, 88, 255),   # corpo, luz
    "s": (224, 168, 120, 255),  # pele
    "S": (192, 138, 94, 255),   # pele, sombra
    "e": (255, 255, 255, 255),  # olho
    "m": (184, 192, 208, 255),  # metal
    "M": (135, 144, 166, 255),  # metal, sombra
}

#: Sprite 16×16 desenhado na grade — cada caractere é um pixel lógico.
SPRITE_ROWS: tuple[str, ...] = (
    "......oooo......",
    ".....osssso.....",
    "....ossessso....",
    "....osepesso....",
    "....osssssSo....",
    ".....oSSSSo.....",
    "...oobbbbbboo...",
    "..obhbbbbbbhbo..",
    "..obhbbbbbbhbo..",
    "..ossbbbbbbsso..",
    "...oobbbbbboo...",
    "....oBBooBBo....",
    "....oBBooBBo....",
    "....oBBooBBo....",
    "...omMo..omMo...",
    "...ooo....ooo...",
)


def pixel_perfect_sprite() -> Image.Image:
    """Sprite 16×16 já Pixel Exact: um pixel do desenho = um pixel do PNG.

    Ele é o *gabarito* do golden test de reconstrução: é o resultado que o
    pipeline deveria recuperar depois de a imagem ter passado por uma
    ampliação de 32× (plano Pixel §90).

    O fundo é ``(0, 0, 0, 0)`` — transparente **e** com RGB zerado — porque é
    assim que o ``AlphaNormalizer`` deixa todo pixel invisível. Um gabarito
    com fundo preto opaco ou com cor residual nos pixels transparentes
    obrigaria o teste a comparar só a região opaca, e a comparação deixaria de
    cobrir o canvas inteiro.
    """
    height = len(SPRITE_ROWS)
    width = len(SPRITE_ROWS[0])
    if any(len(row) != width for row in SPRITE_ROWS):
        raise ValueError("SPRITE_ROWS tem linhas de larguras diferentes")

    array = np.zeros((height, width, 4), dtype=np.uint8)
    for y, row in enumerate(SPRITE_ROWS):
        for x, char in enumerate(row):
            array[y, x] = SPRITE_PALETTE[char]
    return Image.fromarray(array, mode="RGBA")


def upscale_nearest(image: Image.Image, factor: int) -> Image.Image:
    """Amplia por replicação inteira — a origem "já em blocos" do §18.

    ``np.repeat`` nos dois eixos, e não ``Image.resize``: a fixture é a
    referência contra a qual o ``block_vote`` é medido, e ela não pode
    depender do mesmo Pillow que o código sob teste usa. Replicação escrita à
    mão é a definição literal de "cada pixel virou um bloco".
    """
    if factor < 1:
        raise ValueError("o fator de ampliação precisa ser >= 1")
    array = np.array(image.convert("RGBA"), dtype=np.uint8)
    blocks = np.repeat(np.repeat(array, factor, axis=0), factor, axis=1)
    return Image.fromarray(blocks, mode="RGBA")
