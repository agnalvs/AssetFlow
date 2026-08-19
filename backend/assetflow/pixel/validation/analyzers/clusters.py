"""ClusterAnalyzer — tamanho dos blocos de cor sólida (plano Pixel §49 e §50).

Pixel Art bem resolvida é feita de superfícies: áreas contíguas da mesma cor,
com poucas transições. Quando uma imagem de difusão é reduzida sem cuidado,
essas superfícies se desfazem em cacos de um, dois e três pixels — o mesmo
sprite passa a ter centenas de componentes conexos onde deveria ter dezenas.

Este analisador mede exatamente isso, usando ``color_clusters`` (componentes
conexos **por cor**, 8-conectado). E para por aí: o plano Pixel §51 proíbe
tratar um cluster de 1 pixel como erro — não existe regra universal dizendo
que ele está errado, e artista profissional usa pixel isolado de propósito.
O ``microcluster_ratio`` é indicador, não verdade artística.
"""

from __future__ import annotations

from ...imaging import color_clusters
from .base import AnalysisResult, QualityAnalyzer, ValidationContext

__all__ = ["ClusterAnalyzer"]

#: Um cluster é "micro" até este tamanho (plano Pixel §50).
_MICRO_SIZES = (1, 2, 3)

#: Acima desta proporção de microclusters o relatório avisa. Valor
#: experimental, calibrado junto com as penalidades do QualityScorer.
_WARNING_RATIO = 0.25


class ClusterAnalyzer(QualityAnalyzer):
    """Conta componentes conexos por cor e a fatia deles que é minúscula."""

    name = "clusters"

    def analyze(self, context: ValidationContext) -> AnalysisResult:
        clusters = color_clusters(context.array)
        total = len(clusters)

        sizes = [area for _color, area, _box in clusters]
        by_size = {size: sizes.count(size) for size in _MICRO_SIZES}
        micro = sum(by_size.values())
        ratio = round(micro / total, 6) if total else 0.0

        result = AnalysisResult(
            metrics={
                "cluster_total": total,
                "single_pixel_clusters": by_size[1],
                "two_pixel_clusters": by_size[2],
                "three_pixel_clusters": by_size[3],
                "microcluster_ratio": ratio,
            }
        )
        if ratio > _WARNING_RATIO:
            return result.with_warning(
                "PX-WARN-MICROCLUSTER",
                f"{micro} de {total} blocos de cor têm 3 pixels ou menos "
                f"({ratio:.2%}) — a imagem pode não ter superfícies sólidas",
                count=micro,
                ratio=ratio,
                threshold=_WARNING_RATIO,
                cluster_total=total,
            )
        return result
