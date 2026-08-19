"""PaletteQuantizer — o estágio que fixa o conjunto exato de cores (plano Pixel §25 a §28).

Ele roda depois do ``AlphaNormalizer`` de propósito (plano Pixel §8): a essa
altura o alpha já é binário, então **só os pixels opacos importam**. Um pixel
invisível não pode consumir uma entrada da paleta — seria gastar 1 das 16 cores
de um sprite com algo que ninguém vê.

Os três modos do plano Pixel §11 desembocam em duas estratégias:

``max_colors`` (AUTO)
    A paleta é derivada da própria imagem por median cut. A tira de 1 linha
    montada só com os pixels opacos existe por causa da regra acima: quantizar
    a imagem inteira faria o median cut enxergar o fundo transparente como
    massa de cor e reservar caixas de paleta para pixels invisíveis.

``locked`` / ``project_palette`` (§27)
    A paleta chega pronta e nenhuma outra cor pode sobreviver — cada pixel vai
    para a cor mais próxima via :func:`map_to_palette`. É o que mantém
    personagem, inimigo e tile da mesma família visual.

Dithering é **escolha artística, nunca correção técnica** (plano Pixel §26).
Por isso o padrão é desligado: na resolução lógica de um sprite, a difusão de
erro espalha ruído exatamente onde o artista de Pixel Art desenharia a
transição à mão. Ele só entra quando o profile pede.

E, por fim, a garantia dura que impede o check ``PX-COLOR-001`` de reprovar por
detalhe de implementação: ao terminar, o número de cores únicas entre os pixels
opacos **é** ``<= spec.max_colors``. Se o dithering ou uma paleta travada maior
que o limite deixarem excedente, as cores menos usadas são fundidas na vizinha
mais próxima até caber.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from ...imaging import (
    RGBA,
    color_counts,
    color_distance,
    hex_to_rgb,
    map_to_palette,
    opaque_mask,
    to_array,
    to_image,
    unique_colors,
)
from .base import PixelContext, PixelTransform

__all__ = ["PaletteQuantizer"]

#: Quantas cores o modo AUTO deriva quando o profile não informou um limite.
_AUTO_FALLBACK_COLORS = 16


class PaletteQuantizer(PixelTransform):
    """Reduz a imagem ao conjunto exato de cores que o profile permite."""

    name = "pixel.palette_quantizer"
    version = "1.0.0"

    def apply(self, image: Image.Image, context: PixelContext) -> Image.Image:
        spec = context.spec
        array = to_array(image)
        mask = opaque_mask(array)
        limit = spec.max_colors

        if not mask.any():
            # Sem nenhum pixel opaco não existe paleta a derivar: o median cut
            # receberia uma tira de largura zero e a imagem não tem cor visível
            # que possa ser preservada ou perdida.
            context.warn("paleta: imagem totalmente transparente, nenhuma cor a quantizar")
            context.shared["palette"] = ()
            context.shared["palette_counts"] = {}
            self._record(
                context,
                mode=spec.palette.mode,
                requested=limit,
                derived=0,
                final=0,
                merged=0,
                palette=(),
            )
            return image

        palette, mode = self._resolve_palette(array, mask, context)
        derived = int(palette.shape[0])

        if spec.dithering.enabled and derived:
            mapped = _dither_to_palette(array, palette)
        else:
            mapped = map_to_palette(array, palette)

        merged = 0
        if limit is not None:
            mapped, merged = _enforce_limit(mapped, limit)
            if merged:
                context.warn(
                    f"paleta: {merged} cor(es) fundida(s) na vizinha mais próxima "
                    f"para caber no limite de {limit}"
                )

        # `map_to_palette` pinta TODOS os pixels, inclusive os invisíveis: sem
        # esta linha o fundo transparente sairia carregando a cor de paleta
        # mais próxima do preto — exatamente a "cor fantasma" que o
        # AlphaNormalizer tinha acabado de remover, e que reaparece assim que
        # alguém borra, amplia ou baixa o limiar de alpha em um editor.
        # Rezerar aqui, e não antes, é o que mantém o invariante válido no
        # arquivo entregue: nenhum estágio posterior repinta pixel invisível.
        mapped[~opaque_mask(mapped), :3] = 0

        counts = color_counts(mapped)
        final_palette = tuple(counts)
        context.shared["palette"] = final_palette
        context.shared["palette_counts"] = counts

        self._record(
            context,
            mode=mode,
            requested=limit,
            derived=derived,
            final=len(final_palette),
            merged=merged,
            palette=final_palette,
        )
        return to_image(mapped)

    # ------------------------------------------------------------------
    def _resolve_palette(
        self, array: RGBA, mask: np.ndarray, context: PixelContext
    ) -> tuple[np.ndarray, str]:
        """Devolve ``(paleta, modo efetivamente aplicado)``.

        O modo devolvido pode diferir do pedido, e é por isso que ele entra no
        relatório: uma paleta PROJECT que chega aqui sem cores é uma paleta que
        o registry não resolveu. Cair para AUTO produz uma imagem em vez de uma
        exceção — mas isso **não** vira aprovação: quem denuncia a paleta
        ausente é o check PX-PALETTE-001, que reprova o asset com o
        `palette_id` no relatório. A configuração quebrada aparece onde alguém
        vai ler, e não em um traceback no meio de um job.
        """
        palette_spec = context.spec.palette
        wanted = palette_spec.max_colors or _AUTO_FALLBACK_COLORS

        if palette_spec.is_locked:
            colors = _palette_from_hex(palette_spec.colors)
            if colors.size:
                return colors, palette_spec.mode
            context.warn(
                f"paleta: '{palette_spec.palette_id}' não foi resolvida para cores; "
                f"derivando {wanted} cores da própria imagem"
            )
        return _derive_palette(array, mask, wanted), "max_colors"

    def _record(
        self,
        context: PixelContext,
        *,
        mode: str,
        requested: int | None,
        derived: int,
        final: int,
        merged: int,
        palette: tuple[str, ...],
    ) -> None:
        context.detail("mode", mode)
        context.detail("requested_colors", requested)
        context.detail("derived_colors", derived)
        context.detail("final_colors", final)
        context.detail("dither", context.spec.dithering.enabled)
        context.detail("merged_colors", merged)
        context.detail("palette", palette)


# ---------------------------------------------------------------------------
# Derivação da paleta
# ---------------------------------------------------------------------------
def _derive_palette(array: RGBA, mask: np.ndarray, wanted: int) -> np.ndarray:
    """Median cut sobre os pixels opacos (plano Pixel §25 e §28)."""
    colors, _counts = unique_colors(array)
    if colors.shape[0] <= wanted:
        # A imagem já cabe no limite. Passar pelo median cut aqui só deslocaria
        # cores que já estão certas — e cor deslocada em Pixel Art é defeito.
        return colors

    strip = np.ascontiguousarray(array[mask][:, :3]).reshape(1, -1, 3)
    quantized = Image.fromarray(strip, mode="RGB").quantize(
        colors=min(256, max(1, wanted)),
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    return _palette_of(quantized)


def _palette_of(image: Image.Image) -> np.ndarray:
    """Extrai as entradas de paleta realmente usadas por uma imagem ``P``.

    Ler a tabela inteira devolveria também as entradas que o Pillow deixa
    zeradas no fim — e cada uma delas contaria como uma cor da paleta.
    """
    flat = image.getpalette() or []
    entries = [
        tuple(flat[index * 3 : index * 3 + 3])
        for index in (int(value) for value in np.unique(np.asarray(image)))
        if (index + 1) * 3 <= len(flat)
    ]
    if not entries:
        return np.empty((0, 3), dtype=np.uint8)
    return _unique_rows(np.array(entries, dtype=np.uint8))


def _palette_from_hex(colors: tuple[str, ...]) -> np.ndarray:
    if not colors:
        return np.empty((0, 3), dtype=np.uint8)
    return _unique_rows(np.array([hex_to_rgb(value) for value in colors], dtype=np.uint8))


def _unique_rows(colors: np.ndarray) -> np.ndarray:
    """Remove cores repetidas preservando a ordem de chegada.

    Preservar a ordem (em vez de aceitar a ordenação de ``np.unique``) mantém a
    paleta do profile legível no relatório e não muda o resultado: o mapeamento
    escolhe por distância, nunca por posição.
    """
    _values, index = np.unique(colors, axis=0, return_index=True)
    return colors[np.sort(index)]


# ---------------------------------------------------------------------------
# Dithering (plano Pixel §26)
# ---------------------------------------------------------------------------
def _dither_to_palette(array: RGBA, palette: np.ndarray) -> RGBA:
    """Floyd-Steinberg contra a paleta já decidida, com o alpha original de volta.

    O Pillow difunde erro sobre RGB e não conhece o canal alpha, então ele é
    reaplicado depois: dithering pode escolher cores, nunca mudar quem é
    visível. O ``map_to_palette`` final custa quase nada e fecha a porta para
    uma entrada de preenchimento da tabela de 256 virar cor do asset.
    """
    source = Image.fromarray(np.ascontiguousarray(array[:, :, :3]), mode="RGB")
    quantized = source.quantize(
        palette=_palette_image(palette), dither=Image.Dither.FLOYDSTEINBERG
    )
    result = to_array(quantized.convert("RGBA"))
    result[:, :, 3] = array[:, :, 3]
    return map_to_palette(result, palette)


def _palette_image(palette: np.ndarray) -> Image.Image:
    """Imagem ``P`` portadora da paleta exigida pelo ``Image.quantize``.

    As 256 entradas são obrigatórias, e completar a sobra com preto — o atalho
    óbvio — entregaria ao difusor de erro um preto que não está na paleta.
    Repetir a última cor mantém a tabela inteira dentro do conjunto permitido.
    """
    flat: list[int] = [int(value) for value in palette[:256].reshape(-1)]
    tail = flat[-3:]
    while len(flat) < 768:
        flat.extend(tail)

    image = Image.new("P", (1, 1))
    image.putpalette(flat)
    return image


# ---------------------------------------------------------------------------
# Garantia dura do limite (plano Pixel §28 e check PX-COLOR-001)
# ---------------------------------------------------------------------------
def _enforce_limit(array: RGBA, limit: int) -> tuple[RGBA, int]:
    """Funde cores até caber em ``limit``. Devolve ``(imagem, número de fusões)``.

    A vítima é sempre a cor **menos usada** entre os pixels opacos e o destino é
    a cor restante mais próxima: perde-se o detalhe menos presente, nunca a
    massa do sprite. Os empates saem determinísticos de graça — ``unique_colors``
    devolve as cores em ordem lexicográfica de RGB, que é a mesma ordem
    alfabética do hexadecimal, e ``argmin`` fica com o primeiro índice.
    """
    merged = 0
    result = array
    while True:
        colors, counts = unique_colors(result)
        if colors.shape[0] <= limit:
            return result, merged

        victim = int(np.argmin(counts))
        distances = color_distance(colors[victim : victim + 1], colors)[0]
        distances[victim] = np.iinfo(distances.dtype).max
        target = int(np.argmin(distances))

        if result is array:
            result = array.copy()
        # A substituição alcança também os pixels transparentes. Não é
        # desperdício: o RGB deles é zerado no fim do estágio, e tratá-los
        # aqui evita um caminho separado só para pixel invisível.
        pixels = np.all(result[:, :, :3] == colors[victim].reshape(1, 1, 3), axis=2)
        result[pixels, :3] = colors[target]
        merged += 1
