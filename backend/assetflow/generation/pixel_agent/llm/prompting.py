"""O prompt do planejador e o parse do que ele devolve (plano de correção §18).

Este módulo é a fronteira entre "um modelo de linguagem escreveu um texto" e
"existe um plano de desenho válido". Tudo que vem do LLM é tratado como
entrada não confiável: coordenadas fora do canvas, ferramentas inventadas,
cores malformadas, JSON com lixo em volta. O parse recusa cada um desses casos
com uma mensagem específica, e é a mensagem que vira o pedido de correção na
segunda tentativa.

Por que validar antes de desenhar, se as ferramentas já ignoram o que não cabe
---------------------------------------------------------------------------
Porque "ignorar" transforma um plano ruim em um sprite vazio, e um sprite
vazio não diz o que houve. Recusando na entrada, o planner sabe **por que**
falhou, pode pedir de novo com a crítica junto, e só então cai para as
receitas — com um aviso que explica a queda.

Sobre o idioma do prompt
------------------------
O texto enviado ao modelo é em inglês, como já são os prompts que os adapters
montam para SDXL e FLUX. Não é inconsistência com o resto do projeto: é a
mesma regra — texto voltado a modelo em inglês, texto voltado a gente em
português.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..contracts.command import ToolCall
from ..contracts.plan import DrawingBrief, DrawingPlan
from ..palette import SpritePalette

__all__ = ["LLMPlanError", "build_prompt", "parse_plan"]


class LLMPlanError(ValueError):
    """O modelo devolveu algo que não é um plano de desenho utilizável."""


#: Ferramentas que o planejador pode usar, com os parâmetros exatos.
#:
#: ``inspect_canvas`` fica de fora de propósito: ela não desenha, e um plano
#: cheio de inspeções só gastaria tokens. Quem inspeciona é o revisor, depois.
_TOOL_SPEC = """
- fill_rect      {"x0": int, "y0": int, "x1": int, "y1": int, "color": "#rrggbb"}
- draw_rect_line {"x0": int, "y0": int, "x1": int, "y1": int, "color": "#rrggbb"}  (alias of draw_line)
- draw_line      {"x0": int, "y0": int, "x1": int, "y1": int, "color": "#rrggbb"}
- draw_circle    {"cx": int, "cy": int, "radius": int, "color": "#rrggbb", "filled": bool}
- draw_ellipse   {"cx": int, "cy": int, "rx": int, "ry": int, "color": "#rrggbb", "filled": bool}
- draw_triangle  {"x0": int, "y0": int, "x1": int, "y1": int, "x2": int, "y2": int, "color": "#rrggbb"}
- draw_pixel     {"x": int, "y": int, "color": "#rrggbb"}
- draw_pixels    {"points": [[int, int], ...], "color": "#rrggbb"}
""".strip()

def build_prompt(brief: DrawingBrief) -> tuple[str, str]:
    """``(system, user)`` para este pedido.

    O tamanho do canvas entra no *system* e não só no *user* porque é a
    restrição que o modelo mais viola: repeti-la junto das regras duras é o
    que mais reduz plano com coordenada fora da grade.
    """
    max_colors = brief.max_colors or 16
    system = _SYSTEM_TEMPLATE % {
        "tools": _TOOL_SPEC,
        "max_x": brief.width - 1,
        "max_y": brief.height - 1,
        "max_colors": max_colors,
        "budget": _budget_advice(brief),
    }

    user = (
        f"Canvas: {brief.width}x{brief.height} pixels.\n"
        f"Asset type: {brief.asset_type}.\n"
        f"Subject: {brief.subject}.\n"
        f"Color budget: {max_colors} colors.\n"
        f"Background: {'transparent' if brief.transparent else 'solid'}.\n\n"
        "Produce the drawing plan."
    )
    return system, user


def _budget_advice(brief: DrawingBrief) -> str:
    """Conselho que muda com o tamanho — é onde os erros mudam de natureza."""
    smallest = min(brief.width, brief.height)
    if smallest <= 16:
        return (
            "This canvas is tiny. Draw the subject as 2-4 blocky shapes and "
            "nothing else; there is no room for features."
        )
    if smallest <= 32:
        return (
            "At this size, one or two identifying features are all that fit — "
            "a door and a window, a handle, a stem."
        )
    return (
        "There is room for the main shape plus a few identifying features, "
        "but still no room for texture or small ornaments."
    )


#: O texto enviado ao modelo, com os limites do canvas interpolados.
_SYSTEM_TEMPLATE = """You are a pixel-art director. You do not draw images: \
you produce a JSON drawing plan that a deterministic tool executor will run on \
a small pixel grid.

