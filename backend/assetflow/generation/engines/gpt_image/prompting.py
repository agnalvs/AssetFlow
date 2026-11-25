"""O compilador de prompt do GPT Image.

A regra que este arquivo existe para respeitar: **o `FinalResolvedSpec` não é
um prompt**. Ele é o contrato do asset; o prompt é uma tentativa de obtê-lo de
um modelo que não conhece o AssetFlow. Mandar o JSON do spec para o modelo
seria confundir as duas coisas — e o dia em que o spec ganhasse um campo novo,
o prompt mudaria sozinho, sem ninguém decidir isso.

O que o compilador precisa conseguir
------------------------------------
O GPT Image vai gerar em ~832×832 uma imagem que o AssetFlow reduzirá para
32×32. O que decide se essa redução dá certo **não é o realismo da imagem**,
é a estrutura dela:

* áreas de cor **chapadas e grandes**, sem gradiente;
* bordas **duras**, sem anti-aliasing e sem sombra difusa;
* silhueta legível, com o sujeito inteiro dentro do quadro e com margem;
* fundo limpo, para o recorte não trazer lixo junto.

Uma ilustração linda com degradês suaves vira uma mancha em 32×32. Uma
ilustração mais pobre, com massas chapadas, vira um sprite. O prompt inteiro é
construído em torno disso.

O orçamento semântico (o "PromptBudgetPlanner")
-----------------------------------------------
Um grid de 16×16 não comporta a mesma densidade de descrição que um de 96×96 —
"cicatriz no olho" simplesmente não cabe em 256 pixels. O spec continua
completo; quem reduz a densidade é só o compilador, aqui, e ele o faz pedindo
**silhueta** onde não cabe **detalhe**.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["CompiledPrompt", "DetailBudget", "budget_for", "compile_prompt"]


@dataclass(frozen=True, slots=True)
class DetailBudget:
    """Quanta descrição cabe neste grid."""

    name: str
    #: Instrução que substitui detalhe por leitura de forma.
    guidance: str


#: Faixas por lado do grid lógico. Os cortes são de produto, não do provedor:
#: abaixo de 24px um rosto é três pixels, e pedir traços ali produz ruído.
_BUDGETS: tuple[tuple[int, DetailBudget], ...] = (
    (
        24,
        DetailBudget(
            "silhouette",
            "Extremely limited space: prioritize a bold, instantly readable "
            "silhouette over any small detail. Omit facial features and fine "
            "ornaments entirely.",
        ),
    ),
    (
        48,
        DetailBudget(
            "compact",
            "Limited space: keep only the few details that identify the "
            "subject. Simplify or omit small ornaments.",
        ),
    ),
    (
        96,
        DetailBudget(
            "standard",
            "Moderate space: include the defining details, but keep each one "
            "as a distinct block of colour rather than fine texture.",
        ),
    ),
)

_GENEROUS = DetailBudget(
    "detailed",
    "Enough space for rich detail, as long as every detail stays a crisp "
    "shape with hard edges.",
)


def budget_for(logical: tuple[int, int] | None) -> DetailBudget:
    """O orçamento de detalhe deste grid."""
    if logical is None:
        return _GENEROUS
    side = min(logical)
    for limit, budget in _BUDGETS:
        if side < limit:
            return budget
    return _GENEROUS


@dataclass(slots=True)
class CompiledPrompt:
    """O que efetivamente vai para o provedor."""

    text: str
    #: O que o AssetFlow pediu e este motor **não** sabe honrar. Sobe como
    #: aviso do job: uma capacidade ausente precisa aparecer, nunca sumir.
    warnings: list[str] = field(default_factory=list)
    #: Para `engine_output.json` — é o texto real que gerou o asset.
    budget: str = "detailed"


def compile_prompt(
    *,
    positive: str,
    negative: str | None,
    subject: str,
    asset_type: str,
    is_pixel: bool,
    logical: tuple[int, int] | None,
    max_colors: int | None,
    transparent: bool,
    view: str | None,
    seed_requested: bool,
    body_type: str = "unknown",
    detail: str = "auto",
    outline: str = "auto",
    shading: str = "auto",
    light_direction: str | None = None,
    reference_count: int = 0,
) -> CompiledPrompt:
    """Traduz o pedido do AssetFlow para uma instrução ao GPT Image.

    Os campos de estilo chegam como texto, e ``auto`` significa "ninguém
    opinou" — nesses casos o compilador **não diz nada** sobre o assunto, em
    vez de mandar um padrão. Um prompt que sempre pede "contorno seletivo"
    tira do modelo uma decisão que ninguém pediu para tirar.
    """
    warnings: list[str] = []
    budget = budget_for(logical)
    parts: list[str] = []

    if not is_pixel:
        # Arte 2D convencional: o motor é bom nisso sozinho, e encher o prompt
        # de regras de pixel art estragaria o resultado.
        parts.append(positive.strip())
        if negative:
            parts.append(f"Avoid: {negative.strip()}.")
            warnings.append(
                "o GPT Image não aceita negative prompt; ele foi incorporado "
                "ao texto como 'Avoid:'"
            )
        if seed_requested:
            warnings.append(_SEED_WARNING)
        return CompiledPrompt("\n\n".join(parts), warnings, budget.name)

    grid = f"{logical[0]}×{logical[1]}" if logical else "small"
    corpo = _BODY_PHRASES.get(body_type)
    alvo = subject or positive.strip()
    # A topologia entra como aposto, e não como substantivo da frase: sem
    # isso, "four-legged animal, standing on all fours in profile game sprite"
    # sai agramatical, e um prompt confuso confunde o modelo.
    parts.append(
        f"A single {asset_type} game sprite in pixel art style: {alvo}"
        + (f" — {corpo}." if corpo else ".")
    )
    parts.append(
        "This artwork will be downscaled to a "
        f"{grid} pixel grid, so it must be built from large, flat blocks of "
        "colour. Hard edges only. No gradients, no soft shading, no "
        "anti-aliasing, no blur, no texture noise, no glow."
    )
    parts.append(budget.guidance)

    # Detalhe pedido explicitamente refina o orçamento; ele não o substitui.
    # O orçamento é sobre o que **cabe** em 32×32; o detalhe é sobre o quanto
    # se quer. Pedir "alto detalhe" em 16×16 continua sendo silhueta.
    if detail in _DETAIL_PHRASES:
        parts.append(_DETAIL_PHRASES[detail])

    if outline in _OUTLINE_PHRASES:
        parts.append(_OUTLINE_PHRASES[outline])

    if shading in _SHADING_PHRASES:
        frase = _SHADING_PHRASES[shading]
        if light_direction and shading != "flat":
            frase = f"{frase} Light comes from the {light_direction.replace('_', ' ')}."
        parts.append(frase)

    if max_colors:
        parts.append(
            f"Use a very limited palette of about {max_colors} flat colours, "
            "with strong value contrast between neighbouring areas."
        )

    if transparent:
        parts.append(
            "The background must be fully transparent and completely empty — "
            "no ground, no shadow, no scenery, no frame."
        )
    else:
        parts.append("Plain, flat, uniform background.")

    parts.append(
        "The subject is centred, complete, and fully inside the frame, with a "
        "small empty margin on every side. No perspective distortion, no "
        "cropping."
    )

    # A câmera é dita **uma vez**. A versão anterior pedia "straight-on
    # orthographic view" e, três linhas depois, "low top-down, 20 degrees" —
    # duas ordens opostas no mesmo prompt, e o modelo escolhendo qual ignorar.
    if view:
        parts.append(f"Camera: {_view_phrase(view)}.")
    else:
        parts.append("Camera: straight-on orthographic view.")

    if negative:
        parts.append(f"Avoid: {negative.strip()}.")
        warnings.append(
            "o GPT Image não aceita negative prompt; ele foi incorporado ao "
            "texto como 'Avoid:'"
        )

    # Estes dois não são preferência: são os erros que a redução não perdoa.
    parts.append(
        "Do not draw a sprite sheet, multiple poses, grids, labels, borders or "
        "text of any kind. Exactly one subject."
    )

    if seed_requested:
        warnings.append(_SEED_WARNING)
    if reference_count:
        warnings.append(_reference_warning(reference_count))

    return CompiledPrompt("\n\n".join(parts), warnings, budget.name)


def _reference_warning(count: int) -> str:
    plural = "imagem de referência" if count == 1 else "imagens de referência"
    return (
        f"esta gaveta ainda não envia {plural} ao provedor: {count} foram "
        "ignoradas. A API tem endpoint de edição com referências — ele não "
        "está ligado aqui ainda."
    )


_SEED_WARNING = (
    "o GPT Image não aceita seed: esta geração não é reprodutível, e repetir o "
    "mesmo pedido produzirá outra imagem"
)


#: Topologia corporal -> como descrevê-la ao modelo.
#:
#: `unknown` **não** está aqui de propósito: sem informação, o compilador cai
#: em `asset_type` e deixa o modelo decidir. Chutar "humanoid" faria um lobo
#: nascer em pé — é exatamente o erro que o campo existe para evitar.
_BODY_PHRASES = {
    "humanoid": "humanoid character",
    "quadruped": "four-legged animal, standing on all fours in profile",
    "avian": "bird",
    "aquatic": "fish or sea creature",
    "serpentine": "long-bodied serpentine creature",
    "amorphous": "soft amorphous blob-like creature with no limbs",
}

_DETAIL_PHRASES = {
    "low": "Keep it very simple: few shapes, no small ornaments.",
    "medium": "Moderate amount of detail.",
    "high": (
        "Pack in as much readable detail as the grid allows, without ever "
        "softening an edge."
    ),
}

_OUTLINE_PHRASES = {
    "none": "No outline at all: shapes are separated by colour alone.",
    "black": "A solid black outline of uniform width around the whole silhouette.",
    "single_color": "A single dark outline colour around the whole silhouette.",
    "selective": (
        "Selective outlining: outline the silhouette, but let interior shapes "
        "be separated by colour contrast instead of lines."
    ),
    "adaptive_dark": (
        "Outline in a darker shade of each adjacent colour rather than a "
        "single flat black."
    ),
}

_SHADING_PHRASES = {
    "flat": "Completely flat colour: no shading at all, one tone per area.",
    "basic": "Simple two-tone shading: one base colour and one shadow tone.",
    "medium": "Moderate shading with a base tone, a shadow and a highlight.",
    "detailed": (
        "Rich shading with several tones per area — still as hard-edged "
        "blocks, never a gradient."
    ),
}

_VIEWS = {
    "side": "straight side view, perfectly horizontal eye level",
    "front": "straight front view, facing the viewer",
    "back": "straight back view, facing away from the viewer",
    "top_down": "top-down view, seen from directly above",
    "high_top_down": "high top-down view, roughly 35 degrees above the subject",
    "low_top_down": "low top-down view, roughly 20 degrees above the subject",
    "isometric": "isometric view at a 45 degree angle",
    "three_quarter": "three-quarter view",
}


def _view_phrase(view: str) -> str:
    """A vista, em linguagem que o modelo entende.

    O spec guarda `low_top_down` — uma verdade sobre o asset pedido. Isto aqui
    é só a tentativa de obtê-la. A documentação do PixelLab é explícita em
    chamar controle de câmera de *guidance fraca*: o modelo pode não obedecer,
    e quem confere depois é o validador, não este texto.
    """
    return _VIEWS.get(view.strip().lower(), view.replace("_", " "))
