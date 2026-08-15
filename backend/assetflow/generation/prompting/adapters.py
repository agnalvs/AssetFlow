"""Adapters de prompt (planos §27 e §28).

O :class:`SemanticPrompt` é a fonte da verdade e é independente de motor.
Cada tecnologia, porém, responde melhor a um formato de texto diferente.

    SemanticPrompt -> GenericTextPromptAdapter -> texto neutro (padrão)
    SemanticPrompt -> <adapter da gaveta>      -> texto ideal daquele motor

O adapter genérico vive aqui, no AssetFlow. Adapters específicos vivem
**dentro da pasta da gaveta** e são expostos por
``ImageGenerationEngine.prompt_adapter()`` — assim o conhecimento sobre o
formato de um modelo some junto com o modelo.
"""

from __future__ import annotations

from ..schemas import SemanticPrompt

__all__ = ["GenericTextPromptAdapter", "render_semantic_prompt"]


class GenericTextPromptAdapter:
    """Renderiza a semântica em texto neutro, aceito por qualquer motor."""

    id = "generic"

    def render(self, semantic: SemanticPrompt) -> tuple[str, str | None]:
        return render_semantic_prompt(semantic)


def render_semantic_prompt(semantic: SemanticPrompt) -> tuple[str, str | None]:
    """Converte :class:`SemanticPrompt` em ``(positive, negative)``.

    Deliberadamente conservador: sem "truques" de nenhum modelo específico
    (pesos entre parênteses, tokens de qualidade, sintaxe de embeddings).
    Esses truques pertencem ao adapter da gaveta que os entende.
    """
    positive: list[str] = []

    medium = semantic.medium.replace("_", " ").strip()
    if medium:
        positive.append(medium)

    positive.extend(semantic.descriptors())

    composition = semantic.composition
    if composition.single_subject:
        positive.append("single subject")
    if composition.centered:
        positive.append("centered composition")
    if composition.full_body:
        positive.append("full body")
    if composition.isolated_background:
        positive.append("isolated on plain background")

    technical = semantic.technical
    if technical.clean_silhouette:
        positive.append("clean readable silhouette")
    if technical.sharp_edges:
        positive.append("sharp crisp edges")
    if technical.limited_palette:
        positive.append(f"limited palette of {technical.limited_palette} colors")
    if technical.transparent_background:
        positive.append("transparent background")

    negative_terms = list(semantic.avoid)
    if technical.no_text:
        negative_terms.append("text")
    if technical.no_watermark:
        negative_terms.append("watermark")

    positive_text = ", ".join(dict.fromkeys(term for term in positive if term))
    negative_text = ", ".join(dict.fromkeys(term for term in negative_terms if term))
    return positive_text, (negative_text or None)
