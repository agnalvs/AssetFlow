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
from dataclasses import dataclass, field
from typing import Any

from .construcao import expandir_boneco
from .cor_e_luz import DESVIO_MAXIMO, EFEITOS, LUZES, MATERIAIS, VOLUMES, gerar_rampa

#: Operações de construção (lote F3): ``capsula`` e ``copiar``.
CONSTRUCAO = ("capsula", "copiar")

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
_CHAVES_RAIZ = frozenset({"grade", "paleta", "camadas", "rampas", "luz", "boneco"})
_CHAVES_CAMADA = frozenset({"nome", "espelho", "ops", "material"})
#: Campos de cada efeito do lote F2 (cor e luz), além da própria chave.
_EXTRAS_EFEITOS = {
    "sombrear": frozenset({"rampa"}),
    "brilho": frozenset({"sobre"}),
    "oclusao": frozenset({"cor", "sobre"}),
    "sombra_projetada": frozenset({"cor", "sobre", "distancia"}),
}
#: Campos das operações de construção (lote F3), além da própria chave.
_EXTRAS_CONSTRUCAO = {
    "capsula": frozenset({"espessura", "cor", "contorno", "vao"}),
    "copiar": frozenset({"desloca", "espelho"}),
}
#: Nome de cada grupo de comandos opcionais, como o interruptor da gaveta o chama.
COR_E_LUZ = "cor_e_luz"
CONSTRUCAO_GRUPO = "construcao"
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
    #: Os campos de um efeito (lote F2): ``rampa``, ``sobre``, ``camada`` (o
    #: índice da camada citada), ``distancia``.
    parametros: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Camada:
    nome: str
    ops: tuple[Operacao, ...]
    espelho: str | None = None
    #: Material da camada (lote F2): muda o contraste do sombrear e o brilho.
    material: str | None = None


@dataclass(frozen=True, slots=True)
class Receita:
    paleta: dict[str, RGB]
    camadas: tuple[Camada, ...]
    #: Tamanho para o qual a receita foi desenhada, quando ela declara. Só
    #: serve para conferir: quem manda no tamanho é o pedido.
    grade: tuple[int, int] | None = None
    #: De onde vem a luz dos efeitos (lote F2).
    luz: str = "cima-esquerda"
    #: Os grupos de comandos opcionais que a receita usa (``cor_e_luz``...),
    #: para a gaveta conferir os interruptores.
    usa: frozenset[str] = frozenset()


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
    usa: set[str] = set()
    if "rampas" in bruta:
        paleta.update(_ler_rampas(bruta["rampas"], paleta))
        usa.add(COR_E_LUZ)
    luz = bruta.get("luz", "cima-esquerda")
    if luz not in LUZES:
        raise ReceitaInvalida(f"luz: '{luz}' não existe; use {', '.join(LUZES)}")
    if "luz" in bruta:
        usa.add(COR_E_LUZ)

    camadas_brutas = bruta.get("camadas")
    if "boneco" in bruta:
        # O boneco vira camadas no formato da receita, antes das da receita:
        # elas pintam por cima dele (lote F3).
        if not isinstance(bruta["boneco"], dict):
            raise ReceitaInvalida("boneco: um objeto com altura, cabecas, chao, centro e cores")
        try:
            geradas = expandir_boneco(bruta["boneco"])
        except ValueError as exc:
            raise ReceitaInvalida(str(exc)) from exc
        for chave in bruta["boneco"]["cores"].values():
            if chave not in paleta:
                raise ReceitaInvalida(f"boneco: a cor '{chave}' não está na paleta")
        camadas_brutas = [*geradas, *(camadas_brutas or [])]
        usa.add(CONSTRUCAO_GRUPO)
    if not isinstance(camadas_brutas, list) or not camadas_brutas:
        raise ReceitaInvalida(
            "a receita precisa de 'camadas': uma lista com pelo menos uma camada"
        )

    camadas: list[Camada] = []
    nomes: dict[str, int] = {}
    for indice, camada_bruta in enumerate(camadas_brutas):
        camada = _ler_camada(camada_bruta, indice, paleta, nomes)
        if camada.nome in nomes:
            raise ReceitaInvalida(
                f"camadas[{indice}]: o nome '{camada.nome}' já foi usado por outra "
                "camada — cada camada precisa de um nome único"
            )
        nomes[camada.nome] = indice
        camadas.append(camada)
        if camada.material or any(op.forma in EFEITOS for op in camada.ops):
            usa.add(COR_E_LUZ)
        if any(op.forma in CONSTRUCAO for op in camada.ops):
            usa.add(CONSTRUCAO_GRUPO)

    return Receita(
        paleta=paleta, camadas=tuple(camadas), grade=grade, luz=luz, usa=frozenset(usa)
    )


