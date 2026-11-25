"""A receita de desenho: o que o Claude envia, validado antes de virar pixel.

A receita é **o** pedido desta gaveta. Ela chega em
``engine_options["desenhista-v1"]["receita"]`` e descreve o sprite em camadas:

.. code-block:: json

    {
      "grade": [16, 16],
      "paleta": {"k": "#2d3436", "v": "#a8d8e8"},
      "camadas": [
        {"nome": "silhueta", "espelho": "x", "ops": [
          {"elipse": [3, 5, 10, 10], "cor": "k"},
          {"ret": [6, 2, 2, 4], "cor": "k"}
        ]},
        {"nome": "brilho", "ops": [{"px": ["v.", ".v"], "em": [5, 7]}]}
      ]
    }

Quem lê uma mensagem de erro daqui é o Claude, que corrige a receita e manda
de novo. Por isso **nada é corrigido em silêncio** e toda mensagem diz onde
está o problema (``camadas[1] ('vidro').ops[0]``) e o que era esperado. Uma
chave desconhecida também é erro: ``"camada"`` no lugar de ``"camadas"``
viraria um sprite vazio sem que ninguém soubesse por quê.

Este módulo só entende o **formato**. O que depende da grade do pedido —
operação fora dela, ``grade`` divergente, cores além do limite — é conferido
no rasterizador e na gaveta, que conhecem o pedido.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ESPELHOS",
    "FORMAS",
    "RESERVADOS",
    "Camada",
    "Operacao",
    "Receita",
    "ReceitaInvalida",
    "ler_receita",
]

RGB = tuple[int, int, int]

#: Caracteres de ``px`` que não são cor: ``.`` mantém o que está embaixo e
#: ``-`` apaga (deixa transparente). Nenhuma chave de paleta pode usá-los.
MANTER = "."
APAGAR = "-"
RESERVADOS = frozenset({MANTER, APAGAR, " "})

#: As operações, com o número de inteiros que cada uma recebe.
FORMAS = ("ret", "elipse", "linha", "poligono", "balde", "px")

#: Eixos aceitos no campo ``espelho`` de uma camada.
ESPELHOS = ("x", "y", "xy")

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_CHAVES_RAIZ = frozenset({"grade", "paleta", "camadas"})
_CHAVES_CAMADA = frozenset({"nome", "espelho", "ops"})
#: Campos que cada forma aceita além da própria chave.
_EXTRAS = {
    "ret": frozenset({"cor", "contorno"}),
    "elipse": frozenset({"cor", "contorno"}),
    "poligono": frozenset({"cor", "contorno"}),
    "linha": frozenset({"cor"}),
    "balde": frozenset({"cor"}),
    "px": frozenset({"em"}),
}


class ReceitaInvalida(ValueError):
    """A receita não pode ser desenhada; a mensagem diz por quê, em português."""


@dataclass(frozen=True, slots=True)
class Operacao:
    """Uma operação de desenho já validada no formato."""

    forma: str
    #: Os inteiros da forma: ``[x, y, largura, altura]`` para ``ret`` e
    #: ``elipse``, pontos achatados para ``linha`` e ``poligono``, ``[x, y]``
    #: para ``balde``. Vazio para ``px``.
    numeros: tuple[int, ...] = ()
    #: Chave da paleta. ``None`` só em ``px``, que traz as cores nas linhas.
    cor: str | None = None
    contorno: bool = False
    #: Linhas de ``px``, uma string por linha da grade.
    linhas: tuple[str, ...] = ()
    #: Canto superior esquerdo de ``px``.
    em: tuple[int, int] = (0, 0)
    #: Onde a operação está na receita, para as mensagens: ``camadas[1] ('vidro').ops[0]``.
    caminho: str = ""


@dataclass(frozen=True, slots=True)
class Camada:
    nome: str
    ops: tuple[Operacao, ...]
    espelho: str | None = None


@dataclass(frozen=True, slots=True)
class Receita:
    paleta: dict[str, RGB]
    camadas: tuple[Camada, ...]
    #: Tamanho para o qual a receita foi desenhada, quando ela declara. Só
    #: serve para conferir: quem manda no tamanho é o pedido.
    grade: tuple[int, int] | None = None


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def ler_receita(bruta: Any) -> Receita:
    """Valida o formato e devolve a receita pronta para o rasterizador.

    Raises:
        ReceitaInvalida: com a primeira coisa errada, dita em português.
    """
    if not isinstance(bruta, dict):
        raise ReceitaInvalida(
            f"a receita precisa ser um objeto JSON, e chegou {_tipo(bruta)}"
        )
    _sem_chaves_estranhas(bruta, _CHAVES_RAIZ, "a receita")

    paleta = _ler_paleta(bruta.get("paleta"))
    grade = _ler_grade(bruta.get("grade")) if "grade" in bruta else None

    camadas_brutas = bruta.get("camadas")
    if not isinstance(camadas_brutas, list) or not camadas_brutas:
        raise ReceitaInvalida(
            "a receita precisa de 'camadas': uma lista com pelo menos uma camada"
        )

    camadas: list[Camada] = []
    nomes: set[str] = set()
    for indice, camada_bruta in enumerate(camadas_brutas):
        camada = _ler_camada(camada_bruta, indice, paleta)
        if camada.nome in nomes:
            raise ReceitaInvalida(
                f"camadas[{indice}]: o nome '{camada.nome}' já foi usado por outra "
                "camada — cada camada precisa de um nome único"
            )
        nomes.add(camada.nome)
        camadas.append(camada)

    return Receita(paleta=paleta, camadas=tuple(camadas), grade=grade)


def _ler_paleta(bruta: Any) -> dict[str, RGB]:
    if not isinstance(bruta, dict) or not bruta:
        raise ReceitaInvalida(
            "a receita precisa de 'paleta': um objeto de chave de um caractere "
            'para cor "#rrggbb", por exemplo {"k": "#2d3436"}'
        )
    paleta: dict[str, RGB] = {}
    for chave, valor in bruta.items():
        if not isinstance(chave, str) or len(chave) != 1:
            raise ReceitaInvalida(
                f"paleta: a chave '{chave}' precisa ter exatamente um caractere, "
                "para caber nas linhas de 'px'"
            )
        if chave in RESERVADOS:
            raise ReceitaInvalida(
                f"paleta: a chave '{chave}' é reservada ('.' mantém, '-' apaga); "
                "use outro caractere"
            )
        if not isinstance(valor, str) or not _HEX.match(valor):
            raise ReceitaInvalida(
                f"paleta['{chave}']: '{valor}' não é uma cor no formato \"#rrggbb\""
            )
        paleta[chave] = (int(valor[1:3], 16), int(valor[3:5], 16), int(valor[5:7], 16))
    return paleta


def _ler_grade(bruta: Any) -> tuple[int, int]:
    numeros = _inteiros(bruta, 2, "grade")
    if numeros[0] < 1 or numeros[1] < 1:
        raise ReceitaInvalida(f"grade: {list(numeros)} precisa ter largura e altura positivas")
    return (numeros[0], numeros[1])


def _ler_camada(bruta: Any, indice: int, paleta: dict[str, RGB]) -> Camada:
    onde = f"camadas[{indice}]"
    if not isinstance(bruta, dict):
        raise ReceitaInvalida(f"{onde}: cada camada precisa ser um objeto, e chegou {_tipo(bruta)}")
    _sem_chaves_estranhas(bruta, _CHAVES_CAMADA, onde)

    nome = bruta.get("nome", f"camada {indice + 1}")
    if not isinstance(nome, str) or not nome.strip():
        raise ReceitaInvalida(f"{onde}: 'nome' precisa ser um texto não vazio")
    onde = f"{onde} ('{nome}')"

    espelho = bruta.get("espelho")
    if espelho is not None and espelho not in ESPELHOS:
        raise ReceitaInvalida(
            f"{onde}: 'espelho' aceita {', '.join(repr(e) for e in ESPELHOS)}, e chegou {espelho!r}"
        )

    ops_brutas = bruta.get("ops")
    if not isinstance(ops_brutas, list) or not ops_brutas:
        raise ReceitaInvalida(f"{onde}: a camada precisa de 'ops', uma lista com pelo menos uma operação")

    ops = tuple(
        _ler_operacao(op, f"{onde}.ops[{posicao}]", paleta)
        for posicao, op in enumerate(ops_brutas)
    )
    if espelho is not None:
        for op in ops:
            if op.forma == "balde":
                # O balde enxerga a grade *antes* do espelho: numa camada
                # espelhada ele vaza pelo lado que ainda não foi desenhado, e
                # a cópia leva o vazamento junto. Melhor recusar do que deixar
                # o desenho depender dessa ordem.
                raise ReceitaInvalida(
                    f"{op.caminho}: 'balde' não pode ficar em camada com 'espelho' — "
                    "ele preenche antes da cópia e vazaria pelo lado ainda vazio; "
                    "ponha o balde numa camada sem espelho, depois desta"
                )
    return Camada(nome=nome, ops=ops, espelho=espelho)


def _ler_operacao(bruta: Any, onde: str, paleta: dict[str, RGB]) -> Operacao:
    if not isinstance(bruta, dict):
        raise ReceitaInvalida(f"{onde}: cada operação precisa ser um objeto, e chegou {_tipo(bruta)}")

    formas = [chave for chave in bruta if chave in FORMAS]
    if len(formas) != 1:
        achadas = ", ".join(formas) if formas else "nenhuma"
        raise ReceitaInvalida(
            f"{onde}: cada operação tem exatamente uma forma entre "
            f"{', '.join(FORMAS)} (achadas: {achadas})"
        )
    forma = formas[0]
    _sem_chaves_estranhas(bruta, _EXTRAS[forma] | {forma}, f"{onde} ({forma})")
    onde = f"{onde} ({forma})"

    if forma == "px":
        return _ler_px(bruta, onde, paleta)

    cor = bruta.get("cor")
    if cor is None:
        raise ReceitaInvalida(f"{onde}: falta 'cor', a chave da paleta")
    if cor not in paleta:
        raise ReceitaInvalida(
            f"{onde}: a cor '{cor}' não está na paleta (chaves: {', '.join(paleta)})"
        )

    contorno = bruta.get("contorno", False)
    if not isinstance(contorno, bool):
        raise ReceitaInvalida(f"{onde}: 'contorno' precisa ser true ou false")

    valor = bruta[forma]
    if forma in ("ret", "elipse"):
        numeros = _inteiros(valor, 4, f"{onde}", formato="[x, y, largura, altura]")
        if numeros[2] < 1 or numeros[3] < 1:
            raise ReceitaInvalida(f"{onde}: largura e altura precisam ser pelo menos 1")
    elif forma == "linha":
        numeros = _pontos(valor, minimo=2, onde=onde)
    elif forma == "poligono":
        numeros = _pontos(valor, minimo=3, onde=onde)
    else:  # balde
        numeros = _inteiros(valor, 2, f"{onde}", formato="[x, y]")

    return Operacao(forma=forma, numeros=numeros, cor=cor, contorno=contorno, caminho=onde)


def _ler_px(bruta: dict[str, Any], onde: str, paleta: dict[str, RGB]) -> Operacao:
    linhas = bruta["px"]
    if not isinstance(linhas, list) or not linhas or not all(isinstance(item, str) for item in linhas):
        raise ReceitaInvalida(f"{onde}: 'px' precisa ser uma lista de textos, um por linha")
    if "em" not in bruta:
        raise ReceitaInvalida(f"{onde}: falta 'em', o canto superior esquerdo [x, y]")
    em = _inteiros(bruta["em"], 2, f"{onde}.em", formato="[x, y]")

    pinta = False
    for numero, linha in enumerate(linhas):
        for coluna, caractere in enumerate(linha):
            if caractere == MANTER:
                continue
            if caractere != APAGAR and caractere not in paleta:
                raise ReceitaInvalida(
                    f"{onde}: o caractere '{caractere}' (linha {numero}, coluna {coluna}) "
                    f"não está na paleta (chaves: {', '.join(paleta)}; '.' mantém, '-' apaga)"
                )
            pinta = True
    if not pinta:
        raise ReceitaInvalida(f"{onde}: as linhas só têm '.', então não pintam nada")

    return Operacao(forma="px", linhas=tuple(linhas), em=(em[0], em[1]), caminho=onde)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _inteiros(bruto: Any, quantos: int, onde: str, *, formato: str | None = None) -> tuple[int, ...]:
    esperado = formato or f"{quantos} inteiros"
    if (
        not isinstance(bruto, list)
        or len(bruto) != quantos
        or not all(_e_inteiro(item) for item in bruto)
    ):
        raise ReceitaInvalida(f"{onde}: esperava {esperado}, e chegou {bruto!r}")
    return tuple(bruto)


def _pontos(bruto: Any, *, minimo: int, onde: str) -> tuple[int, ...]:
    if (
        not isinstance(bruto, list)
        or len(bruto) < minimo * 2
        or len(bruto) % 2
        or not all(_e_inteiro(item) for item in bruto)
    ):
        raise ReceitaInvalida(
            f"{onde}: esperava pelo menos {minimo} pontos como [x0, y0, x1, y1, ...], "
            f"e chegou {bruto!r}"
        )
    return tuple(bruto)


def _e_inteiro(valor: Any) -> bool:
    # ``True`` é ``int`` em Python, e um [true, 2] não é uma coordenada.
    return isinstance(valor, int) and not isinstance(valor, bool)


def _sem_chaves_estranhas(bruto: dict[str, Any], aceitas: frozenset[str], onde: str) -> None:
    estranhas = sorted(str(chave) for chave in bruto if chave not in aceitas)
    if estranhas:
        raise ReceitaInvalida(
            f"{onde}: chave desconhecida {', '.join(repr(c) for c in estranhas)} "
            f"(aceitas: {', '.join(sorted(aceitas))})"
        )


def _tipo(valor: Any) -> str:
    nomes = {
        dict: "um objeto",
        list: "uma lista",
        str: "um texto",
        int: "um número",
        float: "um número",
        bool: "um booleano",
        type(None): "null",
    }
    return nomes.get(type(valor), type(valor).__name__)
