"""OrphanPixelAnalyzer — pixels sem par de cor na vizinhança (plano Pixel §48).

Um pixel órfão é um pixel opaco cujos **oito** vizinhos têm cor RGB diferente
da sua. Em uma imagem que nasceu de um modelo de difusão, uma nuvem deles é o
sintoma clássico de "imagem grande reduzida na marra": sobra ruído de
gradiente onde deveria haver superfície chapada.

O que este analisador **não** faz é apagar esses pixels. Um pixel isolado pode
ser um olho, um brilho especular ou a ponta de uma espada — o plano Pixel §51
e §106 são explícitos em proibir destruir detalhe intencional para melhorar
uma nota. Aqui ele vira número e aviso; quem eventualmente corrige (com
critérios muito mais duros) é o ConservativeCleaner, no outro lado da fronteira
do plano Pixel §104.
"""

from __future__ import annotations

import numpy as np

from .base import AnalysisResult, QualityAnalyzer, ValidationContext

__all__ = ["OrphanPixelAnalyzer"]

#: Deslocamentos ``(dy, dx)`` dos 8 vizinhos, sem o próprio pixel.
_NEIGHBOURS_8 = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
)

#: Acima disto o relatório ganha um aviso (plano Pixel §48). Valor
#: experimental, calibrado junto com as penalidades do QualityScorer.
_WARNING_RATIO = 0.02

#: Teto de posições registradas. O relatório é lido por gente e serializado em
#: ``validation.json``; um sprite ruidoso pode ter milhares de órfãos e a lista
#: inteira só polui o arquivo — a contagem e o ratio já dizem a gravidade.
_MAX_POSITIONS = 64


class OrphanPixelAnalyzer(QualityAnalyzer):
    """Conta pixels opacos sem nenhum vizinho da mesma cor."""

    name = "orphan_pixels"

    def analyze(self, context: ValidationContext) -> AnalysisResult:
        mask = context.mask
        rgb = context.array[:, :, :3]
        foreground = int(mask.sum())

        orphans = _orphan_mask(rgb, mask)
        count = int(orphans.sum())
        ratio = round(count / foreground, 6) if foreground else 0.0

        # `argwhere` varre em ordem C: já sai ordenado por (y, x), que é
        # exatamente a ordem pedida pelo relatório.
        positions = tuple(
            (int(x), int(y)) for y, x in np.argwhere(orphans)[:_MAX_POSITIONS]
        )

        result = AnalysisResult(
            metrics={
                "orphan_pixel_count": count,
                "orphan_pixel_ratio": ratio,
                "orphan_positions": positions,
            }
        )
        if ratio > _WARNING_RATIO:
            return result.with_warning(
                "PX-WARN-ORPHAN",
                f"{count} pixels isolados ({ratio:.2%} do sprite) — possível "
                "ruído de redução; confira antes de aceitar",
                count=count,
                ratio=ratio,
                threshold=_WARNING_RATIO,
            )
        return result


def _orphan_mask(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Máscara dos pixels opacos sem nenhum vizinho da mesma cor RGB.

    A borda do canvas é tratada como "sem vizinho": o padding entra com alpha
    falso, então um pixel encostado na borda só escapa de ser órfão se
    encontrar um gêmeo dentro da imagem.
    """
    if not mask.any():
        return np.zeros(mask.shape, dtype=bool)

    height, width = mask.shape
    padded_rgb = np.zeros((height + 2, width + 2, 3), dtype=np.uint8)
    padded_rgb[1 : height + 1, 1 : width + 1] = rgb
    padded_mask = np.zeros((height + 2, width + 2), dtype=bool)
    padded_mask[1 : height + 1, 1 : width + 1] = mask

    has_twin = np.zeros((height, width), dtype=bool)
    for row, col in _NEIGHBOURS_8:
        window_rgb = padded_rgb[1 + row : 1 + row + height, 1 + col : 1 + col + width]
        window_mask = padded_mask[1 + row : 1 + row + height, 1 + col : 1 + col + width]
        has_twin |= window_mask & np.all(window_rgb == rgb, axis=2)

    return mask & ~has_twin
