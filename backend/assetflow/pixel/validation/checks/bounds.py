"""PX-BOUND-001 — o sprite não pode estar cortado na borda (plano Pixel §45).

Personagem, prop e ícone são assets isolados: o conteúdo opaco encostando na
borda do canvas quase sempre significa que a composição foi enquadrada apertada
e a silhueta saiu decepada — um braço que termina no nada, uma cabeça sem topo.

O rigor é do profile, não do check (plano Pixel §65): um tile *precisa* tocar
as quatro bordas, então ``boundary_touch`` decide entre ``ignore`` (nem roda),
``warn`` (aprova e explica) e ``fail`` (reprova). No modo ``warn`` o aviso
visível de qualidade é emitido pelo SpriteOccupancyAnalyzer — hard check só
aprova ou reprova, nunca produz aviso (plano Pixel §38 e §47).
"""

from __future__ import annotations

import numpy as np

from ...contracts.validation_report import HardCheckResult
from ...imaging import bounding_box, touches_border
from .base import HardCheck, ValidationContext

__all__ = ["BoundaryCheck"]


def _touched_borders(mask: np.ndarray) -> tuple[str, ...]:
    """Nomeia as bordas tocadas, na ordem fixa topo/base/esquerda/direita.

    ``touches_border`` já respondeu *se* há contato; isto só diz *onde*, e a
    ordem é fixa para que o relatório de dois assets iguais seja igual.
    """
    return tuple(
        name
        for name, touched in (
            ("top", bool(mask[0, :].any())),
            ("bottom", bool(mask[-1, :].any())),
            ("left", bool(mask[:, 0].any())),
            ("right", bool(mask[:, -1].any())),
        )
        if touched
    )


class BoundaryCheck(HardCheck):
    """Conteúdo opaco encostando na borda do canvas."""

    code: str = "PX-BOUND-001"
    name: str = "Boundary Clipping"

    def applies_to(self, context: ValidationContext) -> bool:
        return context.spec.validation.boundary_touch != "ignore"

    def skip_reason(self, context: ValidationContext) -> str:
        return "boundary_touch = 'ignore' no profile"

    def run(self, context: ValidationContext) -> HardCheckResult:
        policy = context.spec.validation.boundary_touch
        mask = context.mask
        box = bounding_box(mask)
        expected = "sem contato com a borda"

        if box is None:
            # Imagem sem foreground: quem reprova o vazio é o PX-EMPTY-001.
            # Reprovar aqui também empilharia duas falhas para a mesma causa.
            return self.passed(
                "sem conteúdo opaco para avaliar",
                expected=expected,
                actual="sem conteúdo",
                policy=policy,
                touches_border=False,
                borders=[],
                bounding_box=None,
            )

        borders = _touched_borders(mask)
        detail = {
            "policy": policy,
            "touches_border": touches_border(mask),
            "borders": list(borders),
            "bounding_box": list(box),
        }

        if not borders:
            return self.passed(
                "o conteúdo opaco não encosta nas bordas do canvas",
                expected=expected,
                actual="sem contato",
                **detail,
            )

        listed = ", ".join(borders)
        actual = f"encosta em: {listed}"

        if policy == "fail":
            return self.failed(
                f"conteúdo cortado na borda do canvas: encosta em {listed}",
                expected=expected,
                actual=actual,
                **detail,
            )
        return self.passed(
            f"o conteúdo encosta em {listed}; o profile trata contato como "
            "aviso (boundary_touch='warn'), então o requisito está atendido",
            expected=expected,
            actual=actual,
            **detail,
        )
