"""AssetTypeClassifier — que tipo de asset é este pedido (plano T→J §4).

O bug que este módulo existe para matar: `tree` virava
``{"asset_type": "character"}``. Não porque alguém tenha decidido que árvore é
personagem, mas porque **ninguém decidia nada** — o tipo vinha do profile
escolhido pela interface, e a interface só conhece "Pixel Art" e "2D Normal".
O sujeito do pedido nunca era olhado.

Classificação em camadas (plano T→J §4 e §22)::

    Camada A   regras determinísticas   vocabulário em config/asset_taxonomy/
    Camada B   fallback                 só para o que a camada A não resolveu

A camada A resolve a esmagadora maioria dos pedidos reais e resolve sempre
igual — mesma frase, mesmo tipo, sem depender de rede, modelo ou humor do
gerador. A camada B é um ponto de extensão declarado
(:class:`ClassifierFallback`): hoje o AssetFlow não tem intérprete de
linguagem natural, e o resolver trata "não sei" como "não opine" — o profile
segue respondendo. Quando existir um, ele entra por aqui e continua **abaixo**
de qualquer restrição explícita na precedência.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..schemas import AssetType
from .taxonomy import AssetTaxonomy, TaxonomyTerm, normalize_text

__all__ = ["AssetTypeClassifier", "Classification", "ClassifierFallback"]


@dataclass(frozen=True, slots=True)
class Classification:
    """O veredito do classificador.

    ``asset_type`` é ``None`` quando nada casou. É um resultado legítimo e
    frequente — "algo bonito e azul" não diz o tipo — e é tratado como
    silêncio, não como palpite: o resolver simplesmente mantém o valor do
    profile (plano T→J §23).
    """

    asset_type: AssetType | None = None
    category: str | None = None
    #: O termo do vocabulário que decidiu, já normalizado. Vai para o trace.
    matched_term: str | None = None
    #: ``rule`` = camada A; ``fallback`` = camada B; ``none`` = ninguém.
    layer: str = "none"

    @property
    def decided(self) -> bool:
        return self.asset_type is not None


@runtime_checkable
class ClassifierFallback(Protocol):
    """Camada B: só é consultada quando as regras não decidiram."""

    def classify(self, text: str) -> Classification:  # pragma: no cover - protocolo
        ...


class AssetTypeClassifier:
    """Decide o tipo de asset a partir do texto do pedido."""

    def __init__(
        self,
        taxonomy: AssetTaxonomy | None = None,
        fallback: ClassifierFallback | None = None,
    ) -> None:
        self._taxonomy = taxonomy or AssetTaxonomy.empty()
        self._fallback = fallback

    @property
    def taxonomy(self) -> AssetTaxonomy:
        return self._taxonomy

    def classify(self, text: str) -> Classification:
        """Classifica o texto — de preferência já sem as restrições numéricas.

        Quem chama passa o sujeito limpo pelo
        :class:`~.constraints.ExplicitConstraintExtractor`. Isso não é
        detalhe de ordem: "tree, transparent background" contém a palavra
        *background*, e classificar antes de extrair transformaria uma árvore
        em cenário.
        """
        normalized = normalize_text(text)
        if not normalized:
            return Classification()

        candidates = self._candidates(normalized)
        if candidates:
            best = max(candidates, key=_strength)
            return Classification(
                asset_type=best.asset_type,
                category=best.category or _category_from(candidates, best),
                matched_term=best.text,
                layer="rule",
            )

        if self._fallback is not None:
            result = self._fallback.classify(text)
            if result.decided:
                return Classification(
                    asset_type=result.asset_type,
                    category=result.category,
                    matched_term=result.matched_term,
                    layer="fallback",
                )

        return Classification()

    # ------------------------------------------------------------------
    def _candidates(self, normalized: str) -> list[TaxonomyTerm]:
        """Todos os termos do vocabulário presentes no texto."""
        padded = f" {normalized} "
        return [term for term in self._taxonomy.terms if f" {term.text} " in padded]


def _strength(term: TaxonomyTerm) -> tuple[bool, int, int, int]:
    """Ordem de força de um termo, e cada critério tem um caso concreto:

    1. **marker antes de keyword** — "grass tileset" é um tileset, não uma
       vegetação;
    2. **frase longa antes de curta** — "sala do trono" ganha de "sala";
    3. **prioridade do tipo** — "guerreiro na floresta" é um personagem em uma
       floresta, e não uma floresta com um guerreiro dentro.
    """
    return (term.marker, term.words, term.priority, len(term.text))


def _category_from(
    candidates: list[TaxonomyTerm], best: TaxonomyTerm
) -> str | None:
    """Categoria emprestada de um sujeito do mesmo tipo.

    Markers nomeiam o tipo e raramente têm categoria: "background" é
    `background`, mas não diz se é natureza ou cidade. Quando o texto também
    traz um sujeito daquele tipo — "forest background" —, é ele quem responde.
    """
    mesmo_tipo = [
        term
        for term in candidates
        if term.asset_type is best.asset_type and term.category and term is not best
    ]
    if not mesmo_tipo:
        return None
    return max(mesmo_tipo, key=_strength).category
