"""Linha e contorno na receita (lote F1, FUNDAMENTOS_E_FERRAMENTAS §4 e §5).

Comandos opcionais, ligados pelo interruptor ``comandos_linha``:

* ``reta`` — dois pontos, traçados com **degraus do mesmo tamanho** (1 por 1,
  2 por 1, 3 por 1). Degraus iguais nem sempre chegam ao ponto final pedido:
  o ponto final é ajustado, e o aviso diz onde a reta terminou. A ``linha`` de
  sempre continua existindo para quando a emenda importa mais que o degrau;
* ``curva`` — três ou mais pontos, por onde a curva passa (Catmull-Rom),
  traçada sem canto em L; degraus fora de progressão viram aviso;
* ``limpar_linha`` — sobre o que a camada já pintou, tira as **dobras** (2×2
  da mesma cor numa linha) e depois os **cantos em L** (o pixel do meio de um
  degrau que encosta nos dois lados), e relata o que tirou e o que sobrou;
* ``contorno`` (raiz) — o contorno de todas as camadas, por último: inteiro
  (uma cor), seletivo (outra cor do lado da luz) ou colorido (o tom mais escuro
  da rampa de cada pixel).

Um canto proposital — os dois braços retos com 2 pixels ou mais, como o canto
de uma caixa — não é canto em L e fica. Uma cor que tem preenchimento (algum
pixel com os quatro vizinhos da mesma cor) não perde dobras: 2×2 ali é a
mancha, não a linha.

Sem fonte externa para os números: as regras são do §4 (Pedro Medeiros, sobre
a ordem "dobras, depois cantos"), e as medidas que conferem o resultado moram no
olho do app (``referencias/olho.py``), calibradas pelas referências.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

__all__ = [
    "TIPOS_DE_CONTORNO",
    "TRACOS",
    "calombos_do_caminho",
    "cantos_em_l",
    "contorno_automatico",
    "curva",
    "dobras",
    "limpar",
    "reta",
    "sem_cantos_no_caminho",
]

Ponto = tuple[int, int]

#: As operações de traço do grupo.
TRACOS = ("reta", "curva")
TIPOS_DE_CONTORNO = ("inteiro", "seletivo", "colorido")
_QUATRO = ((1, 0), (-1, 0), (0, 1), (0, -1))
_OITO = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)


# ---------------------------------------------------------------------------
# Traços
# ---------------------------------------------------------------------------
def _arredonda(valor: float) -> int:
    return math.floor(valor + 0.5)


def reta(x0: int, y0: int, x1: int, y1: int) -> tuple[list[Ponto], Ponto]:
    """Os pixels da reta com degraus iguais, e o ponto onde ela terminou."""
    dx, dy = x1 - x0, y1 - y0
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    ax, ay = abs(dx), abs(dy)
    if ax == 0 or ay == 0:
        comprimento = max(ax, ay) + 1
        pontos = [(x0 + sx * i, y0 + sy * i) for i in range(comprimento)]
        return pontos, pontos[-1]
    if ax >= ay:
        degraus = ay + 1
        passo = max(1, _arredonda((ax + 1) / degraus))
        pontos = [(x0 + sx * (k * passo + i), y0 + sy * k) for k in range(degraus) for i in range(passo)]
    else:
        degraus = ax + 1
        passo = max(1, _arredonda((ay + 1) / degraus))
        pontos = [(x0 + sx * k, y0 + sy * (k * passo + i)) for k in range(degraus) for i in range(passo)]
    return pontos, pontos[-1]


def _catmull_rom(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    t2, t3 = t * t, t * t * t
    return tuple(
        0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3)
        for a, b, c, d in zip(p0, p1, p2, p3)
    )


def _ligar(a: Ponto, b: Ponto) -> list[Ponto]:
    """Os pixels de ``a`` até ``b`` (sem ``a``), 8-conectados."""
    passos = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
    return [
        (_arredonda(a[0] + (b[0] - a[0]) * i / passos), _arredonda(a[1] + (b[1] - a[1]) * i / passos))
        for i in range(1, passos + 1)
    ]


def sem_cantos_no_caminho(caminho: Sequence[Ponto]) -> list[Ponto]:
    """Tira o pixel do meio de cada canto em L de um caminho em ordem."""
    limpo: list[Ponto] = []
    for ponto in caminho:
        if limpo and ponto == limpo[-1]:
            continue
        if len(limpo) >= 2:
            a, b = limpo[-2], limpo[-1]
            if abs(ponto[0] - a[0]) == 1 and abs(ponto[1] - a[1]) == 1 and (
                abs(b[0] - a[0]) + abs(b[1] - a[1]) == 1
            ):
                limpo.pop()
        limpo.append(ponto)
    return limpo


def curva(pontos: Sequence[Ponto]) -> list[Ponto]:
    """A curva que passa pelos pontos, 8-conectada e sem canto em L."""
    controles = [pontos[0], *pontos, pontos[-1]]
    caminho: list[Ponto] = [tuple(pontos[0])]
    for i in range(1, len(controles) - 2):
        p0, p1, p2, p3 = controles[i - 1], controles[i], controles[i + 1], controles[i + 2]
        amostras = max(8, 4 * max(abs(p2[0] - p1[0]), abs(p2[1] - p1[1])))
        for k in range(1, amostras + 1):
            x, y = _catmull_rom(p0, p1, p2, p3, k / amostras)
            alvo = (_arredonda(x), _arredonda(y))
            if alvo != caminho[-1]:
                caminho.extend(_ligar(caminho[-1], alvo))
    return sem_cantos_no_caminho(caminho)


def _grupos(caminho: Sequence[Ponto], eixo: int) -> list[tuple[int, Ponto]]:
    """Os trechos consecutivos do caminho na mesma linha (eixo 1) ou coluna (eixo 0)."""
    grupos: list[tuple[int, Ponto]] = []
    for ponto in caminho:
        if grupos and grupos[-1][1][eixo] == ponto[eixo]:
            grupos[-1] = (grupos[-1][0] + 1, grupos[-1][1])
        else:
            grupos.append((1, ponto))
    return grupos


def _sequencias(grupos: list[tuple[int, Ponto]], eixo: int) -> list[list[tuple[int, Ponto]]]:
    """Os grupos partidos onde a direção do outro eixo muda (o ápice de uma curva)."""
    sequencias: list[list[tuple[int, Ponto]]] = []
    direcao = 0
    for grupo in grupos:
        if sequencias:
            passo = grupo[1][eixo] - sequencias[-1][-1][1][eixo]
            atual = (passo > 0) - (passo < 0)
            if direcao and atual != direcao:
                sequencias.append([sequencias[-1][-1], grupo])
                direcao = atual
                continue
            direcao = atual
            sequencias[-1].append(grupo)
        else:
            sequencias.append([grupo])
    return sequencias


def calombos_do_caminho(caminho: Sequence[Ponto]) -> list[Ponto]:
    """Onde os degraus de um caminho saem da progressão (5, 2, 1, 2 tem um).

    A progressão vale num trecho de inclinação de um sinal só: no ápice de uma
    curva o trecho mais longo é o fim de uma sequência e o começo da outra.
    """
    achados: list[Ponto] = []
    for eixo in (1, 0):
        for sequencia in _sequencias(_grupos(caminho, eixo), eixo):
            for antes, meio, depois in zip(sequencia, sequencia[1:], sequencia[2:]):
                a, b, c = antes[0], meio[0], depois[0]
                if (b < a and b < c) or (b > a and b > c):
                    achados.append(meio[1])
    return achados


# ---------------------------------------------------------------------------
# Limpeza sobre uma máscara
# ---------------------------------------------------------------------------
def _vizinhos(p: Ponto, mascara: set[Ponto], direcoes) -> list[Ponto]:
    return [(p[0] + dx, p[1] + dy) for dx, dy in direcoes if (p[0] + dx, p[1] + dy) in mascara]


def _e_canto_em_l(p: Ponto, mascara: set[Ponto]) -> bool:
    quatro = _vizinhos(p, mascara, _QUATRO)
    if len(quatro) != 2:
        return False
    h = next((q for q in quatro if q[1] == p[1]), None)
    v = next((q for q in quatro if q[0] == p[0]), None)
    if h is None or v is None:
        return False
    diagonal = (h[0], v[1])
    if diagonal in mascara:
        return False  # é um 2×2: dobra, não canto
    if not _simples(p, mascara):
        return False  # junção: tirar o pixel separaria um terceiro traço
    # Canto proposital: os dois braços seguem retos por mais um pixel.
    h2 = (2 * h[0] - p[0], h[1])
    v2 = (v[0], 2 * v[1] - p[1])
    return not (h2 in mascara and v2 in mascara)


def cantos_em_l(mascara: Iterable[Ponto]) -> list[Ponto]:
    """Os pixels do meio de canto em L numa máscara de linha."""
    conjunto = set(mascara)
    return sorted((p for p in conjunto if _e_canto_em_l(p, conjunto)), key=lambda p: (p[1], p[0]))


def dobras(mascara: Iterable[Ponto]) -> list[Ponto]:
    """O canto de cima à esquerda de cada bloco 2×2 da máscara."""
    conjunto = set(mascara)
    return sorted(
        (
            (x, y)
            for x, y in conjunto
            if {(x + 1, y), (x, y + 1), (x + 1, y + 1)} <= conjunto
        ),
        key=lambda p: (p[1], p[0]),
    )


def _tem_miolo(mascara: set[Ponto]) -> bool:
    return any(len(_vizinhos(p, mascara, _QUATRO)) == 4 for p in mascara)


def _simples(p: Ponto, mascara: set[Ponto]) -> bool:
    """Tirar ``p`` não parte a linha nem come uma ponta."""
    vizinhos = _vizinhos(p, mascara, _OITO)
    if len(vizinhos) < 2:
        return False
    restantes = set(vizinhos)
    pilha = [vizinhos[0]]
    vistos = {vizinhos[0]}
    while pilha:
        atual = pilha.pop()
        for q in _vizinhos(atual, restantes, _OITO):
            if q not in vistos:
                vistos.add(q)
                pilha.append(q)
    return vistos == restantes


def limpar(
    celulas: Mapping[Ponto, str | None], cores: Iterable[str] | None = None
) -> tuple[list[Ponto], list[Ponto], dict[str, int], list[str]]:
    """O que ``limpar_linha`` tira: (das dobras, dos cantos, o que sobrou, cores puladas).

    Primeiro as dobras, depois os cantos (§4: corrigir os cantos depois do
    resto, porque tirar dobra pode criar canto). ``sobrou`` mede de novo.
    """
    alvo = set(cores) if cores is not None else {c for c in celulas.values() if c is not None}
    tirados_dobra: list[Ponto] = []
    tirados_canto: list[Ponto] = []
    puladas: list[str] = []
    sobrou = {"cantos": 0, "dobras": 0}
    for cor in sorted(alvo):
        mascara = {p for p, valor in celulas.items() if valor == cor}
        if not mascara:
            continue
        if _tem_miolo(mascara):
            puladas.append(cor)
        else:
            while True:
                blocos = dobras(mascara)
                if not blocos:
                    break
                x, y = blocos[0]
                bloco = [(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)]
                candidatos = sorted(
                    (p for p in bloco if _simples(p, mascara)),
                    key=lambda p: (
                        len(_vizinhos(p, mascara, _QUATRO)),
                        len(_vizinhos(p, mascara, _OITO)),
                        p[1],
                        p[0],
                    ),
                )
                if not candidatos:
                    break
                mascara.discard(candidatos[0])
                tirados_dobra.append(candidatos[0])
        for p in sorted(mascara, key=lambda q: (q[1], q[0])):
            if p in mascara and _e_canto_em_l(p, mascara):
                mascara.discard(p)
                tirados_canto.append(p)
        sobrou["cantos"] += len(cantos_em_l(mascara))
        if cor not in puladas:
            sobrou["dobras"] += len(dobras(mascara))
    return tirados_dobra, tirados_canto, sobrou, puladas


# ---------------------------------------------------------------------------
# Contorno de todas as camadas
# ---------------------------------------------------------------------------
def contorno_automatico(
    celulas: Sequence[str | None],
    largura: int,
    altura: int,
    *,
    tipo: str,
    cor: str,
    cor_luz: str | None,
    luz: tuple[float, float],
    rampas: Sequence[str],
) -> dict[Ponto, str]:
    """A cor de cada pixel da borda da silhueta, no tipo de contorno pedido.

    A borda é o pixel pintado com um vizinho (dos quatro) transparente ou fora
    da grade. ``seletivo`` usa ``cor_luz`` na borda virada para a luz;
    ``colorido``, o tom mais escuro da rampa do pixel (``cor`` fora de rampa).
    """
    def pintado(x: int, y: int) -> bool:
        return 0 <= x < largura and 0 <= y < altura and celulas[y * largura + x] is not None

    escuro_da_rampa = {chave: chaves[0] for chaves in rampas for chave in chaves}
    novas: dict[Ponto, str] = {}
    for y in range(altura):
        for x in range(largura):
            atual = celulas[y * largura + x]
            if atual is None:
                continue
            fora = [(dx, dy) for dx, dy in _QUATRO if not pintado(x + dx, y + dy)]
            if not fora:
                continue
            if tipo == "seletivo" and cor_luz is not None and any(
                dx * luz[0] + dy * luz[1] > 0 for dx, dy in fora
            ):
                novas[(x, y)] = cor_luz
            elif tipo == "colorido":
                novas[(x, y)] = escuro_da_rampa.get(atual, cor)
            else:
                novas[(x, y)] = cor
    return novas
