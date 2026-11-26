"""Detalhes e acabamento na receita (lote F4, FUNDAMENTOS_E_FERRAMENTAS §4 e §5).

Comandos opcionais, ligados pelo interruptor ``comandos_acabamento``:

* ``rosto`` — olhos, sobrancelhas e boca no formato do tamanho da cabeça, com a
  expressão (§9: neutro, feliz, triste, bravo, surpreso) e a direção do olhar;
* ``extremidade`` — mão (aberta ou fechada) ou pé, no formato do tamanho do
  membro, virada para um lado;
* ``suavizar`` — tons intermediários **dentro** da silhueta, no cotovelo dos
  degraus de uma borda curva (§7: AA interno, cor da paleta); recusado, com
  aviso, em sprite pequeno e em reta;
* ``pontilhar`` — duas cores em padrão ancorado à grade (xadrez ou 25%), só
  sobre o que já está pintado; recusado, com aviso, em sprite pequeno ou
  região pequena (§7: "evite em sprites muito pequenos");
* ``textura`` — veio, rachadura, tufos ou escamas sobre o miolo da camada;
* ``luz_de_borda`` — uma linha clara na borda oposta à luz, por dentro do
  contorno, para destacar o sprite de fundo escuro.

"Recusado" aqui não derruba o desenho: o comando não faz nada e o aviso diz
por quê — o desenho do resto da receita continua valendo.

Os números (tamanhos de olho por altura de cabeça, o mínimo para suavizar e
pontilhar) são convenção minha a partir do §7 e do §9, ``a calibrar``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .construcao import borda

__all__ = [
    "EXPRESSOES",
    "LADOS",
    "MINIMO_PARA_PONTILHAR",
    "MINIMO_PARA_SUAVIZAR",
    "OLHARES",
    "PADROES",
    "TEXTURAS",
    "extremidade",
    "luz_de_borda",
    "pontilhar",
    "rosto",
    "suavizar",
    "textura",
]

Ponto = tuple[int, int]

EXPRESSOES = ("neutro", "feliz", "triste", "bravo", "surpreso")
OLHARES = ("frente", "esquerda", "direita", "cima", "baixo")
VISTAS = ("frente", "perfil")
LADOS = ("direita", "esquerda")
PADROES = ("xadrez", "25")
TEXTURAS = ("veio", "rachadura", "tufos", "escamas")
#: O lado maior da grade abaixo do qual ``suavizar`` e ``pontilhar`` são
#: recusados (§7: em sprite pequeno viram ruído). ``a calibrar``.
MINIMO_PARA_SUAVIZAR = 32
MINIMO_PARA_PONTILHAR = 48
#: Pixels pintados na região abaixo dos quais o pontilhado é recusado.
MINIMA_REGIAO = 16
#: Teto de área pontilhada sobre o sprite (§7, "15%, a calibrar").
TETO_PONTILHADO = 0.15
_QUATRO = ((1, 0), (-1, 0), (0, 1), (0, -1))


# ---------------------------------------------------------------------------
# Rosto
# ---------------------------------------------------------------------------
def _medidas_do_olho(cabeca: int) -> tuple[int, int, int, int]:
    """(largura e altura do olho, vão entre os olhos, largura da boca)."""
    if cabeca <= 7:
        return 1, 1, (1 if cabeca <= 5 else 2), (0 if cabeca <= 5 else 1)
    if cabeca <= 11:
        return 1, 2, max(2, cabeca // 4), 1
    if cabeca <= 15:
        return 2, 2, max(2, cabeca // 4), 2
    return 2, 3, max(3, cabeca // 4), 3


def rosto(
    centro: Ponto,
    cabeca: int,
    *,
    expressao: str,
    olhar: str,
    vista: str,
    cor: str,
    boca: str | None,
    reflexo: str | None,
) -> dict[Ponto, str]:
    """Os pixels do rosto. ``centro`` é o meio da linha dos olhos."""
    cx, cy = centro
    largura, altura, vao, boca_l = _medidas_do_olho(cabeca)
    if expressao == "surpreso":
        altura += 1
        boca_l = max(boca_l, 1)
    elif expressao == "bravo":
        altura = max(1, altura - 1)
    dx = {"esquerda": -1, "direita": 1}.get(olhar, 0)
    dy = {"cima": -1, "baixo": 1}.get(olhar, 0)
    topo = cy - altura // 2 + dy
    if vista == "perfil":
        lado = 1 if olhar != "esquerda" else -1
        esquerdas = [cx]
    else:
        lado = 0
        esquerdas = [cx - vao // 2 - largura + dx, cx + (vao + 1) // 2 + dx]

    pixels: dict[Ponto, str] = {}
    for x0 in esquerdas:
        if expressao == "feliz":
            for i in range(largura + (1 if largura == 1 and cabeca >= 8 else 0)):
                pixels[(x0 + i, topo + altura - 1)] = cor  # fechado em linha
        else:
            for i in range(largura):
                for j in range(altura):
                    pixels[(x0 + i, topo + j)] = cor
            if reflexo and largura >= 2 and altura >= 2:
                pixels[(x0, topo)] = reflexo

    if cabeca >= 8 and expressao in ("triste", "bravo") and vista == "frente":
        for indice, x0 in enumerate(esquerdas):
            interno = x0 + largura - 1 if indice == 0 else x0
            externo = x0 if indice == 0 else x0 + largura - 1
            alto, baixo = topo - 2, topo - 1
            if expressao == "triste":  # a ponta de dentro erguida
                pixels[(interno, alto)] = cor
                if externo != interno:
                    pixels[(externo, baixo)] = cor
            else:  # em V: a ponta de dentro baixa
                pixels[(interno, baixo)] = cor
                if externo != interno:
                    pixels[(externo, alto)] = cor
                else:
                    pixels[(interno + (1 if indice == 0 else -1), alto)] = cor

    if boca_l:
        tinta = boca or cor
        linha_da_boca = topo + altura + max(1, cabeca // 4)
        meio = cx + dx + lado
        x0 = meio - boca_l // 2
        if expressao == "surpreso":
            lado_o = 2 if cabeca >= 12 else 1
            for i in range(lado_o):
                for j in range(lado_o):
                    pixels[(meio - lado_o // 2 + i, linha_da_boca + j)] = tinta
        else:
            for i in range(boca_l):
                pixels[(x0 + i, linha_da_boca)] = tinta
            if boca_l >= 2 and expressao in ("feliz", "triste"):
                desloca = -1 if expressao == "feliz" else 1
                pixels[(x0 - 1, linha_da_boca + desloca)] = tinta
                pixels[(x0 + boca_l, linha_da_boca + desloca)] = tinta
    return pixels


# ---------------------------------------------------------------------------
# Mão e pé
# ---------------------------------------------------------------------------
#: Os carimbos virados para a direita; ``#`` pinta. O ponto da receita é o
#: alto do carimbo: o meio dele na mão, o calcanhar no pé.
_MAOS_FECHADAS = {
    1: ["#"],
    2: ["##", "##"],
    3: [".#.", "###", ".#."],
    4: [".##.", "####", "####", ".##."],
}
_MAOS_ABERTAS = {
    1: ["##"],
    2: ["##.", "###"],
    3: [".#.#", "###.", "#.#."],
    4: [".##.#", "####.", "####.", "#.#.."],
}
_PES = {
    1: ["##"],
    2: ["##.", "###"],
    3: ["##..", "####"],
    4: ["###..", "#####", "#####"],
}


def extremidade(
    ponto: Ponto,
    *,
    tipo: str,
    forma: str,
    lado: str,
    tamanho: int,
    cor: str,
    contorno: str | None,
) -> dict[Ponto, str]:
    """Os pixels da mão ou do pé, virados para ``lado``."""
    if tipo == "pe":
        carimbo = _PES[tamanho]
    else:
        carimbo = (_MAOS_ABERTAS if forma == "aberta" else _MAOS_FECHADAS)[tamanho]
    x, y = ponto
    # Virado para a direita, o pé tem o calcanhar no ponto e a mão, o meio da
    # palma; para a esquerda, o carimbo vira em torno do ponto.
    recuo = 0 if tipo == "pe" else (tamanho - 1) // 2
    celulas = set()
    for j, linha in enumerate(carimbo):
        for i, caractere in enumerate(linha):
            if caractere == "#":
                dx = i - recuo
                celulas.add((x + (dx if lado == "direita" else -dx), y + j))
    # Num carimbo de até 3 px todo pixel é borda: o contorno o pintaria inteiro.
    beira = borda(celulas) if contorno and tamanho >= 4 else set()
    return {c: (contorno if c in beira else cor) for c in celulas}


# ---------------------------------------------------------------------------
# Suavizar, pontilhar, textura, luz de borda
# ---------------------------------------------------------------------------
def _trecho(p: Ponto, mascara: set[Ponto], direcao: tuple[int, int]) -> int:
    n, x, y = 1, p[0], p[1]
    while (x + direcao[0], y + direcao[1]) in mascara:
        n += 1
        x, y = x + direcao[0], y + direcao[1]
    return n


def suavizar(
    linha: set[Ponto], pintado: Mapping[Ponto, str | None], cor: str
) -> dict[Ponto, str]:
    """O tom ``cor`` no cotovelo de dentro de cada degrau longo da linha.

    Um degrau é um par de pixels da linha na diagonal. Dos dois cotovelos
    (os pixels que encostam nos dois), o de dentro é o pintado que não é
    linha; o de fora é transparente. Só onde o trecho reto de um dos lados tem
    2 pixels ou mais: uma diagonal de 45° não ganha tom (engrossaria).
    """
    novos: dict[Ponto, str] = {}
    for a in linha:
        for dx, dy in ((1, 1), (1, -1)):
            b = (a[0] + dx, a[1] + dy)
            if b not in linha:
                continue
            cotovelos = [(a[0], b[1]), (b[0], a[1])]
            if any(c in linha for c in cotovelos):
                continue
            longo = max(
                _trecho(a, linha, (-dx, 0)), _trecho(b, linha, (dx, 0)),
                _trecho(a, linha, (0, -dy)), _trecho(b, linha, (0, dy)),
            )
            if longo < 2:
                continue
            dentro = [c for c in cotovelos if pintado.get(c) is not None]
            if len(dentro) == 1:
                novos[dentro[0]] = cor
    return novos


def pontilhar(
    regiao: tuple[int, int, int, int],
    pintado: Mapping[Ponto, str | None],
    cores: str,
    padrao: str,
) -> dict[Ponto, str]:
    """As duas cores em padrão ancorado à grade, só onde já há pintura."""
    x0, y0, largura, altura = regiao
    primeira, segunda = cores[0], cores[1]
    novos = {}
    for y in range(y0, y0 + altura):
        for x in range(x0, x0 + largura):
            if pintado.get((x, y)) is None:
                continue
            if padrao == "xadrez":
                novos[(x, y)] = segunda if (x + y) % 2 else primeira
            else:
                novos[(x, y)] = segunda if (x % 2 == 0 and y % 2 == 0) else primeira
    return novos


def _miolo(celulas: Iterable[Ponto]) -> set[Ponto]:
    conjunto = set(celulas)
    return {p for p in conjunto if all((p[0] + dx, p[1] + dy) in conjunto for dx, dy in _QUATRO)}


def textura(celulas: Iterable[Ponto], padrao: str, cor: str, densidade: int) -> dict[Ponto, str]:
    """O padrão sobre o miolo das células (a borda da camada fica limpa)."""
    miolo = _miolo(celulas)
    passo = {1: 5, 2: 4, 3: 3}[densidade]
    novos = {}
    for x, y in miolo:
        if padrao == "veio":
            # Traços curtos e quebrados, não riscos contínuos (§6, madeira).
            linha = y % (passo - 1 or 2) == 0
            fase = (x + 3 * (y // max(1, passo - 1))) % (passo + 1)
            if linha and fase in (0, 1):
                novos[(x, y)] = cor
        elif padrao == "rachadura":
            celula = ((x // passo), (y // passo))
            local = (x % passo, y % passo)
            if (celula[0] + celula[1]) % 2 == 0 and local in ((0, 0), (1, 1), (1, 2)):
                novos[(x, y)] = cor
        elif padrao == "tufos":
            if (x + 2 * (y // passo)) % passo == 0 and y % passo in (0, 1):
                novos[(x, y)] = cor
        else:  # escamas, em fileiras desencontradas
            largura = 4
            fileira = y // 3
            local_x = (x + (2 if fileira % 2 else 0)) % largura
            local_y = y % 3
            if (local_y == 1 and local_x in (0, 3)) or (local_y == 2 and local_x in (1, 2)):
                novos[(x, y)] = cor
    return {p: c for p, c in novos.items() if p in miolo}


def luz_de_borda(
    alvo: set[Ponto], luz: tuple[float, float], cor: str
) -> dict[Ponto, str]:
    """``cor`` nos pixels do alvo cuja beira fica do lado oposto à luz."""
    novos = {}
    for x, y in alvo:
        for dx, dy in _QUATRO:
            if (x + dx, y + dy) not in alvo and dx * luz[0] + dy * luz[1] < 0:
                novos[(x, y)] = cor
                break
    return novos
