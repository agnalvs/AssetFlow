"""Estágios de geometria do Pixel Exact: entrada, canvas e redução lógica.

Estes três estágios decidem a **forma** do asset — em que modo a imagem entra,
em que aspect ratio ela é enquadrada e em que grade ela termina. Alpha, paleta
e limpeza vêm depois e são cobertos por outros arquivos.

As imagens de teste são sintéticas e montadas com numpy porque a afirmação que
interessa é geométrica: "não foi esticado", "continua centralizado", "continua
redondo". Com geometria conhecida essas frases viram assertivas exatas, e o
teste não depende de motor, modelo nem arquivo de fixture.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from assetflow.pixel.contracts.output_spec import PixelOutputSpec
from assetflow.pixel.imaging import bounding_box, count_colors, opaque_mask, to_array
from assetflow.pixel.processing.service import PixelPostProcessor
from assetflow.pixel.processing.stages import (
    CanvasNormalizer,
    InputNormalizer,
    LogicalPixelReducer,
)
from assetflow.pixel.processing.stages.base import PixelContext

#: Paleta fixa dos mosaicos. Cores bem separadas de propósito: com
#: ``vote_bins=16`` cada uma cai em um balde diferente do ``block_vote``, então
#: a votação nunca é decidida por arredondamento.
_PALETA: tuple[tuple[int, int, int], ...] = (
    (200, 40, 40),
    (20, 180, 60),
    (40, 60, 200),
    (250, 250, 250),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _spec(**overrides) -> PixelOutputSpec:
    """Spec 64×64 — o alvo lógico é o mesmo em todos os testes deste arquivo."""
    payload: dict = {"logical_size": {"width": 64, "height": 64}}
    payload.update(overrides)
    return PixelOutputSpec.model_validate(payload)


def _contexto(spec: PixelOutputSpec) -> PixelContext:
    """Contexto de um estágio isolado — o caderno onde ele anota os detalhes."""
    return PixelContext(spec=spec)


def _ruido(width: int, height: int, *, seed: int) -> Image.Image:
    """Imagem opaca de ruído determinístico (``default_rng`` com semente fixa).

    Ruído é o pior caso para quem copia pixels: qualquer reamostragem, ainda
    que de um pixel só, muda o conteúdo e o teste percebe.
    """
    rng = np.random.default_rng(seed)
    array = rng.integers(0, 256, size=(height, width, 4), dtype=np.uint8)
    array[:, :, 3] = 255
    return Image.fromarray(array, "RGBA")


def _retangulo(
    size: tuple[int, int],
    box: tuple[int, int, int, int],
    color: tuple[int, int, int] = _PALETA[0],
) -> Image.Image:
    """Canvas transparente com um retângulo opaco em ``box`` (fim exclusivo)."""
    width, height = size
    left, top, right, bottom = box
    array = np.zeros((height, width, 4), dtype=np.uint8)
    array[top:bottom, left:right] = (*color, 255)
    return Image.fromarray(array, "RGBA")


def _circulo(size: int, radius: float) -> Image.Image:
    """Círculo opaco centralizado em um canvas quadrado transparente.

    A distância é medida do **centro do pixel** (``x + 0.5``) até o centro
    geométrico do canvas: assim a figura é exatamente simétrica nos dois eixos,
    e uma silhueta preservada continua simétrica depois da redução.
    """
    rows, cols = np.mgrid[0:size, 0:size]
    center = size / 2
    distance = (cols + 0.5 - center) ** 2 + (rows + 0.5 - center) ** 2
    array = np.zeros((size, size, 4), dtype=np.uint8)
    array[distance <= radius**2] = (*_PALETA[0], 255)
    return Image.fromarray(array, "RGBA")


def _mosaico(blocks: int, block: int) -> np.ndarray:
    """Array ``(n, n, 4)`` de blocos uniformes ``block × block`` da paleta fixa."""
    size = blocks * block
    array = np.zeros((size, size, 4), dtype=np.uint8)
    for row in range(blocks):
        for col in range(blocks):
            color = _PALETA[(row + col) % len(_PALETA)]
            array[row * block : (row + 1) * block, col * block : (col + 1) * block] = (
                *color,
                255,
            )
    return array


def _cor(array: np.ndarray, x: int, y: int) -> tuple[int, int, int]:
    """Cor RGB de um pixel, como ``int`` puro (numpy compara mal dentro de tupla)."""
    return tuple(int(value) for value in array[y, x, :3])  # type: ignore[return-value]


def _cores(array: np.ndarray) -> set[tuple[int, int, int]]:
    """Conjunto das cores RGB presentes no array."""
    pixels = array[:, :, :3].reshape(-1, 3)
    return {tuple(int(value) for value in pixel) for pixel in pixels}


# ---------------------------------------------------------------------------
# InputNormalizer (plano Pixel §12)
# ---------------------------------------------------------------------------
def _no_modo(modo: str) -> Image.Image:
    """Imagem 8×8 com 64 cores distintas, no modo pedido."""
    rampa = np.arange(64, dtype=np.uint8).reshape(8, 8)
    if modo == "L":
        return Image.fromarray(rampa, "L")
    if modo == "P":
        return Image.fromarray(rampa, "L").convert("P")
    if modo == "RGB":
        array = np.zeros((8, 8, 3), dtype=np.uint8)
        array[:, :, 0] = rampa
        array[:, :, 1] = 128
        array[:, :, 2] = 255 - rampa
        return Image.fromarray(array, "RGB")
    raise AssertionError(f"modo de teste desconhecido: {modo}")


@pytest.mark.parametrize("modo", ["L", "P", "RGB"])
def test_input_normalizer_converts_any_mode_to_rgba(modo: str):
    """Plano Pixel §12: o resto do módulo só sabe trabalhar em RGBA.

    Um modo sem canal alpha vira RGBA **totalmente opaco** — inventar
    transparência aqui esconderia do ``PX-EMPTY-001`` uma imagem que na origem
    não tinha buraco nenhum. E a conversão não pode fundir tons: as 64 cores
    que entraram continuam sendo 64 na saída.
    """
    origem = _no_modo(modo)

    resultado = InputNormalizer().apply(origem, _contexto(_spec()))
    array = to_array(resultado)

    assert resultado.mode == "RGBA"
    assert resultado.size == origem.size
    assert set(np.unique(array[:, :, 3]).tolist()) == {255}
    assert count_colors(array) == 64


def test_input_normalizer_rejects_degenerate_image():
    """Um eixo zerado precisa morrer na porta de entrada, não três estágios adiante.

    Sem largura ou sem altura não existe conteúdo para enquadrar nem para
    reduzir. Deixar passar trocaria uma mensagem clara por um estouro dentro do
    numpy, com um erro que não diz nada sobre a imagem recebida.
    """
    with pytest.raises(ValueError, match="degenerada"):
        InputNormalizer().apply(Image.new("RGBA", (0, 8)), _contexto(_spec()))


def test_input_normalizer_applies_solid_background_only_when_asked():
    """Plano Pixel §12: ``background.mode`` decide, e o padrão não mexe em nada.

    Com ``solid`` o transparente é composto sobre a cor pedida e o que já era
    opaco permanece intacto. Com ``transparent`` — o padrão — o estágio não
    toca no alpha: adicionar ou remover fundo automaticamente não faz parte do
    Pixel Exact 1.0.
    """
    origem = _retangulo((8, 8), (2, 2, 6, 6), color=(10, 20, 30))

    contexto = _contexto(_spec(background={"mode": "solid", "color": "#ff0000"}))
    solido = to_array(InputNormalizer().apply(origem, contexto))

    assert contexto.details["background_applied"] is True
    assert _cor(solido, 0, 0) == (255, 0, 0)
    assert int(solido[0, 0, 3]) == 255
    assert _cor(solido, 3, 3) == (10, 20, 30), "o sprite não pode ser recolorido"

    contexto = _contexto(_spec())
    transparente = to_array(InputNormalizer().apply(origem, contexto))

    assert contexto.details["background_applied"] is False
    assert int(transparente[0, 0, 3]) == 0


def test_input_normalizer_does_not_resize_or_quantize():
    """Plano Pixel §12: aqui é proibido resize e redução de paleta.

    O spec pede 64×64 e 16 cores, mas quem entrega isso são o
    ``LogicalPixelReducer`` e o ``PaletteQuantizer``. Se este estágio
    antecipasse qualquer um dos dois, estaria adulterando pixels que ainda vão
    ser reamostrados — e sem registro próprio no relatório.
    """
    origem = _ruido(97, 53, seed=11)
    cores_antes = count_colors(to_array(origem))
    spec = _spec()

    resultado = InputNormalizer().apply(origem, _contexto(spec))
    array = to_array(resultado)

    assert resultado.size == (97, 53)
    assert resultado.size != spec.target_size
    assert count_colors(array) == cores_antes
    assert cores_antes > (spec.max_colors or 0), "sem muitas cores o teste não prova nada"


# ---------------------------------------------------------------------------
# CanvasNormalizer (plano Pixel §13 e §14)
# ---------------------------------------------------------------------------
def test_canvas_contain_reaches_target_aspect_without_stretching():
    """Plano Pixel §13: 1024×768 chega ao aspect 1:1 sem achatar o personagem.

    A conta que motiva o estágio: esticar 1024×768 até 64×64 comprime o eixo
    horizontal em 25%. ``contain`` resolve preenchendo, não escalando — por
    isso o teste não se contenta com o tamanho resultante e compara o
    **conteúdo**: os 1024×768 originais precisam reaparecer byte a byte dentro
    do canvas 1024×1024, deslocados apenas pelo pad.
    """
    origem = _ruido(1024, 768, seed=3)
    contexto = _contexto(_spec())

    resultado = CanvasNormalizer().apply(origem, contexto)
    array = to_array(resultado)

    assert resultado.size == (1024, 1024)
    assert contexto.details["aspect_before"] != 1.0
    assert contexto.details["aspect_after"] == 1.0
    assert contexto.details["padded"] is True
    assert contexto.details["cropped"] is False, "contain não descarta pixel"

    topo = (1024 - 768) // 2
    assert np.array_equal(array[topo : topo + 768], to_array(origem))


def test_canvas_cover_crops_instead_of_padding():
    """Plano Pixel §14: ``cover`` promete cobrir o alvo descartando o excedente.

    O oposto de ``contain``: nada de sobra preenchida, e o que sobrevive é a
    janela central da origem — copiada, nunca reamostrada.
    """
    origem = _ruido(1024, 768, seed=5)
    contexto = _contexto(_spec(canvas={"mode": "cover"}))

    resultado = CanvasNormalizer().apply(origem, contexto)

    assert resultado.size == (768, 768), "em cover quem manda é o menor lado"
    assert contexto.details["cropped"] is True
    assert contexto.details["padded"] is False
    esquerda = (1024 - 768) // 2
    assert np.array_equal(
        to_array(resultado), to_array(origem)[:, esquerda : esquerda + 768]
    )


def test_canvas_center_crop_returns_the_logical_window():
    """Plano Pixel §14: ``center_crop`` recorta o centro no tamanho lógico, 1:1.

    É o modo de fontes que já estão na grade: cada pixel de origem vira um
    pixel lógico, sem passar por escala nenhuma.
    """
    origem = _ruido(1024, 768, seed=8)
    contexto = _contexto(_spec(canvas={"mode": "center_crop"}))

    resultado = CanvasNormalizer().apply(origem, contexto)

    assert resultado.size == (64, 64)
    esquerda, topo = (1024 - 64) // 2, (768 - 64) // 2
    assert np.array_equal(
        to_array(resultado),
        to_array(origem)[topo : topo + 64, esquerda : esquerda + 64],
    )


def test_canvas_transparent_pad_centers_a_smaller_source():
    """Plano Pixel §14: ``transparent_pad`` centraliza no canvas lógico e preenche.

    Mesma geometria do ``center_crop``, vista do outro lado — origem menor que
    o alvo. O conteúdo não é ampliado para caber: ele é posicionado.
    """
    origem = _retangulo((20, 10), (0, 0, 20, 10))
    contexto = _contexto(_spec(canvas={"mode": "transparent_pad"}))

    resultado = CanvasNormalizer().apply(origem, contexto)
    array = to_array(resultado)

    assert resultado.size == (64, 64)
    assert contexto.details["padded"] is True
    assert contexto.details["cropped"] is False
    # (64-20)//2 = 22 e (64-10)//2 = 27; a caixa devolvida é inclusiva.
    assert bounding_box(opaque_mask(array)) == (22, 27, 41, 36)
    assert int(array[0, 0, 3]) == 0, "a sobra fica transparente"


def test_canvas_stretch_leaves_the_scaling_to_the_reducer():
    """Plano Pixel §14: ``stretch`` é no-op aqui — quem deforma é o reducer.

    O estágio devolve a origem intocada (não recorta nem preenche), e é o
    ``LogicalPixelReducer`` que leva 1024×768 até 64×64 deformando o aspect.
    Separar as duas coisas é o que impede que uma deformação aconteça por
    acidente em qualquer outro modo.
    """
    spec = _spec(canvas={"mode": "stretch"})
    origem = _ruido(1024, 768, seed=13)
    contexto = _contexto(spec)

    enquadrada = CanvasNormalizer().apply(origem, contexto)

    assert enquadrada.size == origem.size
    assert contexto.details["padded"] is False
    assert contexto.details["cropped"] is False
    assert contexto.details["aspect_after"] == contexto.details["aspect_before"] != 1.0
    assert np.array_equal(to_array(enquadrada), to_array(origem))

    reduzida = LogicalPixelReducer().apply(enquadrada, _contexto(spec))
    assert reduzida.size == (64, 64)


def test_canvas_trim_transparent_adds_the_margin_of_the_plan():
    """Plano Pixel §61: recortar a caixa do conteúdo não pode colar o sprite na borda.

    ``trim_transparent`` sozinho produz exatamente o defeito que a segunda
    tentativa deveria corrigir (``PX-BOUND-001``): a bounding box encosta nos
    quatro lados por construção. A folga de 4% é a correção automática — o
    conteúdo para de tocar a borda e o aspect continua sendo o do alvo.
    """
    origem = _retangulo((128, 128), (0, 0, 80, 80))
    contexto = _contexto(_spec(canvas={"mode": "contain", "trim_transparent": True}))

    resultado = CanvasNormalizer().apply(origem, contexto)
    array = to_array(resultado)

    margem = contexto.details["margin_px"]
    assert contexto.details["trimmed_box"] == (0, 0, 79, 79), (
        "antes do trim o conteúdo já encostava em duas bordas"
    )
    assert margem >= 1
    assert resultado.size == (80 + 2 * margem, 80 + 2 * margem)
    assert contexto.details["aspect_after"] == 1.0

    esquerda, topo, direita, baixo = bounding_box(opaque_mask(array))
    largura, altura = resultado.size
    assert (esquerda, topo) == (margem, margem)
    assert (direita, baixo) == (largura - 1 - margem, altura - 1 - margem)


# ---------------------------------------------------------------------------
# LogicalPixelReducer (plano Pixel §15 a §20)
# ---------------------------------------------------------------------------
def test_logical_reducer_delivers_the_exact_logical_size():
    """Teste de dimensão do plano Pixel §84: 512×512 com alvo 64×64 sai 64×64.

    É a regra de ouro nº 1 (§3) medida no estágio que a produz: um asset 64×64
    é um PNG de 64×64, não um PNG grande com quadradinhos desenhados.
    """
    contexto = _contexto(_spec())

    resultado = LogicalPixelReducer().apply(_circulo(512, 200), contexto)

    assert resultado.size == (64, 64)
    assert contexto.details["source_size"] == (512, 512)
    assert contexto.details["target_size"] == (64, 64)
    assert contexto.shared["logical_size"] == (64, 64)


def test_logical_reducer_box_preserves_the_silhouette():
    """Plano Pixel §16: ao reduzir 8×, ``BOX`` guarda a forma; nearest a sortearia.

    O círculo tem raio 200 em 512px, ou seja 25px na grade lógica. Depois da
    redução ele precisa continuar (a) centralizado, (b) simétrico nos dois
    eixos e (c) com a área de um círculo de raio 25 — três medidas que uma
    amostragem por ponto não tem como garantir, porque nearest depende do
    alinhamento da grade e não do desenho.

    A máscara é lida com o limiar do spec porque o alpha ainda é contínuo neste
    ponto: binarizar é trabalho do ``AlphaNormalizer``, mais adiante.
    """
    spec = _spec()
    contexto = _contexto(spec)

    resultado = LogicalPixelReducer().apply(_circulo(512, 200), contexto)
    array = to_array(resultado)
    mascara = opaque_mask(array, threshold=spec.alpha.threshold)

    assert contexto.details["resample"] == "box"

    esquerda, topo, direita, baixo = bounding_box(mascara)
    assert esquerda == 63 - direita, "continua centralizado no eixo x"
    assert topo == 63 - baixo, "continua centralizado no eixo y"
    assert (direita - esquerda) == (baixo - topo), "continua redondo, não oval"
    assert np.array_equal(mascara, mascara[:, ::-1])
    assert np.array_equal(mascara, mascara[::-1, :])

    area_esperada = np.pi * 25.0**2
    assert abs(int(mascara.sum()) - area_esperada) / area_esperada < 0.05


def test_logical_reducer_upscales_with_nearest_without_inventing_colors():
    """Plano Pixel §16: ampliar é replicar — nenhum tom intermediário pode nascer.

    Com a origem menor que o alvo não existe informação nova para inventar. Um
    filtro suavizado criaria a borda cinza esfumada que o Pixel Exact existe
    para não entregar; por isso o conjunto de cores da saída precisa ser
    subconjunto do da entrada.
    """
    origem = Image.fromarray(_mosaico(blocks=8, block=2), "RGBA")
    contexto = _contexto(_spec())

    resultado = LogicalPixelReducer().apply(origem, contexto)

    assert resultado.size == (64, 64)
    assert contexto.details["resample"] == "nearest"
    assert _cores(to_array(resultado)) <= set(_PALETA)


def test_block_vote_gives_each_logical_pixel_its_block_color():
    """Plano Pixel §18: com múltiplo exato, o pixel lógico é o voto do seu bloco.

    Em 512→64 cada pixel lógico tem um bloco de 8×8 bem definido. Blocos
    uniformes precisam sair com a cor exata do bloco. E o bloco misturado
    (48 pixels de uma cor contra 16 de outra) prova que a decisão é **votação**
    e não média: a média dos dois tons não é nenhuma das duas cores.
    """
    array = _mosaico(blocks=64, block=8)
    maioria, minoria = _PALETA[0], _PALETA[1]
    array[0:8, 8:16] = (*maioria, 255)
    array[0:2, 8:16] = (*minoria, 255)

    contexto = _contexto(_spec(logical_reduction={"method": "block_vote"}))
    resultado = LogicalPixelReducer().apply(Image.fromarray(array, "RGBA"), contexto)
    saida = to_array(resultado)

    assert resultado.size == (64, 64)
    assert contexto.details["resample"] == "block_vote"
    assert contexto.details["block_size"] == (8, 8)
    assert contexto.details["fallback"] is None

    assert _cor(saida, 1, 0) == maioria
    media = tuple(round((3 * um + outro) / 4) for um, outro in zip(maioria, minoria))
    assert _cor(saida, 1, 0) != media, "votação, não média de área"

    esperado = np.array(
        [[_PALETA[(row + col) % len(_PALETA)] for col in range(64)] for row in range(64)],
        dtype=np.uint8,
    )
    esperado[0, 1] = maioria
    assert np.array_equal(saida[:, :, :3], esperado)
    assert set(np.unique(saida[:, :, 3]).tolist()) == {255}


def test_block_vote_falls_back_to_box_when_size_is_not_a_multiple():
    """Plano Pixel §18: sem múltiplo inteiro não existe "o bloco deste pixel".

    100×100 para 64×64 daria blocos de larguras diferentes — o oposto de
    determinístico. O estágio então reduz por média de área e **registra** a
    troca: um resultado que não saiu do algoritmo pedido só é comparável em um
    benchmark se o relatório disser isso (plano Pixel §74 e §76).
    """
    origem = Image.fromarray(_mosaico(blocks=50, block=2), "RGBA")
    spec = _spec(logical_reduction={"method": "block_vote"})

    resultado = PixelPostProcessor([LogicalPixelReducer()]).process(origem, spec)
    relatorio = resultado.report

    assert resultado.image.size == (64, 64)

    etapa = relatorio.step("pixel.logical_reducer")
    assert etapa is not None and etapa.applied
    assert etapa.details["fallback"] == "box"
    assert etapa.details["resample"] == "box"
    assert etapa.details["block_size"] is None
    assert relatorio.logical_reduction == "block_vote", (
        "o relatório continua dizendo o que o profile pediu"
    )
    assert any("block_vote" in aviso for aviso in relatorio.warnings)