Return ONLY a JSON object, with no prose and no markdown fences:

{
  "palette": {
    "base": "#rrggbb", "shade": "#rrggbb", "light": "#rrggbb",
    "accent": "#rrggbb", "outline": "#rrggbb"
  },
  "regions": [{"name": "roof", "bounds": [x0, y0, x1, y1]}],
  "calls": [{"tool": "fill_rect", "params": {...}, "note": "why"}]
}

TOOLS (use only these, with exactly these parameter names):
%(tools)s

HARD RULES - a plan that breaks any of them is rejected:
1. Every coordinate is an INTEGER in [0, %(max_x)d] for x and [0, %(max_y)d]
   for y. There are no half pixels.
2. Use at most %(max_colors)d distinct colors, including the outline.
3. Do NOT draw the outline yourself. The system adds it around the finished
   silhouette. Reserve "outline" in the palette as the darkest color.
4. Leave at least 1 empty pixel of margin on all four sides, so the outline
   fits. Exception: tiles and ground blocks, which must fill the whole canvas.
5. Order calls back to front: big shapes first, details last. Later calls
   paint over earlier ones.

HOW TO DRAW WELL AT THIS SIZE:
- The silhouette is what makes the subject recognizable. Get the overall shape
  right before any detail.
- %(budget)s
- Use `shade` on the side away from the light (bottom-right) and `light` on
  the lit side (top-left). Flat objects read as stickers.