def _ler_rampas(bruta: Any, paleta: dict[str, RGB]) -> dict[str, RGB]:
    """As rampas geradas (lote F2): chave -> cor, do escuro ao claro."""
    if not isinstance(bruta, list) or not bruta:
        raise ReceitaInvalida(
            'rampas: uma lista como [{"chaves": "abc", "base": "#3e8948", "desvio": 12}]'
        )
    geradas: dict[str, RGB] = {}
    for i, item in enumerate(bruta):
        onde = f"rampas[{i}]"
        if not isinstance(item, dict):
            raise ReceitaInvalida(f"{onde}: cada rampa é um objeto com chaves, base e desvio")
        _sem_chaves_estranhas(item, frozenset({"chaves", "base", "desvio", "base_em"}), onde)
        chaves = item.get("chaves")
        if not isinstance(chaves, str) or not 2 <= len(chaves) <= 5 or len(set(chaves)) != len(chaves):
            raise ReceitaInvalida(
                f"{onde}: 'chaves' são de 2 a 5 caracteres diferentes, do escuro ao claro (\"abc\")"
            )
        for chave in chaves:
            if chave in RESERVADOS or chave in paleta or chave in geradas:
                raise ReceitaInvalida(
                    f"{onde}: a chave '{chave}' já está na paleta ou é reservada; use outra"
                )
        base = item.get("base")
        if not isinstance(base, str) or not _HEX.match(base):
            raise ReceitaInvalida(f"{onde}: 'base' é a cor do meio, \"#rrggbb\"")
        desvio = item.get("desvio", 12)
        if not _e_inteiro(desvio) or not 0 <= desvio <= DESVIO_MAXIMO:
            raise ReceitaInvalida(
                f"{onde}: 'desvio' é o desvio de matiz por passo, de 0 a {DESVIO_MAXIMO} graus"
            )
        base_em = item.get("base_em")
        if base_em is not None and (not _e_inteiro(base_em) or not 0 <= base_em < len(chaves)):
            raise ReceitaInvalida(f"{onde}: 'base_em' é a posição da base nas chaves (0 a {len(chaves) - 1})")
        rgb = (int(base[1:3], 16), int(base[3:5], 16), int(base[5:7], 16))
        for chave, cor in zip(chaves, gerar_rampa(rgb, len(chaves), desvio, base_em)):
            geradas[chave] = cor
    return geradas


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


def _ler_camada(
    bruta: Any, indice: int, paleta: dict[str, RGB], anteriores: dict[str, int] | None = None
) -> Camada:
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

    material = bruta.get("material")
    if material is not None and material not in MATERIAIS:
        raise ReceitaInvalida(
            f"{onde}: 'material' aceita {', '.join(MATERIAIS)}, e chegou {material!r}"
        )

    ops_brutas = bruta.get("ops")
    if not isinstance(ops_brutas, list) or not ops_brutas:
        raise ReceitaInvalida(f"{onde}: a camada precisa de 'ops', uma lista com pelo menos uma operação")

    ops = tuple(
        _ler_operacao(op, f"{onde}.ops[{posicao}]", paleta, anteriores or {})
        for posicao, op in enumerate(ops_brutas)
    )
    if espelho is not None:
        for op in ops:
            if op.forma in EFEITOS:
                raise ReceitaInvalida(
                    f"{op.caminho}: '{op.forma}' não pode ficar em camada com 'espelho' — "
                    "a cópia levaria a luz para o lado errado; aplique o efeito numa camada "
                    "sem espelho, depois desta"
                )
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
    return Camada(nome=nome, ops=ops, espelho=espelho, material=material)


def _ler_operacao(
    bruta: Any, onde: str, paleta: dict[str, RGB], anteriores: dict[str, int] | None = None
) -> Operacao:
    if not isinstance(bruta, dict):
        raise ReceitaInvalida(f"{onde}: cada operação precisa ser um objeto, e chegou {_tipo(bruta)}")

    todas = (*FORMAS, *EFEITOS, *CONSTRUCAO)
    formas = [chave for chave in bruta if chave in todas]
    if len(formas) != 1:
        achadas = ", ".join(formas) if formas else "nenhuma"
        raise ReceitaInvalida(
            f"{onde}: cada operação tem exatamente uma forma entre "
            f"{', '.join(todas)} (achadas: {achadas})"
        )
    forma = formas[0]
    if forma in EFEITOS:
        return _ler_efeito(bruta, forma, onde, paleta, anteriores or {})
    if forma in CONSTRUCAO:
        return _ler_construcao(bruta, forma, onde, paleta, anteriores or {})
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


def _chaves_da_paleta(valor: Any, onde: str, campo: str, paleta: dict[str, RGB], minimo: int = 1) -> str:
    if not isinstance(valor, str) or len(valor) < minimo:
        raise ReceitaInvalida(f"{onde}: '{campo}' é um texto com chaves da paleta (\"abc\")")
    faltam = [c for c in valor if c not in paleta]
    if faltam:
        raise ReceitaInvalida(
            f"{onde}: '{campo}' cita {', '.join(faltam)}, que não está na paleta"
        )
    return valor


