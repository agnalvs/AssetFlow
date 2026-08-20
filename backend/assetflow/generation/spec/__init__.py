"""Resolução de especificação — do texto ao contrato (plano Text→JSON).

Este pacote é o caminho inteiro entre a frase que a pessoa escreve e o objeto
que o motor recebe::

    Texto do usuário
        -> ExplicitConstraintExtractor   restrições exatas ("32x32", "8 cores")
        -> AssetTypeClassifier           taxonomia: árvore é prop, não personagem
        -> ConstraintResolver            precedência oficial, camada por camada
        -> FinalResolvedSpec             contrato imutável do job

Ele resolve os dois defeitos que motivaram o plano:

* **"tree" virava personagem.** O tipo vinha do profile, e o profile vem do
  modo escolhido na tela — que só conhece "Pixel Art" e "2D Normal". Agora o
  sujeito é classificado por um vocabulário próprio
  (``config/asset_taxonomy/``), e o profile só responde quando ninguém mais
  sabe.
* **32×32 virava 64×64.** Não havia ordem de precedência; havia camadas
  perguntando ao profile em momentos diferentes. Agora existe uma ordem só,
  escrita em ``SPEC_PRECEDENCE``, e um objeto imutável que a carrega até o
  fim do job.

Os *contratos* (``FinalResolvedSpec`` e companhia) moram em
``generation/schemas/``, porque são linguagem comum de API, job, pipeline e
storage. Aqui mora a *lógica* — que pode conhecer profile sem contaminar os
contratos.
"""

from .classifier import AssetTypeClassifier, Classification, ClassifierFallback
from .constraints import ExplicitConstraintExtractor, ExplicitConstraints
from .resolver import ConstraintResolver, SpecResolution
from .taxonomy import AssetTaxonomy, TaxonomyEntry, TaxonomyTerm, normalize_text

__all__ = [
    "AssetTaxonomy",
    "AssetTypeClassifier",
    "Classification",
    "ClassifierFallback",
    "ConstraintResolver",
    "ExplicitConstraintExtractor",
    "ExplicitConstraints",
    "SpecResolution",
    "TaxonomyEntry",
    "TaxonomyTerm",
    "normalize_text",
]
