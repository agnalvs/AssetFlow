"""OutlineAnalyzer — o estado do contorno do sprite (plano Pixel §52).

Contorno aqui é definição geométrica, não estilística: pixel opaco que faz
fronteira (4-conectado) com transparência ou com a borda do canvas. Um sprite
saudável tem contorno contínuo — poucos componentes conexos cobrindo muitos
pixels. Quando a redução esfarela a silhueta, o mesmo contorno vira dezenas de
pedaços soltos, e é isso que ``outline_fragmentation`` mede.

Esta é a **primeira versão** e ela só detecta. O plano §52 prevê reconstruir
ou reforçar contorno no futuro; fazer isso agora seria desenhar por cima do
trabalho do artista com base em uma heurística de fragmentação — e, pior,
dentro do Validator, que por contrato não altera um único pixel (§37, §104).
"""

from __future__ import annotations

import numpy as np

from ...imaging import color_counts, connected_components
from .base import AnalysisResult, QualityAnalyzer, ValidationContext

__all__ = ["OutlineAnalyzer"]

#: Vizinhança usada para decidir se o pixel é de fronteira.
_NEIGHBOURS_4 = ((-1, 0), (1, 0), (0, -1), (0, 1))

#: Quantas cores predominantes do contorno entram no relatório.
_MAX_OUTLINE_COLORS = 5

#: Acima disto o contorno é considerado esfarelado. Experimental (§60).
_WARNING_FRAGMENTATION = 0.15


class OutlineAnalyzer(QualityAnalyzer):
    """Mede tamanho, cores e continuidade do contorno."""

    name = "outline"

    def analyze(self, context: ValidationContext) -> AnalysisResult:
        outline = _outline_mask(context.mask)
        pixels = int(outline.sum())

        if pixels == 0:
            return AnalysisResult(
                metrics={
                    "outline_pixels": 0,
                    "outline_colors": (),
                    "outline_fragmentation": 0.0,
                }
            )

        # 8-conectado de propósito: um contorno diagonal avança um pixel na
        # diagonal a cada passo. Com 4-conectividade uma silhueta perfeita
        # apareceria quebrada em um componente por pixel.
        _labels, components = connected_components(outline, connectivity=8)
        fragmentation = round(min(1.0, components / pixels), 6)

        result = AnalysisResult(
            metrics={
                "outline_pixels": pixels,
                "outline_colors": _outline_colors(context.array, outline),
                "outline_fragmentation": fragmentation,
            }
        )
        if fragmentation > _WARNING_FRAGMENTATION:
            return result.with_warning(
                "PX-WARN-OUTLINE-FRAGMENTED",
                f"o contorno está em {components} pedaços para {pixels} "
                f"pixels (fragmentação {fragmentation:.2f}) — a silhueta pode "
                "ter se desfeito na redução",
                count=components,
                fragmentation=fragmentation,
                outline_pixels=pixels,
                threshold=_WARNING_FRAGMENTATION,
            )
        return result


def _outline_mask(mask: np.ndarray) -> np.ndarray:
    """Pixels opacos com pelo menos um vizinho 4-conectado transparente.

    O padding entra como transparente, então a borda do canvas conta como
    fronteira: um sprite que sangra para fora tem contorno ali, mesmo sem
    nenhum pixel vazio ao lado.
    """
    if not mask.any():
        return np.zeros(mask.shape, dtype=bool)

    height, width = mask.shape
    padded = np.zeros((height + 2, width + 2), dtype=bool)
    padded[1 : height + 1, 1 : width + 1] = mask

    exposed = np.zeros((height, width), dtype=bool)
    for row, col in _NEIGHBOURS_4:
        exposed |= ~padded[1 + row : 1 + row + height, 1 + col : 1 + col + width]
    return mask & exposed


def _outline_colors(array: np.ndarray, outline: np.ndarray) -> tuple[str, ...]:
    """As cores predominantes do contorno, da mais frequente para a menos.

    Zerar o alpha fora do contorno reaproveita ``color_counts`` — que já
    ignora transparência e já ordena por frequência — em vez de repetir a
    contagem à mão.
    """
    isolated = array.copy()
    isolated[~outline, 3] = 0
    return tuple(color_counts(isolated))[:_MAX_OUTLINE_COLORS]
