"""Construção na receita (lote F3 do FUNDAMENTOS_E_FERRAMENTAS.md, seções 2 e 5).

Comandos opcionais, para pedir a estrutura em vez de pintá-la pixel a pixel:

``{"capsula": [x0, y0, x1, y1, (x2, y2)], "espessura": 3, "cor": "b", "contorno"?: "k", "vao"?: "<camada>"}``
    um membro entre dois ou três pontos (cotovelo, joelho), com pontas
    redondas. ``contorno`` pinta a borda da cápsula com outra chave; ``vao``
    deixa 1 pixel transparente até uma camada anterior (o vão entre braço e
    tronco), menos na ponta de partida, onde o membro se prende.
``{"copiar": "<camada>", "desloca": [dx, dy], "espelho"?: "x"|"y"}``
    duplica o que uma camada anterior pintou, deslocado e, se pedido,
    espelhado em torno do centro dela (o outro braço, a outra orelha).
``"boneco"`` (na raiz)
    as massas de um corpo humanoide em camadas nomeadas, prontas para vestir:
    ``{"altura": 28, "cabecas": 3, "chao": 46, "centro": 24, "forma":
    "circulo"|"quadrado"|"triangulo", "acao": "reta"|"curva"|"inclinada",
    "lado": "direita"|"esquerda", "pose": "parado"|"andando"|"ataque"|"conjurando",
    "cores": {"pele": "p", "roupa": "b", "contorno": "k"}}``. As camadas
    geradas (``boneco_*``) vêm antes das da receita, que pintam por cima.

O boneco é a aposta mais arriscada do plano (§9): ele economiza mais e é o que
mais pode deixar todos os personagens parecidos. Por isso nasce com
parâmetros, é opcional e tem interruptor próprio, ``comandos_construcao``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from itertools import pairwise
from typing import Any

__all__ = [
    "ACOES",
    "FORMAS_DOMINANTES",
    "POSES",
    "celulas_da_capsula",
    "expandir_boneco",
]

Ponto = tuple[int, int]

FORMAS_DOMINANTES = ("circulo", "quadrado", "triangulo")
ACOES = ("reta", "curva", "inclinada")
POSES = ("parado", "andando", "ataque", "conjurando")


def _bresenham(x0: int, y0: int, x1: int, y1: int) -> list[Ponto]:
    pontos = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    erro = dx + dy
    while True:
        pontos.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return pontos
        e2 = 2 * erro
        if e2 >= dy:
            erro += dy
            x0 += sx
        if e2 <= dx:
            erro += dx
            y0 += sy


def _disco(espessura: int) -> list[Ponto]:
    """Os deslocamentos de um disco de diâmetro ``espessura``."""
    raio = espessura / 2
    centro = 0.5 if espessura % 2 == 0 else 0.0
    alcance = math.ceil(raio)
    return [
        (dx, dy)
        for dy in range(-alcance, alcance + 1)
        for dx in range(-alcance, alcance + 1)
        if (dx + centro) ** 2 + (dy + centro) ** 2 <= raio * raio + 0.25
    ]


def celulas_da_capsula(pontos: Iterable[int], espessura: int) -> set[Ponto]:
    """As células de uma cápsula pelos pontos ``[x0, y0, x1, y1, ...]``."""
    numeros = list(pontos)
    caminho: list[Ponto] = []
    pares = [(numeros[i], numeros[i + 1]) for i in range(0, len(numeros), 2)]
    for (xa, ya), (xb, yb) in pairwise(pares):
        caminho.extend(_bresenham(xa, ya, xb, yb))
    disco = _disco(espessura)
    return {(x + dx, y + dy) for x, y in caminho for dx, dy in disco}


def borda(celulas: set[Ponto]) -> set[Ponto]:
    """As células da forma que encostam (pelos 4 lados) no vazio."""
    return {
        (x, y)
        for x, y in celulas
        if any(v not in celulas for v in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    }


# ---------------------------------------------------------------------------
# Boneco
# ---------------------------------------------------------------------------
def expandir_boneco(bruto: Mapping[str, Any]) -> list[dict[str, Any]]:
    """As camadas (no formato da receita) de um boneco, de trás para a frente.

    Raises:
        ValueError: com a mensagem do que está errado, em português.
    """
    def numero(chave: str, padrao: float | None, minimo: float, maximo: float) -> float:
        valor = bruto.get(chave, padrao)
        if not isinstance(valor, (int, float)) or isinstance(valor, bool) or not minimo <= valor <= maximo:
            raise ValueError(f"boneco: '{chave}' vai de {minimo:g} a {maximo:g}")
        return float(valor)

    altura = int(numero("altura", None, 8, 64))
    cabecas = numero("cabecas", 3, 1.5, 8)
    chao = int(numero("chao", None, 0, 255))
    centro = int(numero("centro", None, 0, 255))
    forma = bruto.get("forma", "circulo")
    acao = bruto.get("acao", "reta")
    pose = bruto.get("pose", "parado")
    lado = bruto.get("lado", "direita")
    for nome, valor, opcoes in (
        ("forma", forma, FORMAS_DOMINANTES),
        ("acao", acao, ACOES),
        ("pose", pose, POSES),
        ("lado", lado, ("direita", "esquerda")),
    ):
        if valor not in opcoes:
            raise ValueError(f"boneco: '{nome}' aceita {', '.join(opcoes)}, e chegou {valor!r}")
    cores = bruto.get("cores")
    if not isinstance(cores, Mapping) or not all(isinstance(cores.get(c), str) for c in ("pele", "roupa", "contorno")):
        raise ValueError('boneco: \'cores\' é {"pele": "p", "roupa": "b", "contorno": "k"}, chaves da paleta')
    pele, roupa, contorno = cores["pele"], cores["roupa"], cores["contorno"]
    sinal = 1 if lado == "direita" else -1

    topo = chao - altura + 1
    cabeca = max(3, round(altura / cabecas))
    tronco = max(3, round((altura - cabeca) * 0.45))
    pernas = altura - cabeca - tronco
    amplitude = round(altura * 0.08)

    def linha_de_acao(t: float) -> int:
        """Deslocamento em x da coluna, de t=0 (pés) a t=1 (cabeça)."""
        if acao == "curva":
            return round(sinal * amplitude * math.sin(math.pi * t))
        if acao == "inclinada":
            return round(sinal * amplitude * t)
        return 0

    largura_cabeca = cabeca if forma != "quadrado" else max(3, round(cabeca * 0.95))
    largura_tronco = max(4, round(cabeca * (1.1 if forma == "quadrado" else 1.0)))
    perna = max(2, round(largura_tronco * 0.35))
    braco = max(2, perna - 1)

    cx_cabeca = centro + linha_de_acao(1.0)
    cx_tronco = centro + linha_de_acao(0.62)
    cx_quadril = centro + linha_de_acao(0.35)
    y_cabeca = topo
    y_tronco = topo + cabeca
    y_quadril = y_tronco + tronco

    camadas: list[dict[str, Any]] = []

    def camada(nome: str, ops: list[dict[str, Any]]) -> None:
        camadas.append({"nome": f"boneco_{nome}", "ops": ops})

    # Pernas: do quadril ao chão.
    afastamento = max(1, largura_tronco // 4)
    if pose == "andando":
        pes = (cx_quadril - sinal * round(pernas * 0.35), cx_quadril + sinal * round(pernas * 0.35))
    elif pose == "ataque":
        pes = (cx_quadril - round(pernas * 0.45), cx_quadril + round(pernas * 0.45))
    else:
        pes = (cx_quadril - afastamento, cx_quadril + afastamento)
    quadris = (cx_quadril - afastamento, cx_quadril + afastamento)
    fundo = chao - perna // 2

    # Braços: do ombro à mão.
    y_ombro = y_tronco + braco // 2 + 1
    meio = largura_tronco // 2 + braco // 2 + 1
    ombros = (cx_tronco - meio, cx_tronco + meio)
    comprimento = round(tronco * 1.1)
    if pose == "conjurando":
        maos = ((ombros[0] - 1, y_ombro - round(comprimento * 0.8)), (ombros[1] + 1, y_ombro - round(comprimento * 0.8)))
    elif pose == "ataque":
        frente = ombros[1] if sinal > 0 else ombros[0]
        tras = ombros[0] if sinal > 0 else ombros[1]
        maos_f = (frente + sinal * comprimento, y_ombro - round(comprimento * 0.3))
        maos_t = (tras - sinal * 1, y_ombro + comprimento - 1)
        maos = (maos_t, maos_f) if sinal > 0 else (maos_f, maos_t)
    elif pose == "andando":
        maos = ((ombros[0] + sinal * 2, y_ombro + comprimento - 1), (ombros[1] - sinal * 2, y_ombro + comprimento - 1))
    else:
        maos = ((ombros[0], y_ombro + comprimento - 1), (ombros[1], y_ombro + comprimento - 1))

    tras, frente = (0, 1) if sinal > 0 else (1, 0)

    def membro(nome: str, pontos: list[int], espessura: int, mao: Ponto | None = None) -> None:
        ops: list[dict[str, Any]] = [
            {"capsula": pontos, "espessura": espessura, "cor": roupa, "contorno": contorno}
        ]
        if mao is not None:
            ops.append({"elipse": [mao[0] - 1, mao[1] - 1, 3, 3], "cor": pele})
            ops.append({"elipse": [mao[0] - 1, mao[1] - 1, 3, 3], "cor": contorno, "contorno": True})
        camada(nome, ops)

    membro("braco_tras", [ombros[tras], y_ombro, *maos[tras]], braco, maos[tras])
    membro("perna_tras", [quadris[tras], y_quadril, pes[tras], fundo], perna)
    membro("perna_frente", [quadris[frente], y_quadril, pes[frente], fundo], perna)

    # Tronco: a forma dominante.
    x0 = cx_tronco - largura_tronco // 2
    if forma == "quadrado":
        corpo = [{"ret": [x0, y_tronco, largura_tronco, tronco + 1], "cor": roupa},
                 {"ret": [x0, y_tronco, largura_tronco, tronco + 1], "cor": contorno, "contorno": True}]
    elif forma == "triangulo":
        ombro = round(largura_tronco * 0.7)
        cintura = max(2, round(largura_tronco * 0.4))
        pontos = [cx_tronco - ombro, y_tronco, cx_tronco + ombro, y_tronco,
                  cx_tronco + cintura, y_quadril, cx_tronco - cintura, y_quadril]
        corpo = [{"poligono": pontos, "cor": roupa}, {"poligono": pontos, "cor": contorno, "contorno": True}]
    else:
        corpo = [{"elipse": [x0, y_tronco, largura_tronco, tronco + 2], "cor": roupa},
                 {"elipse": [x0, y_tronco, largura_tronco, tronco + 2], "cor": contorno, "contorno": True}]
    camada("tronco", corpo)

    # Cabeça.
    hx = cx_cabeca - largura_cabeca // 2
    if forma == "quadrado":
        cabeca_ops = [{"ret": [hx, y_cabeca, largura_cabeca, cabeca], "cor": pele},
                      {"ret": [hx, y_cabeca, largura_cabeca, cabeca], "cor": contorno, "contorno": True}]
    else:
        cabeca_ops = [{"elipse": [hx, y_cabeca, largura_cabeca, cabeca], "cor": pele},
                      {"elipse": [hx, y_cabeca, largura_cabeca, cabeca], "cor": contorno, "contorno": True}]
    camada("cabeca", cabeca_ops)
    membro("braco_frente", [ombros[frente], y_ombro, *maos[frente]], braco, maos[frente])
    return camadas
