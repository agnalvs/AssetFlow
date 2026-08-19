"""PX-PALETTE-001 — paleta travada é travada mesmo (plano Pixel §43).

Nos modos LOCKED e PROJECT o usuário não pediu "mais ou menos estas cores":
ele pediu que o inimigo novo use a mesma paleta do personagem, do tile e do
ícone (plano Pixel §11). Uma única cor intermediária sobrevivente já quebra a
coerência visual do conjunto — e é justamente o que sobra quando a
quantização roda antes de algum estágio voltar a misturar pixels.

Contar quantas cores escaparam e quais são as piores é o que permite decidir
entre "um artefato de borda" e "a paleta não foi aplicada".
"""

from __future__ import annotations

from collections.abc import Sequence

from ...contracts.validation_report import HardCheckResult
from ...imaging import color_counts, hex_to_rgb, rgb_to_hex
from .base import HardCheck, ValidationContext

__all__ = ["LockedPaletteCheck"]

#: Quantas cores estranhas entram no detalhe do relatório (plano Pixel §62).
_MAX_LISTED = 16


def _normalized_palette(colors: Sequence[str]) -> tuple[str, ...]:
    """Reescreve a paleta na mesma forma textual que a imagem produz.

    A comparação é feita por string ``#rrggbb``; passar pela conversão de
    ida e volta garante que ``#FFF`` do YAML e o ``#ffffff`` medido no PNG
    sejam a mesma cor. Duplicatas somem para que ``palette_size`` reflita as
    cores realmente disponíveis.
    """
    unique: list[str] = []
    for color in colors:
        normalized = rgb_to_hex(hex_to_rgb(color))
        if normalized not in unique:
            unique.append(normalized)
    return tuple(unique)


class LockedPaletteCheck(HardCheck):
    """Toda cor de pixel opaco pertence à paleta travada do spec."""

    code: str = "PX-PALETTE-001"
    name: str = "Locked Palette Compliance"

    def applies_to(self, context: ValidationContext) -> bool:
        spec = context.spec
        return spec.validation.require_locked_palette and spec.palette.is_locked

    def skip_reason(self, context: ValidationContext) -> str:
        spec = context.spec
        if not spec.validation.require_locked_palette:
            return "require_locked_palette desligado no profile"
        return "o profile deriva a paleta da imagem, não a trava"

    def run(self, context: ValidationContext) -> HardCheckResult:
        spec_palette = context.spec.palette
        if not spec_palette.colors:
            # Paleta PROJECT que o PixelProfileRegistry não conseguiu resolver:
            # o `palette_id` não existe na tabela `palettes:`. Sem cores, o
            # quantizador cai para median cut e entrega um asset bonito que
            # **não** usa a paleta do projeto. Reprovar aqui é o que faz a
            # configuração quebrada aparecer no relatório do asset, em vez de
            # virar uma incoerência visual silenciosa entre personagem e tile.
            return self.failed(
                f"paleta de projeto '{spec_palette.palette_id}' não foi "
                "resolvida: nenhuma cor para conferir",
                expected="uma paleta de projeto resolvida",
                actual="paleta vazia",
                palette_id=spec_palette.palette_id,
                palette_size=0,
            )

        palette = _normalized_palette(spec_palette.colors)
        allowed = set(palette)
        usage = color_counts(context.array)

        # `color_counts` vem ordenado da cor mais frequente para a menos, então
        # as primeiras estranhas da lista já são as que mais poluem a imagem.
        foreign = [
            {"color": color, "pixels": pixels}
            for color, pixels in usage.items()
            if color not in allowed
        ]
        expected = f"apenas as {len(palette)} cores da paleta"

        if not foreign:
            return self.passed(
                f"paleta travada respeitada — cores em uso: {len(usage)} "
                f"de {len(palette)}",
                expected=expected,
                actual="nenhuma cor fora da paleta",
                palette_size=len(palette),
                used_colors=len(usage),
                foreign_color_count=0,
            )

        foreign_pixels = sum(int(entry["pixels"]) for entry in foreign)
        return self.failed(
            f"paleta travada violada — cores estranhas: {len(foreign)}, "
            f"pixels afetados: {foreign_pixels}",
            expected=expected,
            actual=f"{len(foreign)} cores fora da paleta",
            palette_size=len(palette),
            used_colors=len(usage),
            foreign_color_count=len(foreign),
            foreign_pixels=foreign_pixels,
            foreign_colors=foreign[:_MAX_LISTED],
        )
