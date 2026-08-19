"""ColorRedundancyAnalyzer — cores quase iguais na mesma paleta (plano §55).

Quantizador não tem olho: ele minimiza erro numérico e por isso adora gastar
duas entradas de paleta em ``#3a4f6b`` e ``#3b506c``. Na tela de 64×64 as duas
são a mesma cor, e o resultado é uma paleta de 16 que na prática tem 10.

O critério é distância euclidiana no espaço RGB — grosseiro do ponto de vista
perceptual, mas suficiente para o que se procura aqui e, principalmente,
barato e determinístico. Nenhum par é fundido automaticamente: mesclar cores é
alterar a imagem, e alterar a imagem é do outro lado da fronteira do plano
Pixel §37 e §104.
"""

from __future__ import annotations

import numpy as np

from ...imaging import color_distance, rgb_to_hex, unique_colors
from .base import AnalysisResult, QualityAnalyzer, ValidationContext

__all__ = ["ColorRedundancyAnalyzer"]

#: Abaixo desta distância euclidiana no RGB, duas cores são consideradas
#: indistinguíveis. Experimental (plano Pixel §60).
_REDUNDANT_DISTANCE = 12

#: ``color_distance`` devolve o **quadrado** da distância — comparar ao
#: quadrado evita a raiz e o erro de ponto flutuante que viria com ela.
_REDUNDANT_DISTANCE_SQ = _REDUNDANT_DISTANCE * _REDUNDANT_DISTANCE


class ColorRedundancyAnalyzer(QualityAnalyzer):
    """Lista os pares de cores próximos demais para se distinguirem."""

    name = "color_redundancy"

    def analyze(self, context: ValidationContext) -> AnalysisResult:
        colors, _counts = unique_colors(context.array)
        pairs = _redundant_pairs(colors)

        result = AnalysisResult(metrics={"redundant_color_pairs": pairs})
        if pairs:
            listed = ", ".join(f"{first}~{second}" for first, second in pairs)
            return result.with_warning(
                "PX-WARN-COLOR-REDUNDANCY",
                f"{len(pairs)} par(es) de cores quase indistinguíveis "
                f"({listed}) — cada par desperdiça uma entrada da paleta",
                count=len(pairs),
                pairs=[list(pair) for pair in pairs],
                distance=_REDUNDANT_DISTANCE,
            )
        return result


def _redundant_pairs(colors: np.ndarray) -> tuple[tuple[str, str], ...]:
    """Pares ``(hex_a, hex_b)`` mais próximos que o limiar.

    ``unique_colors`` devolve as cores já ordenadas lexicograficamente por
    ``(r, g, b)``, e ``triu_indices`` varre a matriz triangular superior em
    ordem fixa: cada par sai uma única vez, com o menor hexadecimal à
    esquerda, na mesma sequência a cada execução.
    """
    if colors.shape[0] < 2:
        return ()

    distances = color_distance(colors, colors)
    rows, cols = np.triu_indices(colors.shape[0], k=1)
    close = distances[rows, cols] < _REDUNDANT_DISTANCE_SQ
    hexes = [rgb_to_hex(color) for color in colors]
    return tuple(
        (hexes[int(row)], hexes[int(col)])
        for row, col in zip(rows[close], cols[close])
    )
