"""LLMPixelReviewer — o revisor do Optimizer, feito por um modelo (§42).

O revisor determinístico enxerga o que o ``PixelValidator`` sabe medir: pixel
órfão, contorno esfarelado, paleta estourada, ocupação. É bastante, e é
limitado do mesmo jeito que qualquer lista fechada: ele não tem como notar que
a chaminé da casa ficou solta do telhado, porque "chaminé" não é uma medida.

Este revisor troca a lista por um modelo. Ele **descreve** problemas
estruturais a partir do retrato do canvas — e só isso: o que fazer a respeito
continua sendo do :class:`RepairPlanner`, e cada correção continua passando
pelo executor, pela guarda de paleta e pelo log.

Por que a fronteira fica exatamente aqui
----------------------------------------
Porque é o que impede um modelo de estragar um asset. Um revisor que também
corrigisse poderia pintar qualquer coisa em qualquer lugar; um que só descreve
esbarra em três muros que não são dele: o §17 (preservar o pixel que pode ser
um olho), o §16 (a paleta manda) e o §20 (se a nota cair, tudo é descartado).

O pior caso de um laudo alucinado é um reparo inútil registrado no log — não
um sprite destruído.

Por que ele mora **fora** de ``assetflow/pixel/``
-------------------------------------------------
A ilha Pixel Exact não faz rede, não lê configuração e não conhece fornecedor.
Um revisor que fala HTTP não cabe lá dentro sem furar essa regra. Então a ilha
define o contrato — ``review(canvas, spec, validation) -> PixelReview`` — e
esta camada o implementa, entrando por injeção no ``bootstrap``.

Queda é rebaixamento, nunca falha
---------------------------------
Provedor fora do ar, JSON malformado, resposta vazia: em qualquer um desses
casos o laudo do revisor determinístico vale, e o job segue. Uma geração não
pode morrer porque um modelo de texto não respondeu — no máximo, ser menos
revisada, e dizer isso.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..pixel.optimizer.canvas import PixelCanvas
from ..pixel.optimizer.contracts import IssueSeverity, PixelIssue, PixelReview
from ..pixel.optimizer.reviewer import PixelReviewer
from .chat import ChatClient, ChatError

__all__ = ["SYSTEM_PROMPT", "LLMPixelReviewer"]

_LOG = logging.getLogger("assetflow.llm.pixel_reviewer")

#: Tipos de problema que o :class:`RepairPlanner` sabe tratar. Um tipo fora
#: desta lista **não** é descartado: ele entra no laudo e o planejador o
#: declina com o motivo genérico — que é exatamente a informação que se quer
#: quando o revisor aprende a ver algo que o planejador ainda não trata.
#:
#: A lista é montada no prompt a partir daqui, e não escrita nele à mão: duas
#: cópias divergiriam no dia em que um tipo novo entrasse, e o modelo passaria
#: a nomear problemas que o planejador não reconhece — sem que ninguém
#: percebesse.
KNOWN_TYPES = (
    "orphan_pixel",
    "fragmented_outline",
    "palette_overflow",
    "locked_palette_violation",
    "empty_canvas",
    "overfilled_canvas",
    "border_touch",
)

SYSTEM_PROMPT = """Você revisa sprites de Pixel Art já reduzidos à grade final.

Seu trabalho é DESCREVER problemas estruturais. Você não corrige nada, não
escolhe cores e não desenha: outra peça decide o que fazer com o seu laudo.

Responda SOMENTE com JSON neste formato:

{"issues": [
  {"type": "orphan_pixel", "severity": "medium", "region": "copa",
   "pixels": [[6, 17]], "detail": "pixel solto acima da folhagem"}
]}

Regras:
- `type` preferencialmente um destes: {tipos}. Se o que você viu não é nenhum
  deles, use um nome curto em snake_case — o laudo registra, mesmo sem
  correção conhecida.
- `severity` é low, medium ou high.
- `pixels` são coordenadas INTEIRAS dentro da grade, no formato [x, y].
  Só inclua posições de que você tem certeza.
- `detail` é uma frase curta em português.
- Nenhum problema encontrado é uma resposta legítima: {"issues": []}.
- Não invente problema para parecer útil. Um laudo vazio sobre um sprite bom
  vale mais do que um laudo cheio sobre um sprite bom.
