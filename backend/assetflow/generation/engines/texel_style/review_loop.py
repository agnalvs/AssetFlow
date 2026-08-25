"""ReviewLoop — a etapa 4 do engine estilo Texel (plano de motores §9.4).

Depois de executar o plano, o agente **olha o canvas e decide ajustes**. Esta
é a etapa que separa um gerador procedural de um agente: um gerador imprime a
receita e vai embora; o agente confere o resultado contra critérios e corrige
o que dá para corrigir.

As correções aqui são poucas e conservadoras, e cada uma existe por um defeito
concreto de pixel art:

``contorno``
    Sem uma linha escura em volta, um sprite pequeno se dissolve em qualquer
    fundo que não seja o do editor. O contorno é o que garante silhueta — o
    critério que o §20 lista primeiro depois da fidelidade.
``pixels órfãos``
    Um pixel opaco sem nenhum vizinho é ruído. Em 1024 px ninguém vê; em 32×32
    ele é 0,1% da imagem e salta aos olhos.
``orçamento de cores``
    O plano já limita a paleta, mas ruído sobreposto pode criar combinações
    inesperadas. Quem estoura o orçamento é remapeado para a cor mais próxima
    que já está em uso.
``sprite vazio``
    Uma receita que não desenhou nada precisa falhar alto, não entregar um PNG
    transparente que só será notado três telas adiante.

**Toda correção passa pelas mesmas ferramentas do desenho.** O Review Loop não
mexe no canvas por fora: ele emite tool calls, que entram no mesmo log. É o
que mantém a promessa do §9.5 — o histórico reconstrói o resultado final, e
não só o rascunho.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .canvas import RGBA, PixelCanvas
from .tool_executor import ToolCall, ToolCallLog, ToolExecutor
from .tools.base import as_color

__all__ = ["ReviewFinding", "ReviewReport", "ReviewLoop"]

#: Abaixo disto o sprite é considerado vazio demais para ser um asset.
_MIN_OCCUPANCY = 0.02


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    """Algo que a revisão notou, e o que fez a respeito."""

    code: str
    message: str
    #: Quantos pixels a correção mexeu. ``0`` = só observação.
    pixels_changed: int = 0

    def document(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "pixels_changed": self.pixels_changed,
        }


@dataclass(slots=True)
class ReviewReport:
    """O resultado da revisão inteira."""

    findings: list[ReviewFinding] = field(default_factory=list)
    passes: int = 0

    def add(self, code: str, message: str, pixels_changed: int = 0) -> None:
        self.findings.append(ReviewFinding(code, message, pixels_changed))

    @property
    def corrected_pixels(self) -> int:
        return sum(finding.pixels_changed for finding in self.findings)

    def document(self) -> dict[str, Any]:
        return {
            "passes": self.passes,
            "corrected_pixels": self.corrected_pixels,
            "findings": [finding.document() for finding in self.findings],
        }


class ReviewLoop:
    """Inspeciona o canvas e emite as correções (plano de motores §9.4)."""

    def __init__(self, executor: ToolExecutor) -> None:
        self._executor = executor

    # ------------------------------------------------------------------
    def run(
        self,
        canvas: PixelCanvas,
        *,
        outline_color: str,
        max_colors: int | None,
        log: ToolCallLog,
        max_passes: int = 2,
    ) -> ReviewReport:
        """Revisa o canvas, corrigindo o que der.

        A **ordem** é a parte que importa, e ela custou um teste para
        aparecer: limpar antes, contornar depois.

        Contornar primeiro parece inofensivo e faz o contrário do que se quer.
        O contorno envolve todo pixel opaco — inclusive o pixel solto que a
        limpeza ia remover. Envolvido, ele deixa de ser órfão, sobrevive à
        limpeza e vira um borrão de cinco pixels no meio do nada: a sujeira
        não só permanece, como fica maior e mais visível.

        ``max_passes`` limita a limpeza porque remover um pixel pode deixar o
        vizinho sozinho. Duas passadas resolvem o caso real; um laço até
        convergir poderia apagar um sprite fino inteiro, pixel a pixel, e isso
        seria pior do que deixar um ponto solto.
        """
        report = ReviewReport()

        for index in range(max_passes):
            report.passes = index + 1
            self._executor.execute(
                canvas,
                ToolCall(tool="view_canvas", params={}, note=f"revisão {index + 1}"),
                log,
            )
            if self._remove_orphans(canvas, log, report) == 0:
                break

        # Contorno depois da limpeza, e uma vez só: ele fecha a silhueta do
        # que ficou de pé.
        self._add_outline(canvas, outline_color, log, report)
        self._enforce_palette(canvas, max_colors, log, report)
        self._check_not_empty(canvas, report)
        return report

    # ------------------------------------------------------------------
    def _add_outline(
        self,
        canvas: PixelCanvas,
        outline_color: str,
        log: ToolCallLog,
        report: ReviewReport,
    ) -> int:
        """Desenha o contorno na borda externa do conteúdo."""
        edges = canvas.edge_pixels()
        if not edges:
            return 0
        record = self._executor.execute(
            canvas,
            ToolCall(
                tool="draw_pixels",
                params={"points": [list(point) for point in edges], "color": outline_color},
                note="contorno da silhueta",
            ),
            log,
        )
        if record.pixels_changed:
            report.add(
                "TX-OUTLINE",
                f"contorno aplicado em {record.pixels_changed} pixels",
                record.pixels_changed,
            )
        return record.pixels_changed

    def _remove_orphans(
        self, canvas: PixelCanvas, log: ToolCallLog, report: ReviewReport
    ) -> int:
        """Apaga pixels opacos que ficaram sozinhos."""
        orphans = canvas.orphans()
        if not orphans:
            return 0
        record = self._executor.execute(
            canvas,
            ToolCall(
                tool="draw_pixels",
                params={
                    "points": [list(point) for point in orphans],
                    # Alpha 0: apagar é pintar de transparente. Não existe
                    # ferramenta de borracha, e não precisa existir.
                    "color": [0, 0, 0, 0],
                },
                note="remoção de pixels órfãos",
            ),
            log,
        )
        if record.pixels_changed:
            report.add(
                "TX-ORPHAN",
                f"{record.pixels_changed} pixel(s) solto(s) removido(s)",
                record.pixels_changed,
            )
        return record.pixels_changed

    def _enforce_palette(
        self,
        canvas: PixelCanvas,
        max_colors: int | None,
        log: ToolCallLog,
        report: ReviewReport,
    ) -> None:
        """Traz o sprite para dentro do orçamento de cores.

        As cores que ficam são as **mais usadas**, e as que saem viram a mais
        próxima entre elas. Manter por frequência preserva as áreas grandes —
        que são o que define o objeto — e sacrifica detalhes pontuais, que é a
        ordem certa de perder informação em pixel art.
        """
        if max_colors is None:
            return
        counts = canvas.colors()
        if len(counts) <= max_colors:
            return

        keep = list(counts)[:max_colors]
        drop = list(counts)[max_colors:]

        remapped = 0
        for color in drop:
            replacement = _closest(color, keep)
            points = [
                [x, y] for x, y, current in canvas if current == color
            ]
            if not points:
                continue
            record = self._executor.execute(
                canvas,
                ToolCall(
                    tool="draw_pixels",
                    params={"points": points, "color": list(replacement)},
                    note="ajuste de paleta",
                ),
                log,
            )
            remapped += record.pixels_changed

        if remapped:
            report.add(
                "TX-PALETTE",
                f"paleta reduzida a {max_colors} cores ({remapped} pixels remapeados)",
                remapped,
            )

    def _check_not_empty(self, canvas: PixelCanvas, report: ReviewReport) -> None:
        """Registra um sprite vazio demais, sem tentar consertá-lo.

        Não há correção honesta possível aqui: inventar pixels para tapar o
        buraco entregaria um asset que ninguém pediu. O achado sobe como aviso
        e o Pixel Validator, depois, decide se o resultado passa.
        """
        stats = canvas.stats()
        if stats.occupancy < _MIN_OCCUPANCY:
            report.add(
                "TX-EMPTY",
                f"o desenho ocupa apenas {stats.occupancy:.1%} do canvas",
            )


def _closest(color: RGBA, candidates: list[RGBA]) -> RGBA:
    """A cor mais próxima em distância euclidiana no espaço RGB.

    RGB simples, e não um espaço perceptual: as paletas do engine têm meia
    dúzia de cores bem separadas, e a diferença entre RGB e CIELAB nesse
    cenário não muda a escolha — muda só o custo.
    """
    target = as_color(color)
    return min(
        candidates,
        key=lambda item: sum(
            (int(item[index]) - int(target[index])) ** 2 for index in range(3)
        ),
    )