def _ler_efeito(
    bruta: dict[str, Any], efeito: str, onde: str, paleta: dict[str, RGB], anteriores: dict[str, int]
) -> Operacao:
    """Um efeito de cor e luz (lote F2), conferido no formato."""
    _sem_chaves_estranhas(bruta, _EXTRAS_EFEITOS[efeito] | {efeito}, f"{onde} ({efeito})")
    onde = f"{onde} ({efeito})"
    valor = bruta[efeito]
    parametros: dict[str, Any] = {}
    cor = None
    if efeito == "sombrear":
        if valor not in VOLUMES:
            raise ReceitaInvalida(f"{onde}: o volume é {', '.join(VOLUMES)}, e chegou {valor!r}")
        parametros["volume"] = valor
        parametros["rampa"] = _chaves_da_paleta(bruta.get("rampa"), onde, "rampa", paleta, 2)
    elif efeito == "brilho":
        cor = _chaves_da_paleta(valor, onde, "brilho", paleta)
        if len(cor) != 1:
            raise ReceitaInvalida(f"{onde}: 'brilho' é a chave de uma cor só")
        parametros["sobre"] = _chaves_da_paleta(bruta.get("sobre"), onde, "sobre", paleta)
    else:  # oclusao, sombra_projetada
        if valor not in anteriores:
            raise ReceitaInvalida(
                f"{onde}: '{valor}' precisa ser o nome de uma camada desenhada antes desta "
                f"(antes: {', '.join(anteriores) or 'nenhuma'})"
            )
        parametros["camada"] = anteriores[valor]
        cor = bruta.get("cor")
        if cor not in paleta:
            raise ReceitaInvalida(f"{onde}: 'cor' é a chave da cor da sombra, na paleta")
        if "sobre" in bruta:
            parametros["sobre"] = _chaves_da_paleta(bruta["sobre"], onde, "sobre", paleta)
        if efeito == "sombra_projetada":
            distancia = bruta.get("distancia", 1)
            if not _e_inteiro(distancia) or not 1 <= distancia <= 4:
                raise ReceitaInvalida(f"{onde}: 'distancia' vai de 1 a 4 pixels")
            parametros["distancia"] = distancia
    return Operacao(forma=efeito, cor=cor, caminho=onde, parametros=parametros)


def _ler_construcao(
    bruta: dict[str, Any], forma: str, onde: str, paleta: dict[str, RGB], anteriores: dict[str, int]
) -> Operacao:
    """``capsula`` e ``copiar`` (lote F3), conferidos no formato."""
    _sem_chaves_estranhas(bruta, _EXTRAS_CONSTRUCAO[forma] | {forma}, f"{onde} ({forma})")
    onde = f"{onde} ({forma})"
    parametros: dict[str, Any] = {}
    if forma == "capsula":
        valor = bruta["capsula"]
        if (
            not isinstance(valor, list)
            or len(valor) not in (4, 6)
            or not all(_e_inteiro(v) for v in valor)
        ):
            raise ReceitaInvalida(
                f"{onde}: esperava 2 ou 3 pontos, [x0, y0, x1, y1] ou [x0, y0, x1, y1, x2, y2]"
            )
        espessura = bruta.get("espessura", 2)
        if not _e_inteiro(espessura) or not 1 <= espessura <= 8:
            raise ReceitaInvalida(f"{onde}: 'espessura' vai de 1 a 8")
        cor = bruta.get("cor")
        if cor not in paleta:
            raise ReceitaInvalida(f"{onde}: falta 'cor', a chave da paleta")
        if "contorno" in bruta and bruta["contorno"] not in paleta:
            raise ReceitaInvalida(f"{onde}: 'contorno' é a chave da cor da borda, na paleta")
        parametros.update(espessura=espessura, contorno=bruta.get("contorno"))
        if "vao" in bruta:
            if bruta["vao"] not in anteriores:
                raise ReceitaInvalida(f"{onde}: 'vao' cita uma camada desenhada antes desta")
            parametros["vao"] = anteriores[bruta["vao"]]
        return Operacao(forma=forma, numeros=tuple(valor), cor=cor, caminho=onde, parametros=parametros)
    origem = bruta["copiar"]
    if origem not in anteriores:
        raise ReceitaInvalida(
            f"{onde}: '{origem}' precisa ser uma camada desenhada antes desta "
            f"(antes: {', '.join(anteriores) or 'nenhuma'})"
        )
    desloca = _inteiros(bruta.get("desloca", [0, 0]), 2, f"{onde}.desloca", formato="[dx, dy]")
    espelho = bruta.get("espelho")
    if espelho not in (None, "x", "y"):
        raise ReceitaInvalida(f"{onde}: 'espelho' é 'x' ou 'y'")
    parametros.update(camada=anteriores[origem], desloca=desloca, espelho=espelho)
    return Operacao(forma=forma, caminho=onde, parametros=parametros)


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
