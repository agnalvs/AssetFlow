"""Vocabulário, classificador e extrator, testados sem subir o sistema.

Os testes de ``test_resolved_spec.py`` provam o comportamento de ponta a
ponta. Estes provam as regras isoladas — é onde se lê *por que* "grass
tileset" é um tileset, sem que a resposta dependa de profile, job ou storage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from assetflow.generation.schemas import AssetType
from assetflow.generation.spec import (
    AssetTaxonomy,
    AssetTypeClassifier,
    Classification,
    ExplicitConstraintExtractor,
    normalize_text,
)

from tests.conftest import BACKEND_ROOT

TAXONOMY_DIR = BACKEND_ROOT / "config" / "asset_taxonomy"


@pytest.fixture(scope="module")
def taxonomy() -> AssetTaxonomy:
    return AssetTaxonomy.from_directory(TAXONOMY_DIR)


@pytest.fixture(scope="module")
def classifier(taxonomy: AssetTaxonomy) -> AssetTypeClassifier:
    return AssetTypeClassifier(taxonomy)


# ---------------------------------------------------------------------------
# Vocabulário
# ---------------------------------------------------------------------------
def test_every_type_file_is_loaded(taxonomy: AssetTaxonomy):
    """Um arquivo torto sumiria em silêncio; este teste conta os tipos."""
    tipos = set(taxonomy.types())

    assert AssetType.PROP in tipos
    assert AssetType.CHARACTER in tipos
    assert AssetType.BACKGROUND in tipos
    assert AssetType.TILESET in tipos
    assert len(taxonomy) == len(list(TAXONOMY_DIR.glob("*.yaml")))


def test_terms_are_normalized(taxonomy: AssetTaxonomy):
    """Acento é decoração de quem escreve, não parte do termo."""
    termos = {term.text for term in taxonomy.terms}

    assert "arvore" in termos
    assert "árvore" not in termos, "o acento tinha de ter sido normalizado na carga"


def test_normalization_strips_punctuation():
    assert normalize_text("Árvore, 32x32!") == "arvore 32x32"


def test_a_missing_directory_degrades_to_silence(tmp_path: Path):
    """Sem vocabulário o AssetFlow não classifica — mas continua gerando."""
    vazia = AssetTaxonomy.from_directory(tmp_path / "nao-existe")

    assert len(vazia) == 0
    assert AssetTypeClassifier(vazia).classify("tree").decided is False


def test_a_broken_file_does_not_take_the_others_down(tmp_path: Path):
    """Configuração torta vira aviso no log, não boot quebrado."""
    (tmp_path / "quebrado.yaml").write_text("type: inexistente\n", encoding="utf-8")
    (tmp_path / "prop.yaml").write_text(
        "type: prop\npriority: 40\nkeywords:\n  en: [tree]\n", encoding="utf-8"
    )

    carregada = AssetTaxonomy.from_directory(tmp_path)

    assert carregada.types() == (AssetType.PROP,)


# ---------------------------------------------------------------------------
# Classificador
# ---------------------------------------------------------------------------
def test_a_marker_beats_a_subject_keyword(classifier: AssetTypeClassifier):
    """A regra central: o termo que nomeia o TIPO ganha do que nomeia o sujeito.

    "grass" é vegetação e "tileset" é um tipo de asset. Sem essa distinção,
    "grass tileset" viraria um prop de grama — e a diferença entre as duas
    respostas é o produto inteiro.
    """
    assert classifier.classify("grass tileset").asset_type is AssetType.TILESET
    assert classifier.classify("grass").asset_type is AssetType.PROP


def test_a_longer_phrase_beats_a_shorter_one(classifier: AssetTypeClassifier):
    """"sala do trono" é um interior; "sala" sozinha nem está no vocabulário."""
    resultado = classifier.classify("sala do trono")

    assert resultado.asset_type is AssetType.BACKGROUND
    assert resultado.matched_term == "sala do trono"


def test_priority_decides_between_equals(classifier: AssetTypeClassifier):
    """"guerreiro na floresta" é um personagem, não uma floresta.

    Os dois termos são keywords de uma palavra. O desempate é a prioridade
    declarada nos arquivos, e ela existe para este caso: um sujeito animado em
    um lugar continua sendo o sujeito.
    """
    assert classifier.classify("guerreiro na floresta").asset_type is AssetType.CHARACTER


def test_a_marker_borrows_the_category_from_the_subject(classifier: AssetTypeClassifier):
    """"forest background" é um cenário — e um cenário de natureza."""
    resultado = classifier.classify("forest background")

    assert resultado.asset_type is AssetType.BACKGROUND
    assert resultado.category == "nature"


def test_partial_words_do_not_match(classifier: AssetTypeClassifier):
    """"treehouse" não contém o asset "tree" — contém as letras dele."""
    assert classifier.classify("treehouse").matched_term != "tree"


def test_the_fallback_is_only_consulted_when_the_rules_are_silent(
    taxonomy: AssetTaxonomy,
):
    """Camada B nunca contradiz a camada A (plano T→J §4).

    A ordem importa: uma regra determinística é reproduzível e auditável; um
    palpite não é. O palpite entra onde não há regra, e só ali.
    """
    consultas: list[str] = []

    class Palpite:
        def classify(self, text: str) -> Classification:
            consultas.append(text)
            return Classification(asset_type=AssetType.UI, layer="fallback")

    classificador = AssetTypeClassifier(taxonomy, fallback=Palpite())

    assert classificador.classify("tree").asset_type is AssetType.PROP
    assert consultas == [], "a regra decidiu; o fallback não devia ter sido chamado"

    resultado = classificador.classify("coisa indescritível")
    assert resultado.asset_type is AssetType.UI
    assert resultado.layer == "fallback"
    assert consultas == ["coisa indescritível"]


# ---------------------------------------------------------------------------
# Extrator de restrições explícitas
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def extractor() -> ExplicitConstraintExtractor:
    return ExplicitConstraintExtractor()


@pytest.mark.parametrize(
    ("texto", "tamanho"),
    [
        ("tree 32x32", (32, 32)),
        ("tree 32 x 32", (32, 32)),
        ("tree 32 × 32", (32, 32)),
        ("tree 64x32", (64, 32)),
        ("tree 128X128", (128, 128)),
    ],
)
def test_size_patterns(extractor: ExplicitConstraintExtractor, texto: str, tamanho):
    restricoes = extractor.extract(texto)

    assert (restricoes.logical_width, restricoes.logical_height) == tamanho
    assert restricoes.subject == "tree"


@pytest.mark.parametrize(
    ("texto", "cores"),
    [
        ("tree 8 colors", 8),
        ("tree 8 colours", 8),
        ("tree 16 cores", 16),
        ("tree 16-color", 16),
        ("tree paleta de 12 cores", 12),
    ],
)
def test_color_patterns(extractor: ExplicitConstraintExtractor, texto: str, cores: int):
    restricoes = extractor.extract(texto)

    assert restricoes.max_colors == cores
    assert restricoes.subject == "tree"


@pytest.mark.parametrize(
    "texto",
    ["tree transparent background", "tree sem fundo", "tree fundo transparente"],
)
def test_transparency_patterns(extractor: ExplicitConstraintExtractor, texto: str):
    assert extractor.extract(texto).background == "transparent"


def test_the_word_background_alone_is_not_a_constraint(
    extractor: ExplicitConstraintExtractor,
):
    """A armadilha inteira em um teste.

    Se "background" sozinho fosse consumido como restrição de fundo, "forest
    background" chegaria ao classificador como "forest" — e um pedido de
    cenário viraria outra coisa.
    """
    restricoes = extractor.extract("forest background")

    assert restricoes.background is None
    assert restricoes.subject == "forest background"


def test_view_patterns(extractor: ExplicitConstraintExtractor):
    assert extractor.extract("knight, vista lateral").view == "side"
    assert extractor.extract("village, top-down").view == "top_down"
    assert extractor.extract("knight").view is None


def test_the_subject_survives_the_extraction_intact(
    extractor: ExplicitConstraintExtractor,
):
    """O exemplo do plano T→J §25, incluindo a limpeza da pontuação órfã.

    O sujeito vai inteiro para o motor. "tree , , " faria o modelo desenhar
    vírgulas — ou pior, o próprio texto.
    """
    restricoes = extractor.extract("tree 32x32, 8 colors, transparent background")

    assert restricoes.subject == "tree"
    assert restricoes.logical_width == 32
    assert restricoes.max_colors == 8
    assert restricoes.background == "transparent"
    assert len(restricoes.matched) == 3


def test_a_plain_description_is_left_alone(extractor: ExplicitConstraintExtractor):
    """Sem restrição escrita, o extrator não inventa nem corta nada."""
    frase = "cavaleiro medieval com armadura azul"
    restricoes = extractor.extract(frase)

    assert restricoes.subject == frase
    assert restricoes.matched == ()
    assert restricoes.logical_width is None
    assert restricoes.max_colors is None
    assert restricoes.background is None
