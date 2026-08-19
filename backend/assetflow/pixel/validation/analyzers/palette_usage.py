"""PaletteUsageAnalyzer — quem realmente usa o palette budget (plano Pixel §54).

O limite de cores é um orçamento: em uma paleta de 16, cada entrada precisa
pagar o próprio espaço. Esta análise mostra a distribuição real — quantos
pixels cada cor final pinta — e destaca as cores que aparecem em um punhado
de pixels.

E só destaca. Uma cor usada em 4 pixels pode ser exatamente o brilho do olho
ou o reflexo da lâmina, e nesse caso ela vale os 4 pixels. Por isso o
resultado é registro, não reprovação (plano Pixel §47): quem lê o relatório
decide se aquela entrada de paleta compensa ou se é sobra de quantização.
"""

from __future__ import annotations

from ...imaging import color_counts
from .base import AnalysisResult, QualityAnalyzer, ValidationContext

__all__ = ["PaletteUsageAnalyzer"]

#: Uma cor é "rara" quando pinta no máximo esta fração do foreground.
#: Experimental, como todos os limiares de qualidade (plano Pixel §60).
_RARE_COLOR_RATIO = 0.002

#: Piso do limiar: em um sprite minúsculo, 0,2% arredonda para zero e nenhuma
#: cor seria rara. Uma cor de um pixel único sempre merece ser listada.
_RARE_COLOR_FLOOR = 1


class PaletteUsageAnalyzer(QualityAnalyzer):
    """Frequência de cada cor final e a lista das cores raras."""

    name = "palette_usage"

    def analyze(self, context: ValidationContext) -> AnalysisResult:
        # `color_counts` já devolve ordenado por frequência decrescente e,
        # em caso de empate, pelo hexadecimal — a ordem do dicionário é o
        # próprio ranking e não depende da varredura da imagem.
        usage = color_counts(context.array)
        foreground = int(context.mask.sum())
        threshold = max(_RARE_COLOR_FLOOR, int(foreground * _RARE_COLOR_RATIO))

        rare = tuple(
            color
            for color, _count in sorted(
                (item for item in usage.items() if item[1] <= threshold),
                key=lambda item: (item[1], item[0]),
            )
        )

        result = AnalysisResult(
            metrics={"palette_usage": usage, "rare_colors": rare}
        )
        if rare:
            return result.with_warning(
                "PX-WARN-PALETTE-RARE",
                f"{len(rare)} cores pintam {threshold} pixel(s) ou menos: "
                f"{', '.join(rare)} — confira se cada uma paga o próprio "
                "espaço na paleta",
                count=len(rare),
                colors=list(rare),
                threshold=threshold,
            )
        return result
