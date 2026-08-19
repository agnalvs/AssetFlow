"""Testes dos estágios de cor do Pixel Exact: alpha, paleta e limpeza.

São três estágios que rodam em sequência (plano Pixel §8) e cada um protege uma
regra de ouro diferente:

``AlphaNormalizer``
    alpha só pode ser 0 ou 255 (plano Pixel §21 a §24, TESTE DE ALPHA do §85);
``PaletteQuantizer``
    o conjunto de cores é exato, e paleta travada é travada mesmo
    (plano Pixel §25 a §28, TESTES DE PALETA do §86 e §87);
``ConservativeCleaner``
    detectar não é remover — a limpeza corrige só o inequívoco
    (plano Pixel §29 a §31 e a regra de ouro do §106).

Os estágios são exercitados **isolados**, com um ``PixelOutputSpec`` montado à
mão: o contrato de um estágio é ``(imagem, spec) -> imagem``, e testá-lo pelo
pipeline inteiro esconderia qual etapa produziu o resultado.

Nenhuma imagem aqui vem de arquivo ou de sorteio: todas são construídas pixel a
pixel pelos helpers abaixo, para que a expectativa de cada teste possa ser
calculada, e não observada.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from assetflow.pixel.contracts.output_spec import PixelOutputSpec
from assetflow.pixel.imaging import alpha_values, color_counts, count_colors, to_array
from assetflow.pixel.processing.service import PixelPostProcessor
from assetflow.pixel.processing.stages.alpha_normalizer import AlphaNormalizer
from assetflow.pixel.processing.stages.base import PixelContext
from assetflow.pixel.processing.stages.conservative_cleaner import ConservativeCleaner
from assetflow.pixel.processing.stages.palette_quantizer import PaletteQuantizer

#: Cor de fundo dos campos sólidos usados pelos testes de limpeza.
_FUNDO = (60, 60, 60)


# ---------------------------------------------------------------------------
# Helpers — todas as imagens dos testes nascem aqui
# ---------------------------------------------------------------------------
def _spec(width: int = 64, height: int = 64, **overrides: Any) -> PixelOutputSpec:
    """``PixelOutputSpec`` mínimo, com os sub-specs pedidos por teste."""
    return PixelOutputSpec.model_validate(
        {"logical_size": {"width": width, "height": height}, **overrides}
    )


def _contexto(spec: PixelOutputSpec) -> PixelContext:
    return PixelContext(spec=spec)


def _imagem(array: np.ndarray) -> Image.Image:
    return Image.fromarray(np.ascontiguousarray(array, dtype=np.uint8), mode="RGBA")


def _tira_de_alphas(alphas: list[int]) -> np.ndarray:
    """Uma linha de pixels, cada um com um alpha e um RGB próprio e não-zero.

    O RGB distinto por pixel é o que permite verificar depois quem teve a cor
    zerada e quem manteve a sua.
    """
    array = np.zeros((1, len(alphas), 4), dtype=np.uint8)
    for indice, alpha in enumerate(alphas):
        array[0, indice] = (10 + indice, 20 + indice, 30 + indice, alpha)
    return array


def _gradiente_multicolorido(width: int, height: int) -> np.ndarray:
    """Imagem opaca com uma cor distinta por pixel — o pior caso do quantizador."""
    array = np.zeros((height, width, 4), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            array[y, x] = ((x * 4) % 256, (y * 4) % 256, (x * 7 + y * 11) % 256, 255)
    return array


def _campo_solido(size: int = 32, cor: tuple[int, int, int] = _FUNDO) -> np.ndarray:
    """Retângulo totalmente opaco de uma cor só."""
    array = np.zeros((size, size, 4), dtype=np.uint8)
    array[:, :, :3] = cor
    array[:, :, 3] = 255
    return array


def _sprite_com_ruido() -> np.ndarray:
    """Sprite 64×64 em três faixas com quatro pixels isolados de cores raras.

    As quatro situações do plano Pixel §30 aparecem de uma vez: dois pixels
    interiores com vizinhança unânime (corrigíveis), um na fronteira entre
    faixas (vizinhos discordantes) e um na borda do canvas (contorno).
    """
    array = np.zeros((64, 64, 4), dtype=np.uint8)
    array[:, :, 3] = 255
    array[0:21, :, :3] = (30, 40, 90)
    array[21:42, :, :3] = (120, 60, 40)
    array[42:, :, :3] = (200, 190, 90)
    array[10, 10, :3] = (250, 0, 0)
    array[30, 30, :3] = (0, 250, 0)
    array[21, 33, :3] = (0, 0, 250)
    array[0, 20, :3] = (250, 0, 250)
    return array


def _cores_opacas(image: Image.Image) -> set[str]:
    """Conjunto das cores hexadecimais presentes entre os pixels opacos."""
    return set(color_counts(to_array(image)))


# ---------------------------------------------------------------------------
# AlphaNormalizer — TESTE DE ALPHA (plano Pixel §85)
# ---------------------------------------------------------------------------
def test_alpha_normalizer_leaves_only_zero_and_255():
    """TESTE DE ALPHA do plano Pixel §85: não sobra nenhum alpha intermediário.

    Um alpha 120 sobrevivente vira, na ampliação nearest da engine, um bloco
    translúcido no meio do contorno — a "franja suja" que o §21 proíbe. Os
    valores da entrada cercam o limiar padrão (128) pelos dois lados para que
    o teste falhe tanto se o corte sumir quanto se ele inverter.
    """
    entrada = [0, 12, 120, 200, 255]
    contexto = _contexto(_spec(width=len(entrada), height=1))

    resultado = to_array(
        AlphaNormalizer().apply(_imagem(_tira_de_alphas(entrada)), contexto)
    )

    assert alpha_values(resultado) == (0, 255)
    assert list(resultado[0, :, 3]) == [0, 0, 0, 255, 255]
    assert contexto.details["semitransparent_before"] == 3
    assert contexto.details["opaque_after"] == 2
    assert contexto.details["transparent_after"] == 3


def test_alpha_threshold_is_the_exact_cut_point():
    """O corte é ``>= threshold``, e o limiar vem do spec — não do código.

    Os dois pixels do teste são vizinhos no eixo do alpha: ``threshold`` e
    ``threshold - 1``. Rodar com dois limiares diferentes impede que a
    implementação passe no teste com o 128 gravado à mão (plano Pixel §64).
    """
    for limiar in (128, 200):
        array = np.zeros((1, 2, 4), dtype=np.uint8)
        array[0, 0] = (255, 255, 255, limiar)
        array[0, 1] = (255, 255, 255, limiar - 1)
        contexto = _contexto(_spec(width=2, height=1, alpha={"threshold": limiar}))

        resultado = to_array(AlphaNormalizer().apply(_imagem(array), contexto))

        assert list(resultado[0, :, 3]) == [255, 0], f"limiar {limiar}"
        assert contexto.details["threshold"] == limiar


def test_solid_background_forces_every_pixel_opaque():
    """Fundo sólido não convive com buraco transparente (plano Pixel §22).

    Se o profile pediu um fundo pintado, recortar o alpha deixaria um furo
    sobre a própria tinta — contraditório. Aqui até o pixel de alpha 0 sai
    opaco, e com o RGB original preservado.
    """
    entrada = [0, 12, 120, 200, 255]
    array = _tira_de_alphas(entrada)
    contexto = _contexto(
        _spec(
            width=len(entrada),
            height=1,
            background={"mode": "solid", "color": "#101010"},
        )
    )

    resultado = to_array(AlphaNormalizer().apply(_imagem(array), contexto))

    assert alpha_values(resultado) == (255,)
    assert np.array_equal(
        resultado[:, :, :3], array[:, :, :3]
    ), "forçar opacidade não pode repintar o sprite"
    assert contexto.details["forced_opaque"] is True


def test_transparent_pixels_lose_their_rgb():
    """Pixel invisível não guarda cor — a "cor fantasma" do plano Pixel §23.

    A cor de um pixel de alpha 0 reaparece ao ampliar ou borrar em um editor e
    contamina a leitura da paleta do estágio seguinte. O RGB dos pixels que
    ficaram opacos, por outro lado, precisa continuar intacto: zerar demais
    seria tão errado quanto não zerar.
    """
    entrada = [0, 12, 120, 200, 255]
    array = _tira_de_alphas(entrada)
    contexto = _contexto(_spec(width=len(entrada), height=1))

    resultado = to_array(AlphaNormalizer().apply(_imagem(array), contexto))

    invisiveis = resultado[:, :, 3] == 0
    assert int(invisiveis.sum()) == 3
    assert not resultado[invisiveis][:, :3].any(), "pixel transparente com RGB residual"
    visiveis = ~invisiveis
    assert np.array_equal(resultado[visiveis][:, :3], array[visiveis][:, :3])


# ---------------------------------------------------------------------------
# PaletteQuantizer — TESTES DE PALETA (plano Pixel §86 e §87)
# ---------------------------------------------------------------------------
def test_palette_quantizer_enforces_the_color_limit():
    """TESTE DE PALETA do plano Pixel §86: centenas de cores entram, 16 saem.

    O limite é uma garantia dura, não um alvo do median cut: o check
    PX-COLOR-001 reprova em 17 cores, então o estágio precisa terminar com
    ``<= max_colors`` mesmo quando o quantizador do Pillow devolve sobra.
    """
    array = _gradiente_multicolorido(64, 64)
    assert count_colors(array) > 200, "sem centenas de cores o teste não prova nada"
    contexto = _contexto(_spec(palette={"mode": "max_colors", "max_colors": 16}))

    resultado = PaletteQuantizer().apply(_imagem(array), contexto)

    assert count_colors(to_array(resultado)) <= 16
    assert len(contexto.shared["palette"]) <= 16
    assert contexto.details["final_colors"] == count_colors(to_array(resultado))


def test_locked_palette_admits_no_foreign_color():
    """TESTE DE PALETA TRAVADA do plano Pixel §87: nenhuma cor de fora sobrevive.

    Uma única cor intermediária já quebra a coerência entre personagem, inimigo
    e tile do mesmo mundo (§11) — e é exatamente o que o check PX-PALETTE-001
    procura. A entrada é o pior caso: uma imagem cujas cores não têm nenhuma
    interseção com a paleta pedida.
    """
    travada = ("#1a1c2c", "#5d275d", "#b13e53", "#ef7d57", "#ffcd75", "#38b764")
    array = _gradiente_multicolorido(64, 64)
    contexto = _contexto(_spec(palette={"mode": "locked", "colors": list(travada)}))

    resultado = PaletteQuantizer().apply(_imagem(array), contexto)

    assert _cores_opacas(resultado) <= set(travada)
    assert set(contexto.shared["palette"]) <= set(travada)
    assert contexto.details["mode"] == "locked", "o relatório precisa dizer que travou"


def test_transparent_pixels_do_not_spend_palette_entries():
    """Pixel invisível não gasta uma das N cores do sprite (plano Pixel §25).

    O fundo verde-berrante ocupa a maior parte do canvas: se o quantizador
    olhasse a imagem inteira, o median cut reservaria caixas de paleta para
    ele e o sprite perderia nuances de verdade para pintar o que ninguém vê.
    """
    verde = "#00ff00"
    array = np.zeros((32, 32, 4), dtype=np.uint8)
    array[:, :, :3] = (0, 255, 0)  # fundo transparente, mas pintado
    array[8:24, 8:24, 3] = 255
    for i, y in enumerate(range(8, 24)):
        for j, x in enumerate(range(8, 24)):
            array[y, x, :3] = (10 + i * 3, 20 + j * 3, 30 + (i + j) * 2)
    contexto = _contexto(
        _spec(width=32, height=32, palette={"mode": "max_colors", "max_colors": 8})
    )

    resultado = PaletteQuantizer().apply(_imagem(array), contexto)

    assert verde not in contexto.shared["palette"]
    assert verde not in _cores_opacas(resultado)
    assert len(contexto.shared["palette"]) <= 8


def test_quantizer_keeps_transparent_pixels_black():
    """O quantizador não pode desfazer a limpeza de RGB do AlphaNormalizer.

    ``map_to_palette`` pinta **todos** os pixels, inclusive os invisíveis: sem
    cuidado, cada pixel transparente sai com a cor da paleta mais próxima do
    preto. É a "cor fantasma" que o estágio anterior tinha acabado de remover,
    e que reaparece assim que alguém amplia, borra ou baixa o limiar de alpha
    em um editor. Como ``color_counts`` ignora pixels transparentes, nenhum
    hard check pegaria isso — só este teste pega.
    """
    array = np.zeros((16, 16, 4), dtype=np.uint8)
    # Sprite escuro no centro: a cor mais próxima do preto na paleta derivada
    # é justamente a dele, então o fundo herdaria essa cor.
    array[4:12, 4:12, :3] = (20, 18, 31)
    array[4:12, 4:12, 3] = 255

    spec = _spec(16, 16, palette={"mode": "max_colors", "max_colors": 4})
    resultado = to_array(
        PaletteQuantizer().apply(_imagem(array), _contexto(spec))
    )

    transparentes = resultado[resultado[:, :, 3] == 0][:, :3]
    assert transparentes.size, "o teste precisa de pixels transparentes para valer"
    assert np.array_equal(transparentes, np.zeros_like(transparentes)), (
        "pixel invisível saiu do quantizador carregando cor de paleta"
    )
    # E o sprite continua intacto: zerar o fundo não pode custar o conteúdo.
    assert _cores_opacas(_imagem(resultado)) == {"#14121f"}


def test_shared_palette_is_ordered_by_frequency():
    """A paleta publicada em ``context.shared`` vem da cor mais usada para a menos.

    É a ordem que o plano Pixel §54 pede no relatório: quem lê precisa
    reconhecer a cor dominante do sprite na primeira entrada, não caçá-la. O
    teste usa três cores com contagens bem separadas (40/16/8) para que a
    ordem esperada seja calculável, e não uma leitura da implementação.
    """
    array = _campo_solido(size=8, cor=(255, 0, 0))
    array[0:2, :, :3] = (0, 128, 0)
    array[2, :, :3] = (0, 0, 255)
    contexto = _contexto(
        _spec(width=8, height=8, palette={"mode": "max_colors", "max_colors": 16})
    )

    PaletteQuantizer().apply(_imagem(array), contexto)

    assert contexto.shared["palette"] == ("#ff0000", "#008000", "#0000ff")
    assert list(contexto.shared["palette_counts"].values()) == [40, 16, 8]


def test_dithering_is_off_by_default():
    """Dithering é escolha artística, nunca correção técnica (plano Pixel §26).

    Uma área chapada de cinza médio, contra uma paleta preto/branco, é o caso
    em que a difusão de erro se denuncia: ligada, ela salpica a região com as
    duas cores; desligada, a área inteira vai para o vizinho mais próximo e
    continua chapada. O padrão do spec precisa ser o segundo comportamento.
    """
    array = _campo_solido(size=16, cor=(128, 128, 128))
    paleta = {"mode": "locked", "colors": ["#000000", "#ffffff"]}
    padrao = _spec(width=16, height=16, palette=paleta)
    assert padrao.dithering.enabled is False

    contexto = _contexto(padrao)
    chapado = PaletteQuantizer().apply(_imagem(array), contexto)

    assert count_colors(to_array(chapado)) == 1, "a área chapada saiu salpicada"

    # O contraste prova que o resultado acima vem do padrão desligado, e não
    # de a imagem ser indiferente ao dithering.
    ligado = _contexto(
        _spec(width=16, height=16, palette=paleta, dithering={"enabled": True})
    )
    salpicado = PaletteQuantizer().apply(_imagem(array), ligado)
    assert count_colors(to_array(salpicado)) == 2


def test_dithering_enabled_still_respects_the_color_limit():
    """Ligar o dithering não pode furar o teto de cores (plano Pixel §26 e §28).

    A difusão de erro escolhe cores livremente e a tabela de 256 entradas do
    Pillow é um convite a cores de preenchimento; a fusão final existe para
    que o asset caiba no limite de qualquer jeito. Sem o dithering ter mudado
    a imagem, o teste seria vazio — por isso ele também exige a diferença.
    """
    array = _gradiente_multicolorido(64, 64)
    paleta = {"mode": "max_colors", "max_colors": 8}
    sem_dither = PaletteQuantizer().apply(_imagem(array), _contexto(_spec(palette=paleta)))
    contexto = _contexto(_spec(palette=paleta, dithering={"enabled": True}))

    com_dither = PaletteQuantizer().apply(_imagem(array), contexto)

    assert count_colors(to_array(com_dither)) <= 8
    assert len(contexto.shared["palette"]) <= 8
    assert contexto.details["dither"] is True
    assert not np.array_equal(
        to_array(com_dither), to_array(sem_dither)
    ), "o caminho do dithering não chegou a rodar"


# ---------------------------------------------------------------------------
# ConservativeCleaner — a regra de ouro do plano Pixel §106
# ---------------------------------------------------------------------------
def test_isolated_pixel_with_unanimous_neighbours_is_corrected():
    """O único caso de altíssima confiança do plano Pixel §30 é corrigido.

    Pixel interior, opaco, de cor rara (1 em 1024 pixels), cercado pelos 8
    vizinhos opacos e todos da mesma cor: isso é ruído de quantização, não
    desenho. Corrigir aqui é o que justifica o estágio existir.
    """
    array = _campo_solido()
    array[16, 16, :3] = (200, 10, 10)
    contexto = _contexto(_spec(width=32, height=32))

    resultado = to_array(ConservativeCleaner().apply(_imagem(array), contexto))

    assert tuple(resultado[16, 16, :3]) == _FUNDO
    assert contexto.details["candidates"] == 1
    assert contexto.details["corrected"] == 1
    assert count_colors(resultado) == 1


def test_isolated_pixel_on_the_outline_is_never_touched():
    """Contorno é intocável (plano Pixel §30, condição 4, e §31).

    O mesmo pixel do teste anterior, agora com um vizinho transparente, passa
    a fazer parte do contorno do sprite — onde um pixel isolado costuma ser a
    ponta de uma espada ou um brilho, e não ruído. Ele é **detectado** (vira
    candidato e gera aviso), mas a imagem não muda.
    """
    array = _campo_solido()
    array[16, 16, :3] = (200, 10, 10)
    array[15, 15, 3] = 0
    contexto = _contexto(_spec(width=32, height=32))

    resultado = to_array(ConservativeCleaner().apply(_imagem(array), contexto))

    assert tuple(resultado[16, 16, :3]) == (200, 10, 10)
    assert contexto.details["candidates"] == 1
    assert contexto.details["corrected"] == 0
    assert contexto.details["protected_outline"] == 1
    assert any("contorno" in aviso for aviso in contexto.warnings)


def test_isolated_pixel_with_disagreeing_neighbours_only_warns():
    """Vizinhança dividida vira aviso, nunca correção (plano Pixel §31).

    Com três vizinhos de uma cor e cinco de outra não existe "a" cor certa
    para copiar: qualquer escolha seria o AssetFlow inventando desenho. O
    relatório fica sabendo; a imagem, não.
    """
    array = _campo_solido()
    array[16, 16, :3] = (200, 10, 10)
    array[15, 15:18, :3] = (10, 10, 200)  # três vizinhos discordantes
    contexto = _contexto(_spec(width=32, height=32))

    resultado = to_array(ConservativeCleaner().apply(_imagem(array), contexto))

    assert tuple(resultado[16, 16, :3]) == (200, 10, 10)
    assert contexto.details["candidates"] == 1
    assert contexto.details["corrected"] == 0
    assert contexto.details["ambiguous"] == 1
    assert any("ambiguidade" in aviso for aviso in contexto.warnings)


def test_cleanup_off_skips_the_stage_entirely():
    """``cleanup.mode = "off"`` não roda o estágio — e o relatório diz por quê.

    A mesma imagem passa pelo processador duas vezes; a única diferença é o
    profile. Com a limpeza ligada o ruído some, com ela desligada o pixel
    permanece e o passo aparece como ``applied=False`` com motivo registrado
    (plano Pixel §9: um estágio pulado é informação, não silêncio).
    """
    array = _campo_solido()
    array[16, 16, :3] = (200, 10, 10)
    processador = PixelPostProcessor(transforms=[ConservativeCleaner()])

    desligado = processador.process(
        _imagem(array), _spec(width=32, height=32, cleanup={"mode": "off"})
    )
    ligado = processador.process(
        _imagem(array), _spec(width=32, height=32, cleanup={"mode": "conservative"})
    )

    passo = desligado.report.steps[0]
    assert passo.name == "pixel.conservative_cleaner"
    assert passo.applied is False
    assert "off" in (passo.skipped_reason or "")
    assert tuple(to_array(desligado.image)[16, 16, :3]) == (200, 10, 10)
    assert ligado.report.steps[0].applied is True
    assert tuple(to_array(ligado.image)[16, 16, :3]) == _FUNDO


def test_cleanup_never_introduces_a_new_color():
    """A regra de ouro do plano Pixel §106: a limpeza só copia, jamais inventa.

    O estágio roda **depois** do quantizador, então uma cor nova estouraria o
    limite de paleta já validado e faria o check PX-COLOR-001 reprovar um
    asset que estava correto. Como a correção copia a cor de um vizinho, o
    conjunto de cores só pode encolher.

    O sprite cobre as três decisões ao mesmo tempo (corrigir, proteger o
    contorno e preservar por ambiguidade), para que a propriedade seja
    verificada em uma imagem onde o estágio de fato agiu.
    """
    array = _sprite_com_ruido()
    antes = set(color_counts(array))
    contexto = _contexto(_spec())

    resultado = ConservativeCleaner().apply(_imagem(array), contexto)

    depois = _cores_opacas(resultado)
    assert contexto.details["corrected"] >= 1, "sem correção a propriedade é trivial"
    assert contexto.details["protected_outline"] >= 1
    assert contexto.details["ambiguous"] >= 1
    assert depois <= antes, f"cores inventadas pela limpeza: {sorted(depois - antes)}"
    assert len(depois) < len(antes), "as cores raras corrigidas deviam ter saído"
