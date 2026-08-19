"""Golden tests do módulo Pixel (plano Pixel §90 e §91).

Um golden test compara a saída do pipeline com um resultado conhecido. Ele só
tem sentido se duas coisas forem verdade ao mesmo tempo:

1. a **entrada** é conhecida e reprodutível — por isso as fixtures são
   construídas por código em ``tests/fixtures/pixel/``, e não arquivos PNG
   versionados (o módulo explica o porquê);
2. a **saída** é determinística — por isso o último teste deste arquivo, o de
   determinismo, é o alicerce dos outros dois: sem ele, "comparar com o
   resultado esperado" seria comparar com o resultado de ontem.

Os três casos do plano:

``§91 — a "falsa Pixel Art"``
    A imagem que um gerador devolve quando se pede pixel art: grande, com
    milhares de cores, alpha suave e bordas interpoladas. Depois do módulo
    Pixel ela precisa ser um asset de verdade.
``§90 — o sprite que já era Pixel Art``
    Ampliado com nearest, o pipeline com ``block_vote`` tem de recuperar a
    grade lógica original.
``§90 — determinismo``
    A mesma entrada produz o mesmo PNG, byte a byte.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from assetflow.bootstrap import AppContainer
from assetflow.pixel import PixelAssetProcessor
from assetflow.pixel.contracts import PixelOutputSpec
from assetflow.pixel.imaging import (
    alpha_values,
    count_colors,
    decode,
    opaque_mask,
    to_array,
)
from tests.fixtures.pixel import (
    fake_pixel_art,
    pixel_perfect_sprite,
    upscale_nearest,
)

#: Lado da imagem bruta nos dois casos. 512 é múltiplo inteiro de 64 e de 16,
#: que é o que o ``block_vote`` exige do caso (b) (plano Pixel §18).
RENDER_SIZE = 512

#: Fator de ampliação do sprite lógico: 16 × 32 = 512.
SPRITE_SCALE = 32


def _step(outcome, name: str):
    """O relatório de um estágio pelo nome, para não depender da posição."""
    for step in outcome.processing.steps:
        if step.name == name:
            return step
    raise AssertionError(f"o estágio '{name}' não aparece no ProcessingReport")


def _block_vote_spec(max_colors: int) -> PixelOutputSpec:
    """Contrato 16×16 com reconstrução por votação de bloco (plano Pixel §18).

    O spec é montado aqui, e não lido de ``pixel_profiles.yaml``, porque
    ``max_colors`` é a variável do experimento: os dois testes de
    reconstrução diferem **só** no orçamento de paleta, e é essa diferença
    que separa "reconstruiu" de "reconstruiu e quantizou".
    """
    return PixelOutputSpec.model_validate(
        {
            "id": "golden_block_vote",
            "logical_size": {"width": 16, "height": 16},
            "palette": {"mode": "max_colors", "max_colors": max_colors},
            "logical_reduction": {"method": "block_vote", "statistic": "dominant"},
            "preview": {"enabled": True, "scale": 16},
        }
    )


# ---------------------------------------------------------------------------
# (a) A "falsa Pixel Art" do plano Pixel §91
# ---------------------------------------------------------------------------
def test_fake_pixel_art_fixture_really_is_fake():
    """A fixture precisa ter os defeitos do §91, senão o caso (a) não prova nada.

    Este teste protege o **outro** teste: se um dia a construção da fixture
    for simplificada e ela passar a ter 12 cores e alpha binário, o caso (a)
    continuaria verde sem nunca ter exercitado a redução de paleta nem a
    binarização do alpha. Aqui as três características são medidas de forma
    independente da implementação que as produz.
    """
    array = to_array(fake_pixel_art(RENDER_SIZE))

    assert array.shape[:2] == (RENDER_SIZE, RENDER_SIZE)
    assert count_colors(array) >= 256, "o §91 fala de uma imagem com 256+ cores"

    partial_alpha = [value for value in alpha_values(array) if 0 < value < 255]
    assert len(partial_alpha) > 32, (
        "sem alpha parcial não existe a franja interpolada que o §91 descreve"
    )


def test_fake_pixel_art_becomes_a_real_pixel_asset(container: AppContainer):
    """Plano Pixel §91: a imagem grande e borrada vira um asset 64×64 exato.

    É o caso de aceitação do módulo inteiro. O que ele fixa não é um valor
    bonito, é a diferença entre *parecer* Pixel Art e *ser*: resolução lógica
    real, orçamento de paleta respeitado e alpha sem meio-termo — as três
    regras de ouro do plano Pixel §3, §11 e §21, medidas no arquivo entregue.

    Os números vêm do profile ``pixel_character_64_strict``, não de constantes
    do teste: quem decide 64 e 16 é ``config/pixel_profiles.yaml`` (§64).
    """
    spec = container.pixel_profiles.get("pixel_character_64_strict")
    outcome = PixelAssetProcessor().run(fake_pixel_art(RENDER_SIZE), spec)
    array = to_array(outcome.logical)

    assert outcome.logical.size == spec.target_size == (64, 64)
    assert count_colors(array) <= spec.max_colors
    assert set(alpha_values(array)) <= {0, 255}

    # O asset entregue é o PNG lógico, não o preview ampliado (§35 e §103).
    assert decode(outcome.artifacts["logical.png"]).size == (64, 64)
    assert outcome.pixel_exact is True, outcome.decision.reasons


# ---------------------------------------------------------------------------
# (b) O sprite que já era Pixel Art (plano Pixel §18 e §90)
# ---------------------------------------------------------------------------
def test_block_vote_reconstructs_the_original_sprite():
    """Um sprite 16×16 ampliado 32× volta a ser exatamente ele mesmo.

    É a propriedade que justifica a existência do ``block_vote`` (plano Pixel
    §18): quando a origem já vem em blocos, cada pixel lógico tem um bloco
    correspondente e a decisão pode ser exata, sem média e sem chute.

    Com orçamento de paleta folgado (16 cores para 10 cores de sprite) o
    ``PaletteQuantizer`` não precisa mexer em nada, e a comparação pode ser
    **pixel a pixel**: o canal alpha inteiro e o RGB de toda a região opaca.

    O RGB dos pixels **transparentes** fica de fora da comparação de
    propósito, e não por tolerância: um pixel invisível não é cor do sprite —
    é o mesmo critério que ``color_counts`` usa ao medir a paleta do asset
    (plano Pixel §28). O que ele carrega no RGB não é observável no jogo.
    """
    original = to_array(pixel_perfect_sprite())
    source = upscale_nearest(pixel_perfect_sprite(), SPRITE_SCALE)
    assert source.size == (RENDER_SIZE, RENDER_SIZE)

    outcome = PixelAssetProcessor().run(source, _block_vote_spec(16), export=False)
    result = to_array(outcome.logical)

    # A votação por bloco tem de ter acontecido de fato: o reducer cai para
    # média de área quando a origem não é múltipla inteira do alvo, e nesse
    # caminho o teste estaria medindo outro algoritmo.
    details = _step(outcome, "pixel.logical_reducer").details
    assert details["resample"] == "block_vote"
    assert details["fallback"] is None
    assert tuple(details["block_size"]) == (SPRITE_SCALE, SPRITE_SCALE)

    assert result.shape == original.shape
    assert np.array_equal(result[:, :, 3], original[:, :, 3]), (
        "a silhueta precisa voltar idêntica: nenhum pixel a mais, nenhum a menos"
    )
    opaque = opaque_mask(original)
    assert np.array_equal(result[opaque][:, :3], original[opaque][:, :3]), (
        "com paleta folgada nenhuma cor do sprite pode ter se deslocado"
    )


def test_palette_quantization_is_the_only_thing_that_moves_a_pixel():
    """Com paleta apertada a silhueta continua exata; só as cores se fundem.

    Este é o teste que **documenta por que a igualdade não pode ser byte a
    byte quando há quantização**. Com orçamento de 8 cores para um sprite de
    10, duas cores precisam desaparecer: o median cut e a fusão de cores do
    ``PaletteQuantizer`` escolhem representantes que não são necessariamente
    nenhuma das cores originais (plano Pixel §25 e §28). Um ``assert`` de
    igualdade byte a byte aqui não estaria protegendo a reconstrução — estaria
    proibindo a quantização de fazer o trabalho dela.

    O que continua exigível, e é o que o teste fixa:

    * a **geometria** não muda — a máscara opaca é idêntica à do gabarito;
    * o remapeamento é **por cor, não por posição** — dois pixels que tinham a
      mesma cor continuam com a mesma cor. Se a redução tivesse borrado ou
      interpolado, pixels irmãos teriam terminado em cores diferentes;
    * o orçamento é respeitado e realmente apertou: sobram 8 cores, e pelo
      menos uma delas não existia no original.
    """
    original = to_array(pixel_perfect_sprite())
    source = upscale_nearest(pixel_perfect_sprite(), SPRITE_SCALE)

    outcome = PixelAssetProcessor().run(source, _block_vote_spec(8), export=False)
    result = to_array(outcome.logical)
    opaque = opaque_mask(original)

    assert np.array_equal(opaque_mask(result), opaque), "a silhueta não pode mudar"
    assert count_colors(result) == 8, "o orçamento de paleta precisa ter sido usado"

    # {cor original -> conjunto de cores finais}: uma função, não uma relação.
    mapping: dict[tuple[int, ...], set[tuple[int, ...]]] = {}
    for before, after in zip(original[opaque][:, :3], result[opaque][:, :3]):
        mapping.setdefault(tuple(int(v) for v in before), set()).add(
            tuple(int(v) for v in after)
        )

    assert len(mapping) == 10, "o gabarito precisa ter mais cores que o orçamento"
    espalhadas = {origem: destinos for origem, destinos in mapping.items() if len(destinos) > 1}
    assert not espalhadas, (
        "uma cor original terminou em mais de uma cor final — sinal de "
        f"interpolação espacial, que o plano Pixel §20 proíbe: {espalhadas}"
    )

    deslocadas = {
        origem for origem, destinos in mapping.items() if next(iter(destinos)) != origem
    }
    assert deslocadas, (
        "nenhuma cor se moveu: o orçamento não apertou e o teste não estaria "
        "exercitando a quantização que ele existe para descrever"
    )


# ---------------------------------------------------------------------------
# (c) Determinismo — o alicerce de todo golden test (plano Pixel §90)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("profile_id", ["pixel_character_64_strict", "pixel_tileset_16"])
def test_processing_twice_produces_the_same_png(
    container: AppContainer, profile_id: str
):
    """A mesma entrada, duas execuções: PNG idêntico byte a byte.

    Sem esta propriedade os dois testes acima não seriam golden tests — seriam
    apostas. Ela também é o que permite ao AssetFlow reprocessar um asset e
    saber que nada mudou sem ter de comparar imagem por imagem.

    Cada execução parte de uma fixture recém-construída e de um
    ``PixelAssetProcessor`` novo: se sobrasse estado entre as passagens
    (paleta em cache, contexto reaproveitado), a igualdade viria do estado e
    não do algoritmo.

    ``processing.json`` e ``validation.json`` ficam fora da comparação porque
    carregam duração medida em milissegundos (plano Pixel §93) — dois
    relatórios idênticos em conteúdo têm timings diferentes por construção.
    """
    spec = container.pixel_profiles.get(profile_id)

    first = PixelAssetProcessor().run(fake_pixel_art(RENDER_SIZE), spec)
    second = PixelAssetProcessor().run(fake_pixel_art(RENDER_SIZE), spec)

    assert first.artifacts["logical.png"] == second.artifacts["logical.png"]
    assert first.artifacts["preview.png"] == second.artifacts["preview.png"]
    assert first.artifacts["palette.json"] == second.artifacts["palette.json"]

    # O veredito também precisa ser estável: um score que oscila tornaria a
    # política de aceitação (§60) não reproduzível.
    assert first.validation.pixel_exact == second.validation.pixel_exact
    assert first.validation.quality.score == second.validation.quality.score
    assert first.decision.status == second.decision.status


def test_logical_png_survives_a_disk_round_trip(container: AppContainer, tmp_path):
    """Plano Pixel §33: o asset é PNG lossless — gravar e reler não muda um pixel.

    O golden test compara bytes de arquivo, então "o arquivo representa
    exatamente os pixels do asset" é premissa, não detalhe. Trocar o exporter
    por um formato com perda (JPEG, WebP lossy) mataria a paleta e o alpha
    binário de uma vez, e é exatamente isso que este teste impede.
    """
    spec = container.pixel_profiles.get("pixel_character_64_strict")
    outcome = PixelAssetProcessor().run(fake_pixel_art(RENDER_SIZE), spec)

    path = tmp_path / "logical.png"
    path.write_bytes(outcome.artifacts["logical.png"])
    with Image.open(path) as reopened:
        recovered = to_array(reopened)

    assert np.array_equal(recovered, to_array(outcome.logical))
    assert set(alpha_values(recovered)) <= {0, 255}
    assert count_colors(recovered) <= spec.max_colors
