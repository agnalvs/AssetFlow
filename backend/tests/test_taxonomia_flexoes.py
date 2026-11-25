"""As formas de cada palavra do vocabulário de personagem.

O classificador casa a palavra inteira e não flexiona: "arqueira" não casa
"arqueiro", e "arqueiras" não casa nenhum dos dois. Forma que não está escrita
no ``character.yaml`` não existe para ele — e foi assim que "arqueira" ficou
fora de ``body_types`` enquanto "arqueiro" estava lá, e o recorte do MCP saiu
sem proporções para uma arqueira.

Estes testes leem o YAML cru, lista por lista (cada categoria e cada forma de
corpo é uma lista à parte), e conferem três coisas:

* toda forma masculina tem, na mesma lista, a feminina — quando ela existe —
  e os plurais das duas;
* toda palavra masculina do jeito regular (terminada em -o ou -ão) está
  classificada aqui: tem par em :data:`FLEXOES` ou motivo em
  :data:`SEM_FEMININO`. É o que impede a próxima palavra de entrar sem
  feminino sem ninguém perceber;
* todo termo de ``categories`` é um sujeito que o classificador enxerga.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest
import yaml

from assetflow.generation.spec import AssetTaxonomy, normalize_text
from tests.conftest import BACKEND_ROOT

ARQUIVO = BACKEND_ROOT / "config" / "asset_taxonomy" / "character.yaml"

#: Masculino, feminino, plural masculino, plural feminino. Numa lista do
#: vocabulário, ou a palavra está com as quatro formas, ou não está.
FLEXOES: tuple[tuple[str, str, str, str], ...] = (
    ("guerreiro", "guerreira", "guerreiros", "guerreiras"),
    ("cavaleiro", "cavaleira", "cavaleiros", "cavaleiras"),
    ("mago", "maga", "magos", "magas"),
    ("bruxo", "bruxa", "bruxos", "bruxas"),
    ("feiticeiro", "feiticeira", "feiticeiros", "feiticeiras"),
    ("arqueiro", "arqueira", "arqueiros", "arqueiras"),
    ("ladino", "ladina", "ladinos", "ladinas"),
    ("ladrão", "ladra", "ladrões", "ladras"),
    ("assassino", "assassina", "assassinos", "assassinas"),
    ("paladino", "paladina", "paladinos", "paladinas"),
    ("bardo", "barda", "bardos", "bardas"),
    ("monge", "monja", "monges", "monjas"),
    ("rei", "rainha", "reis", "rainhas"),
    ("príncipe", "princesa", "príncipes", "princesas"),
    ("aldeão", "aldeã", "aldeões", "aldeãs"),
    ("mercador", "mercadora", "mercadores", "mercadoras"),
    ("ferreiro", "ferreira", "ferreiros", "ferreiras"),
    ("fazendeiro", "fazendeira", "fazendeiros", "fazendeiras"),
    ("homem", "mulher", "homens", "mulheres"),
    ("menino", "menina", "meninos", "meninas"),
    ("inimigo", "inimiga", "inimigos", "inimigas"),
    ("ogro", "ogra", "ogros", "ogras"),
    ("dragão", "dragoa", "dragões", "dragoas"),
    ("demônio", "demônia", "demônios", "demônias"),
    ("elfo", "elfa", "elfos", "elfas"),
    ("vampiro", "vampira", "vampiros", "vampiras"),
    ("gato", "gata", "gatos", "gatas"),
    ("cachorro", "cachorra", "cachorros", "cachorras"),
    ("lobo", "loba", "lobos", "lobas"),
    ("cavalo", "égua", "cavalos", "éguas"),
    ("cão", "cadela", "cães", "cadelas"),
    ("urso", "ursa", "ursos", "ursas"),
    ("leão", "leoa", "leões", "leoas"),
    ("tigre", "tigresa", "tigres", "tigresas"),
    ("cervo", "corça", "cervos", "corças"),
    ("rato", "rata", "ratos", "ratas"),
    ("aquático", "aquática", "aquáticos", "aquáticas"),
    ("amorfo", "amorfa", "amorfos", "amorfas"),
    ("king", "queen", "kings", "queens"),
    ("prince", "princess", "princes", "princesses"),
    ("man", "woman", "men", "women"),
    ("boy", "girl", "boys", "girls"),
    ("sorcerer", "sorceress", "sorcerers", "sorceresses"),
)

#: Masculinos regulares que ficam sem feminino no vocabulário, e por quê.
SEM_FEMININO: Mapping[str, str] = {
    # Normalizada, "anã" vira "ana": "Ana segurando uma espada" passaria a ser
    # um personagem anão, e uma poção "da Ana", um personagem.
    "anão": "sem acento 'anã' vira 'ana' e casaria com o nome Ana",
    "soldado": "'soldada' é também particípio de soldar ('chapa soldada')",
    "porco": "'porca' é também a peça que se rosqueia no parafuso",
    "pato": "'pata' é também o pé do animal ('pata de lobo')",
    "veado": "a forma feminina é usada como ofensa",
    "serpentino": "'serpentina' é também a fita de papel de festa",
    "chefão": "sem feminino de uso corrente",
    "monstro": "substantivo sem flexão de gênero",
    "esqueleto": "substantivo sem flexão de gênero",
    "pássaro": "substantivo sem flexão de gênero",
    "corvo": "substantivo sem flexão de gênero",
    "polvo": "substantivo sem flexão de gênero",
    "caranguejo": "substantivo sem flexão de gênero",
    "morcego": "substantivo sem flexão de gênero",
    "tubarão": "substantivo sem flexão de gênero",
    "espírito": "substantivo sem flexão de gênero",
    "robô": "substantivo sem flexão de gênero",
}


def _formas(valores: Any) -> Iterator[str]:
    """Lista do YAML, com sublistas, para termos soltos."""
    if isinstance(valores, Mapping):
        for item in valores.values():
            yield from _formas(item)
    elif isinstance(valores, list):
        for item in valores:
            yield from _formas(item)
    elif isinstance(valores, str):
        yield valores


@pytest.fixture(scope="module")
def vocabulario() -> dict[str, Any]:
    with ARQUIVO.open(encoding="utf-8") as arquivo:
        return yaml.safe_load(arquivo)


@pytest.fixture(scope="module")
def listas(vocabulario: dict[str, Any]) -> dict[str, set[str]]:
    """Cada lista em que uma palavra pode estar, já normalizada."""
    resultado = {"keywords": {normalize_text(t) for t in _formas(vocabulario["keywords"])}}
    for secao in ("categories", "body_types"):
        for nome, valores in vocabulario[secao].items():
            resultado[f"{secao}.{nome}"] = {normalize_text(t) for t in _formas(valores)}
    return resultado


def test_cada_palavra_vem_com_feminino_e_plurais(listas: dict[str, set[str]]):
    """A arqueira que ficou sem corpo: "arqueiro" estava em `body_types`, e ela não."""
    faltas = []
    for lista, termos in listas.items():
        for flexao in FLEXOES:
            formas = [normalize_text(forma) for forma in flexao]
            presentes = [forma for forma in formas if forma in termos]
            if presentes and len(presentes) < len(formas):
                ausentes = [forma for forma in formas if forma not in termos]
                faltas.append(f"{lista}: tem {presentes[0]!r} e falta {', '.join(ausentes)}")

    assert not faltas, "formas faltando no character.yaml:\n" + "\n".join(faltas)


def test_todo_masculino_regular_esta_classificado(listas: dict[str, set[str]]):
    """A próxima palavra em -o ou -ão não entra sem alguém decidir o feminino.

    A guarda é morfológica e pega só o padrão regular. Palavra em -or
    ("caçador") escapa, porque o inglês "warrior" também termina assim: essas
    dependem de quem a acrescenta pôr o par em FLEXOES.
    """
    conhecidos = {normalize_text(flexao[0]) for flexao in FLEXOES}
    conhecidos |= {normalize_text(termo) for termo in SEM_FEMININO}
    soltos = sorted(
        termo
        for termos in listas.values()
        for termo in termos
        if " " not in termo and termo.endswith("o") and termo not in conhecidos
    )

    assert not soltos, (
        "masculino sem decisão de feminino: acrescente as formas ao character.yaml "
        "e a FLEXOES, ou o motivo a SEM_FEMININO — " + ", ".join(soltos)
    )


def test_ana_fica_fora_do_vocabulario(listas: dict[str, set[str]]):
    """"anã" ficou de fora de propósito: o motivo está em SEM_FEMININO."""
    assert all("ana" not in termos for termos in listas.values()), SEM_FEMININO["anão"]


def test_todo_termo_de_categoria_e_um_sujeito(vocabulario: dict[str, Any]):
    """Um termo só em `categories` nunca casa: o classificador lê `keywords` e
    `body_types`. Feminino posto só na categoria seria configuração morta."""
    sujeitos = {normalize_text(t) for t in _formas(vocabulario["keywords"])}
    sujeitos |= {normalize_text(t) for t in _formas(vocabulario["body_types"])}
    mortos = sorted(
        normalize_text(termo)
        for termo in _formas(vocabulario["categories"])
        if normalize_text(termo) not in sujeitos
    )

    assert not mortos, "termos de categories que o classificador não enxerga: " + ", ".join(mortos)


def test_categoria_com_corpo_nao_contradiz_nenhum_membro():
    """`category_body_types` só lista categoria em que todo membro tem aquele
    corpo: nenhum termo dela pode nomear outro."""
    taxonomia = AssetTaxonomy.from_directory(ARQUIVO.parent)
    (personagem,) = [e for e in taxonomia.entries if e.asset_type.value == "character"]

    assert dict(personagem.category_body_types) == {"humanoid": "humanoid"}
    contrarios = sorted(
        f"{termo.text} ({termo.body_type})"
        for termo in personagem.terms
        if termo.category in personagem.category_body_types
        and termo.body_type not in (None, personagem.category_body_types[termo.category])
    )
    assert not contrarios, "membros com outro corpo: " + ", ".join(contrarios)