""".replace("{tipos}", ", ".join(KNOWN_TYPES))


class LLMPixelReviewer:
    """Revisa o sprite com um modelo de linguagem (plano Optimizer §42)."""

    def __init__(
        self,
        client: ChatClient,
        *,
        fallback: PixelReviewer | None = None,
        max_attempts: int = 2,
    ) -> None:
        self._client = client
        self._fallback = fallback or PixelReviewer()
        self._max_attempts = max(1, max_attempts)
        self._degraded = False

    @property
    def name(self) -> str:
        """Quem revisou de fato — é o que vai para ``optimizer.json``.

        Ele muda para ``heuristic`` depois de uma queda, e a mudança é o ponto:
        dois assets com laudos diferentes precisam dizer se foram revisados
        pela mesma coisa.
        """
        return "heuristic" if self._degraded else "llm"

    # ------------------------------------------------------------------
    def review(self, canvas: PixelCanvas, spec, validation) -> PixelReview:
        base = self._fallback.review(canvas, spec, validation)

        try:
            issues = self._ask(canvas, spec, validation)
        except ChatError as exc:
            self._degraded = True
            _LOG.warning("revisor por LLM indisponível (%s); vale o determinístico", exc)
            return base

        self._degraded = False
        # O laudo do modelo entra **por cima** do determinístico, não no lugar
        # dele: o que o Validator mediu continua valendo, e a contribuição do
        # modelo é o que ele viu além disso.
        for issue in issues:
            if not _duplicate(base, issue):
                base.add(issue)
        return base

    # ------------------------------------------------------------------
    def _ask(self, canvas: PixelCanvas, spec, validation) -> list[PixelIssue]:
        prompt = _describe(canvas, spec, validation)
        last: str = ""

        for attempt in range(1, self._max_attempts + 1):
            texto = self._client.complete(
                SYSTEM_PROMPT,
                prompt if attempt == 1 else f"{prompt}\n\nA tentativa anterior falhou: {last}",
            )
            try:
                return _parse(texto, canvas)
            except ValueError as exc:
                last = str(exc)
                _LOG.debug("laudo do LLM recusado (tentativa %s): %s", attempt, exc)

        raise ChatError(f"o modelo não produziu um laudo utilizável: {last}")


# ----------------------------------------------------------------------
def _describe(canvas: PixelCanvas, spec, validation) -> str:
    """O retrato do sprite, em texto.

    O mapa vem como índices de paleta, um caractere por pixel, e não como uma
    lista de cores por coordenada: em 64×64 a lista teria milhares de linhas e
    o modelo perderia a **forma**, que é justamente o que se está pedindo que
    ele veja.
    """
    stats = canvas.stats()
    colors = list(canvas.colors())
    index = {color: position for position, color in enumerate(colors)}

    linhas = []
    for y in range(canvas.height):
        linha = []
        for x in range(canvas.width):
            color = canvas.get(x, y)
            linha.append("." if color[3] == 0 else _DIGITS[index[color] % len(_DIGITS)])
        linhas.append("".join(linha))

    paleta = ", ".join(
        f"{_DIGITS[position % len(_DIGITS)]}=#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
        for position, color in enumerate(colors)
    )
    falhas = [check.code for check in validation.failures]
    avisos = [warning.code for warning in validation.quality.warnings]

    return (
        f"Grade: {stats.width}x{stats.height}\n"
        f"Ocupação: {stats.occupancy:.1%} ({stats.opaque_pixels} pixels opacos)\n"
        f"Pixels isolados: {stats.orphan_pixels}\n"
        f"Cores em uso ({stats.color_count}, limite {spec.max_colors}): {paleta}\n"
        f"Falhas do validador: {falhas or 'nenhuma'}\n"
        f"Avisos do validador: {avisos or 'nenhum'}\n"
        f"Nota atual: {validation.quality.score}\n\n"
        "Mapa (x cresce para a direita, y para baixo; '.' é transparente):\n"
        + "\n".join(linhas)
    )


#: Um caractere por cor. Paletas de Pixel Art cabem folgadamente aqui.
_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _parse(text: str, canvas: PixelCanvas) -> list[PixelIssue]:
    """Lê o laudo e recusa o que não dá para usar.

    Coordenada fora da grade é **descartada** em vez de derrubar o laudo: um
    modelo que erra uma posição entre vinte ainda produziu dezenove úteis, e
    perder as dezenove por causa da vigésima seria o pior dos dois mundos. Um
    problema que fica sem nenhuma posição válida, esse sim é descartado — ele
    não teria como virar reparo.
    """
    payload = _json_object(text)
    raw = payload.get("issues")
    if not isinstance(raw, list):
        raise ValueError("faltou a lista 'issues'")

    issues: list[PixelIssue] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip()
        if not kind:
            continue

        pixels = tuple(_positions(item.get("pixels"), canvas))
        if item.get("pixels") and not pixels:
            continue

        issues.append(
            PixelIssue(
                type=kind,
                severity=_severity(item.get("severity")),
                region=str(item["region"]) if item.get("region") else None,
                position=pixels[0] if len(pixels) == 1 else None,
                detail=str(item.get("detail") or "")[:300],
                pixels=pixels,
            )
        )
    return issues


def _json_object(text: str) -> dict[str, Any]:
    """O objeto JSON dentro da resposta, mesmo cercado de prosa ou de ```."""
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("a resposta não contém um objeto JSON")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("a resposta não é um objeto JSON")
    return payload


def _positions(raw: Any, canvas: PixelCanvas) -> list[tuple[int, int]]:
    if not isinstance(raw, list):
        return []
    found: list[tuple[int, int]] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        try:
            x, y = int(item[0]), int(item[1])
        except (TypeError, ValueError):
            continue
        if canvas.contains(x, y):
            found.append((x, y))
    return found


def _severity(raw: Any) -> IssueSeverity:
    try:
        return IssueSeverity(str(raw).strip().lower())
    except ValueError:
        return IssueSeverity.LOW


def _duplicate(review: PixelReview, issue: PixelIssue) -> bool:
    """O determinístico já viu isto?

    Sem esta conferência, um pixel órfão apareceria duas vezes no laudo — uma
    do Validator e outra do modelo —, e o planejador tentaria apagá-lo duas
    vezes. A segunda não muda nada, mas polui o log com um reparo que não
    corrigiu nada.
    """
    for existing in review.issues:
        if existing.type != issue.type:
            continue
        if issue.position is not None and existing.position == issue.position:
            return True
        if not issue.pixels and not existing.pixels:
            return True
    return False