- Details that need fewer than 2 pixels do not survive. Skip them.
- Prefer 3-8 large shapes over dozens of single pixels."""


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------
#: Ferramentas aceitas no plano, com os parâmetros obrigatórios de cada uma.
_ALLOWED: dict[str, tuple[str, ...]] = {
    "fill_rect": ("x0", "y0", "x1", "y1"),
    "draw_line": ("x0", "y0", "x1", "y1"),
    "draw_circle": ("cx", "cy", "radius"),
    "draw_ellipse": ("cx", "cy", "rx", "ry"),
    "draw_triangle": ("x0", "y0", "x1", "y1", "x2", "y2"),
    "draw_pixel": ("x", "y"),
    "draw_pixels": ("points",),
}

#: Nomes que os modelos inventam com frequência, mapeados para o real. Ser
#: tolerante aqui é barato e evita jogar fora um plano bom por um sinônimo.
_ALIASES = {
    "draw_rect": "fill_rect",
    "draw_rect_line": "draw_line",
    "rect": "fill_rect",
    "fill_rectangle": "fill_rect",
    "line": "draw_line",
    "circle": "draw_circle",
    "ellipse": "draw_ellipse",
    "triangle": "draw_triangle",
    "pixel": "draw_pixel",
    "pixels": "draw_pixels",
    "set_pixel": "draw_pixel",
    "set_pixels": "draw_pixels",
}

_HEX = re.compile(r"^#?([0-9a-fA-F]{3,8})$")
_MAX_CALLS = 400


def parse_plan(raw: str, brief: DrawingBrief) -> DrawingPlan:
    """Transforma a resposta do modelo em um :class:`DrawingPlan` válido.

    Raises:
        LLMPlanError: com o motivo exato, em inglês — ele é reenviado ao
            modelo na segunda tentativa, e o modelo lê inglês melhor.
    """
    document = _load_json(raw)

    palette = _parse_palette(document.get("palette"))
    calls = _parse_calls(document.get("calls"), brief)
    if not calls:
        raise LLMPlanError("the plan has no drawing calls")

    regions = _parse_regions(document.get("regions"))

    return DrawingPlan(
        canvas=(brief.width, brief.height),
        asset_type=brief.asset_type,
        subject=brief.subject,
        recipe="llm",
        palette=palette,
        regions=regions,
        calls=tuple(calls),
    )


def _load_json(raw: str) -> dict[str, Any]:
    """Extrai o objeto JSON, tolerando cerca de markdown e prosa em volta.

    Modelos pequenos embrulham JSON em ```json ... ``` mesmo quando se pede o
    contrário. Recusar por causa disso jogaria fora planos perfeitamente bons.
    """
    text = (raw or "").strip()
    if not text:
        raise LLMPlanError("the model returned an empty response")

    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMPlanError("no JSON object found in the response")

    try:
        document = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMPlanError(f"the response is not valid JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise LLMPlanError("the top-level JSON value must be an object")
    return document


def _parse_palette(raw: Any) -> SpritePalette:
    """A paleta do plano, com papéis faltantes preenchidos.

    Um papel ausente não invalida o plano: o modelo às vezes manda só três
    cores, e derivar as outras é melhor do que recusar. O que **não** se
    inventa é o contorno — sem ele o sprite perde a silhueta, e um cinza
    qualquer no lugar seria pior do que um preto declarado.
    """
    data = raw if isinstance(raw, dict) else {}
    colors = {
        key: _parse_color(value, f"palette.{key}")
        for key, value in data.items()
        if isinstance(value, str)
    }

    base = colors.get("base") or colors.get("main") or "#8a8a92"
    return SpritePalette(
        base=base,
        shade=colors.get("shade") or colors.get("dark") or _shift(base, -40),
        light=colors.get("light") or colors.get("highlight") or _shift(base, 40),
        accent=colors.get("accent") or base,
        outline=colors.get("outline") or "#1a1a1a",
        extra={
            key: value
            for key, value in colors.items()
            if key not in {"base", "shade", "light", "accent", "outline",
                           "main", "dark", "highlight"}
        },
    )


def _parse_calls(raw: Any, brief: DrawingBrief) -> list[ToolCall]:
    if not isinstance(raw, list):
        raise LLMPlanError("`calls` must be a list")
    if len(raw) > _MAX_CALLS:
        raise LLMPlanError(f"too many calls: {len(raw)} (limit is {_MAX_CALLS})")

    calls: list[ToolCall] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise LLMPlanError(f"call #{index} is not an object")

        name = str(item.get("tool") or "").strip().lower()
        name = _ALIASES.get(name, name)
        if name not in _ALLOWED:
            raise LLMPlanError(
                f"call #{index} uses unknown tool '{item.get('tool')}'; "
                f"allowed: {', '.join(sorted(_ALLOWED))}"
            )

        params = item.get("params")
        if not isinstance(params, dict):
            # Alguns modelos põem os parâmetros no mesmo nível do `tool`.
            params = {k: v for k, v in item.items() if k not in {"tool", "note"}}
        if not isinstance(params, dict):
            raise LLMPlanError(f"call #{index} has no params object")

        clean = _clean_params(name, params, brief, index)
        calls.append(
            ToolCall(tool=name, params=clean, note=str(item.get("note") or ""))
        )
    return calls


def _clean_params(
    tool: str, params: dict[str, Any], brief: DrawingBrief, index: int
) -> dict[str, Any]:
    """Valida e normaliza os parâmetros de uma chamada."""
    clean: dict[str, Any] = {}

    for required in _ALLOWED[tool]:
        if required not in params:
            raise LLMPlanError(
                f"call #{index} ({tool}) is missing '{required}'"
            )

    if tool == "draw_pixels":
        points = params.get("points")
        if not isinstance(points, list) or not points:
            raise LLMPlanError(f"call #{index} has an empty `points` list")
        clean["points"] = [
            [
                _coord(point[0], brief.width, f"call #{index} points.x"),
                _coord(point[1], brief.height, f"call #{index} points.y"),
            ]
            for point in points
            if isinstance(point, (list, tuple)) and len(point) >= 2
        ]
        if not clean["points"]:
            raise LLMPlanError(f"call #{index} has no usable points")
    else:
        for key in _ALLOWED[tool]:
            limit = brief.height if key in {"y", "y0", "y1", "y2", "cy", "ry"} else brief.width
            if key in {"radius", "rx", "ry"}:
                clean[key] = max(0, _integer(params[key], f"call #{index} {key}"))
            else:
                clean[key] = _coord(params[key], limit, f"call #{index} {key}")

    if "filled" in params:
        clean["filled"] = bool(params["filled"])

    color = params.get("color") or params.get("colour") or params.get("fill")
    if color is None:
        raise LLMPlanError(f"call #{index} ({tool}) is missing 'color'")
    clean["color"] = _parse_color(color, f"call #{index} color")
    return clean


def _coord(value: Any, limit: int, where: str) -> int:
    """Uma coordenada inteira dentro do canvas.

    Fora da grade é **recusado**, e não recortado: uma coordenada fora
    significa que o modelo entendeu o tamanho errado, e recortar produziria
    uma forma achatada contra a borda que ninguém pediu. Recusar dá ao planner
    a chance de pedir de novo com a crítica.
    """
    number = _integer(value, where)
    if not (0 <= number < limit):
        raise LLMPlanError(
            f"{where}={number} is outside the canvas (valid: 0..{limit - 1})"
        )
    return number


def _integer(value: Any, where: str) -> int:
    if isinstance(value, bool):
        raise LLMPlanError(f"{where} must be a number, not a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise LLMPlanError(f"{where}={value} is fractional; pixels are integers")
        return int(value)
    if isinstance(value, str):
        try:
            return _integer(float(value.strip()), where)
        except ValueError as exc:
            raise LLMPlanError(f"{where}={value!r} is not a number") from exc
    raise LLMPlanError(f"{where} must be a number")


def _parse_color(value: Any, where: str) -> str:
    if isinstance(value, (list, tuple)) and len(value) in (3, 4):
        parts = [max(0, min(255, int(item))) for item in value[:3]]
        return "#%02x%02x%02x" % tuple(parts)
    if not isinstance(value, str):
        raise LLMPlanError(f"{where} must be a hex string like '#a4453a'")
    match = _HEX.match(value.strip())
    if not match:
        raise LLMPlanError(f"{where}={value!r} is not a hex color")
    digits = match.group(1)
    if len(digits) in (3, 4):
        digits = "".join(char * 2 for char in digits)
    if len(digits) not in (6, 8):
        raise LLMPlanError(f"{where}={value!r} is not a hex color")
    return f"#{digits[:6]}"


def _parse_regions(raw: Any) -> dict[str, tuple[int, int, int, int]]:
    """As regiões nomeadas. Opcionais: elas documentam, não desenham."""
    if not isinstance(raw, list):
        return {}
    regions: dict[str, tuple[int, int, int, int]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        bounds = item.get("bounds") or item.get("bbox")
        if not name or not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            continue
        try:
            regions[name] = tuple(int(value) for value in bounds)  # type: ignore[assignment]
        except (TypeError, ValueError):
            continue
    return regions


def _shift(color: str, amount: int) -> str:
    """Clareia ou escurece uma cor — para completar papéis que faltaram."""
    text = color.lstrip("#")
    parts = [int(text[index : index + 2], 16) for index in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, value + amount)) for value in parts
    )
