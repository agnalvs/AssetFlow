"""ConservativeCleaner — detectar não é remover (plano Pixel §29, §30, §31 e §106).

Este é o estágio onde a tentação de "melhorar sozinho" faz o maior estrago. Um
pixel isolado pode ser um olho, um brilho especular ou a ponta de uma espada:
em Pixel Art profissional ele quase sempre é intencional (plano Pixel §51). Por
isso a regra do plano §31 vale palavra por palavra aqui — **detectar não
significa remover**, e a limpeza agressiva fica de fora do enum de
:class:`~assetflow.pixel.contracts.output_spec.CleanupSpec` justamente para que
ninguém a ligue "só para subir a nota" (plano Pixel §106).

O único caso corrigido é o de altíssima confiança do §30: um pixel interior,
opaco, cercado pelos 8 vizinhos opacos e todos da **mesma** cor ``D`` diferente
da sua, cuja cor ``C`` é rara o bastante para não ser detalhe deliberado, e que
não pertence ao contorno. Isso é ruído de quantização, não desenho.

Tudo o mais — vizinhos discordando, cor não rara, pixel no contorno — vira
**aviso** e nada além disso. O relatório fica sabendo; a imagem, não.

Duas propriedades que sustentam o resto do módulo:

*A decisão sai do array original em uma única passagem vetorizada.* Corrigir em
cascata (ler o pixel já corrigido ao decidir o vizinho) propagaria uma correção
por regiões inteiras e faria o resultado depender da ordem de varredura.

*A limpeza nunca inventa cor.* Ela só copia a cor de um vizinho opaco, que por
construção já está na paleta fechada pelo ``PaletteQuantizer``. É o que permite
rodá-la depois da quantização sem risco de estourar o limite de cores.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from ...imaging import (
    RGBA,
    color_counts,
    opaque_mask,
    to_array,
    to_image,
    unique_colors,
)
from .base import PixelContext, PixelTransform

__all__ = ["ConservativeCleaner"]

#: Vizinhança de 8 usada pelo plano Pixel §30, em ``(dy, dx)``.
_OFFSETS = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 1),
    (1, -1), (1, 0), (1, 1),
)

#: Quantas posições acompanham um aviso agregado.
_SAMPLE_LIMIT = 3


@dataclass(frozen=True, slots=True)
class _Decision:
    """O veredito por pixel, em máscaras do tamanho da imagem.

    ``candidate`` é o conjunto detectado (pixels opacos sem nenhum vizinho da
    própria cor); as outras três o particionam entre corrigir, preservar por
    contorno e preservar por ambiguidade.
    """

    candidate: np.ndarray
    corrected: np.ndarray
    protected: np.ndarray
    ambiguous: np.ndarray
    #: Cor ``D`` a copiar em cada posição corrigida.
    target: np.ndarray


class ConservativeCleaner(PixelTransform):
    """Corrige só o ruído inequívoco e reporta o resto."""

    name = "pixel.conservative_cleaner"
    version = "1.0.0"

    def applies_to(self, context: PixelContext) -> bool:
        return context.spec.cleanup.mode != "off"

    def skip_reason(self, context: PixelContext) -> str:
        return "limpeza desligada pelo profile (cleanup.mode = 'off')"

    def apply(self, image: Image.Image, context: PixelContext) -> Image.Image:
        cleanup = context.spec.cleanup
        array = to_array(image)
        opaque = opaque_mask(array)
        foreground = int(opaque.sum())

        if foreground == 0:
            context.warn("limpeza: imagem totalmente transparente, nada a inspecionar")
            self._record(context, candidates=0, corrected=0, ambiguous=0, protected=0)
            return image

        decision = _decide(
            array,
            opaque,
            foreground=foreground,
            rare_ratio=cleanup.max_rare_color_ratio,
            protect_outline=cleanup.protect_outline,
        )

        corrected = int(decision.corrected.sum())
        protected = int(decision.protected.sum())
        ambiguous = int(decision.ambiguous.sum())

        # Um aviso por categoria, e não um por pixel: um sprite pode ter dezenas
        # de pixels isolados legítimos, e inundar o ProcessingReport com eles
        # esconderia os avisos que realmente pedem atenção.
        if protected:
            context.warn(
                f"limpeza: {protected} pixel(s) isolado(s) no contorno preservado(s)"
                f"{_sample(decision.protected)}"
            )
        if ambiguous:
            context.warn(
                f"limpeza: {ambiguous} pixel(s) isolado(s) preservado(s) por ambiguidade "
                f"(vizinhos discordantes, cor não rara ou vizinhança incompleta)"
                f"{_sample(decision.ambiguous)}"
            )

        self._record(
            context,
            candidates=int(decision.candidate.sum()),
            corrected=corrected,
            ambiguous=ambiguous,
            protected=protected,
        )

        if not corrected:
            return image

        result = array.copy()
        result[:, :, :3] = np.where(
            decision.corrected[:, :, None], decision.target, array[:, :, :3]
        )

        if "palette" in context.shared:
            # A correção só copia cor de vizinho, então a paleta jamais cresce —
            # mas ela pode encolher, quando a última ocorrência de uma cor rara
            # era justamente o ruído corrigido. O relatório não pode continuar
            # anunciando uma cor que saiu do asset.
            counts = color_counts(result)
            context.shared["palette"] = tuple(counts)
            context.shared["palette_counts"] = counts

        return to_image(result)

    # ------------------------------------------------------------------
    def _record(
        self,
        context: PixelContext,
        *,
        candidates: int,
        corrected: int,
        ambiguous: int,
        protected: int,
    ) -> None:
        context.detail("mode", context.spec.cleanup.mode)
        context.detail("candidates", candidates)
        context.detail("corrected", corrected)
        context.detail("ambiguous", ambiguous)
        context.detail("protected_outline", protected)
        context.detail("rare_color_ratio", context.spec.cleanup.max_rare_color_ratio)


# ---------------------------------------------------------------------------
# A passagem única (plano Pixel §30)
# ---------------------------------------------------------------------------
def _decide(
    array: RGBA,
    opaque: np.ndarray,
    *,
    foreground: int,
    rare_ratio: float,
    protect_outline: bool,
) -> _Decision:
    """Avalia as quatro condições do §30 para todos os pixels de uma vez."""
    height, width = opaque.shape
    rgb = array[:, :, :3]

    # A moldura de 1 pixel resolve dois problemas ao mesmo tempo: dá vizinho a
    # quem está na borda e, por ser marcada como não opaca, faz a borda da
    # imagem contar como contorno do sprite (condição 4).
    padded_rgb = np.pad(rgb, ((1, 1), (1, 1), (0, 0)))
    padded_opaque = np.pad(opaque, 1, constant_values=False)
    neighbour_rgb = [
        padded_rgb[1 + dy : 1 + dy + height, 1 + dx : 1 + dx + width] for dy, dx in _OFFSETS
    ]
    neighbour_opaque = [
        padded_opaque[1 + dy : 1 + dy + height, 1 + dx : 1 + dx + width]
        for dy, dx in _OFFSETS
    ]

    # Condição 1: os 8 vizinhos existem dentro da imagem.
    interior = np.zeros((height, width), dtype=bool)
    interior[1:-1, 1:-1] = True

    # Condição 2: todos opacos e todos com a mesma cor D, diferente de C.
    all_opaque = np.logical_and.reduce(neighbour_opaque)
    target = neighbour_rgb[0]
    agree = np.logical_and.reduce(
        [np.all(item == target, axis=2) for item in neighbour_rgb[1:]]
    )
    differs = ~np.all(target == rgb, axis=2)

    # Detecção (§29): pixel opaco sem nenhum vizinho opaco da própria cor.
    matched = np.logical_or.reduce(
        [
            np.all(item == rgb, axis=2) & flag
            for item, flag in zip(neighbour_rgb, neighbour_opaque)
        ]
    )
    candidate = opaque & ~matched

    # Condição 3: a cor do pixel é rara no sprite.
    rare = _color_ratio(array, foreground) <= rare_ratio

    # Condição 4: contorno = pixel opaco vizinho de transparente ou da borda.
    outline = opaque & ~all_opaque

    corrected = candidate & interior & all_opaque & agree & differs & rare
    if protect_outline:
        # Redundante hoje — `all_opaque` já exclui todo pixel de contorno —, mas
        # escrita porque é uma condição do plano por direito próprio: se um dia
        # a condição 2 afrouxar, a proteção do contorno continua valendo.
        corrected = corrected & ~outline
        protected = candidate & outline
    else:
        protected = np.zeros((height, width), dtype=bool)

    return _Decision(
        candidate=candidate,
        corrected=corrected,
        protected=protected,
        ambiguous=candidate & ~corrected & ~protected,
        target=target,
    )


def _color_ratio(array: RGBA, foreground: int) -> np.ndarray:
    """Frequência da cor de cada pixel entre os pixels opacos (plano Pixel §30).

    A busca binária substitui um laço por cor: ``unique_colors`` já devolve as
    cores em ordem lexicográfica de RGB, e empacotá-las em um inteiro
    ``r<<16 | g<<8 | b`` preserva essa ordem, então ``searchsorted`` acha a
    contagem de cada pixel de uma vez só.
    """
    colors, counts = unique_colors(array)
    keys = _pack(colors)
    pixel_keys = _pack(array[:, :, :3].reshape(-1, 3)).reshape(array.shape[:2])

    position = np.clip(np.searchsorted(keys, pixel_keys), 0, keys.size - 1)
    # Cor presente só entre pixels transparentes não está em `keys`; para ela a
    # frequência é 0, o que a torna "rara" — inofensivo, já que só pixels opacos
    # chegam a ser candidatos.
    found = keys[position] == pixel_keys
    return np.where(found, counts[position], 0) / float(foreground)


def _pack(colors: np.ndarray) -> np.ndarray:
    """``(n, 3)`` RGB -> ``(n,)`` inteiros, preservando a ordem lexicográfica."""
    values = colors.astype(np.int64)
    return (values[:, 0] << 16) | (values[:, 1] << 8) | values[:, 2]


def _sample(mask: np.ndarray) -> str:
    """Trecho ``" — em (x, y), (x, y)…"`` com as primeiras posições da máscara."""
    positions = np.argwhere(mask)[:_SAMPLE_LIMIT]
    if positions.size == 0:
        return ""
    listed = ", ".join(f"({int(x)}, {int(y)})" for y, x in positions)
    suffix = "…" if int(mask.sum()) > _SAMPLE_LIMIT else ""
    return f" — em {listed}{suffix}"
