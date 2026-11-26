"""Rasterizador da receita: camadas de formas viram uma grade de pixels.

Ele trabalha **na grade lógica**, uma célula por pixel do arquivo entregue,
e cada célula guarda a *chave* da paleta (ou ``None``, transparente). Cor de
verdade só aparece no fim, em :func:`para_png`: até lá não existe cor
intermediária, anti-aliasing nem alpha parcial para alguém ter de limpar.

Por que aqui, e não sobre o ``PixelCanvas`` do Optimizer: uma gaveta não pode
importar ``assetflow.pixel`` (``tests/test_architecture_boundaries.py``,
regra 7). O canvas daqui é o mínimo necessário para desenhar, e nada mais.

As regras de cada forma, com a origem no canto superior esquerdo, x para a
direita e y para baixo:

``ret [x, y, largura, altura]``
    o retângulo cheio; com ``contorno``, só a borda de 1 pixel.
``elipse [x, y, largura, altura]``
    a elipse inscrita na caixa. Uma célula entra se o **centro** dela cai
    dentro da elipse — o teste é simétrico, então a elipse também é. Com
    ``contorno``, ficam as células da elipse que encostam (pelos 4 lados) em
    uma célula de fora.
``linha [x0, y0, x1, y1, ...]``
    segmentos de Bresenham de 1 pixel, ligando os pontos em ordem.
``poligono [x0, y0, x1, y1, ...]``
    as arestas (Bresenham, fechando no primeiro ponto) mais as células cujo
    centro cai dentro do polígono (regra par-ímpar). Com ``contorno``, só as
    arestas.
``balde [x, y]``
    preenche a região de células iguais à de ``(x, y)``, ligadas pelos 4 lados.
``px`` com ``em [x, y]``
    uma string por linha; ``.`` mantém o que está embaixo, ``-`` apaga.

Camadas são grupos de operações aplicados em ordem sobre a mesma grade. Uma
camada com ``espelho`` é desenhada e depois copiada em torno do centro da
grade (ver :func:`_espelhar`).

O desenho guarda também **de qual camada é cada pixel** (a última que o
pintou): o :attr:`Desenho.mapa_de_camadas`. A gaveta o grava no relatório do
motor, e é por ele que o olho do app mede o contraste de valor entre partes
vizinhas (Fase B2) — a receita é a única fonte que sabe onde termina uma
parte e começa outra.
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from itertools import pairwise

from PIL import Image

from . import cor_e_luz
from .receita import APAGAR, MANTER, Camada, Operacao, Receita, ReceitaInvalida

__all__ = ["SIMBOLOS_DE_CAMADA", "Desenho", "Grade", "desenhar", "para_png"]

#: Um caractere por camada no mapa: a camada ``i`` é ``SIMBOLOS_DE_CAMADA[i]``.
#: Da 63ª em diante, ``?``; ``.`` é transparente.
SIMBOLOS_DE_CAMADA = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

#: O que uma célula guarda: a chave da paleta, ou ``None`` (transparente).
Celula = str | None
Ponto = tuple[int, int]


@dataclass(slots=True)
class Grade:
    """Grade de células endereçada por ``(x, y)``."""

    largura: int
    altura: int
    celulas: list[Celula] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.largura < 1 or self.altura < 1:
            raise ValueError(f"grade degenerada: {self.largura}×{self.altura}")
        if not self.celulas:
            self.celulas = [None] * (self.largura * self.altura)

    def contem(self, x: int, y: int) -> bool:
        return 0 <= x < self.largura and 0 <= y < self.altura

    def ler(self, x: int, y: int) -> Celula:
        return self.celulas[y * self.largura + x]

    def escrever(self, x: int, y: int, valor: Celula) -> None:
        self.celulas[y * self.largura + x] = valor

    def copia(self) -> Grade:
        return Grade(self.largura, self.altura, list(self.celulas))

    def linhas(self) -> list[str]:
        """A grade como texto: chave da paleta, ou ``.`` no transparente.

        É a forma que os testes comparam e a que um laudo em texto mostraria.
        """
        return [
            "".join(
                valor if valor is not None else MANTER
                for valor in self.celulas[y * self.largura : (y + 1) * self.largura]
            )
            for y in range(self.altura)
        ]

    def chaves_usadas(self) -> set[str]:
        return {valor for valor in self.celulas if valor is not None}


@dataclass(frozen=True, slots=True)
class Desenho:
    grade: Grade
    #: Recortes e outras coisas que não impedem o desenho mas precisam ser
    #: ditas: "nada é corrigido em silêncio".
    avisos: tuple[str, ...] = ()
    #: Uma linha por y: o símbolo da camada dona de cada pixel (ver
    #: :data:`SIMBOLOS_DE_CAMADA`), ou ``.`` no transparente.
    mapa_de_camadas: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Desenho
# ---------------------------------------------------------------------------
def desenhar(receita: Receita, largura: int, altura: int) -> Desenho:
    """Desenha a receita numa grade ``largura × altura``.

    Raises:
        ReceitaInvalida: quando a receita não cabe neste pedido — ``grade``
            diferente, operação inteira fora da grade, balde fora dela.
    """
    if receita.grade is not None and receita.grade != (largura, altura):
        raise ReceitaInvalida(
            f"a receita foi desenhada para {receita.grade[0]}×{receita.grade[1]}, "
            f"mas o pedido é {largura}×{altura}"
        )

    grade = Grade(largura, altura)
    donos: list[int | None] = [None] * (largura * altura)
    avisos: list[str] = []
    for indice, camada in enumerate(receita.camadas):
        _aplicar_camada(grade, camada, avisos, donos, indice, receita.luz)
    mapa = tuple(
        "".join(
            "." if dono is None or grade.celulas[y * largura + x] is None
            else (SIMBOLOS_DE_CAMADA[dono] if dono < len(SIMBOLOS_DE_CAMADA) else "?")
            for x, dono in enumerate(donos[y * largura : (y + 1) * largura])
        )
        for y in range(altura)
    )
    return Desenho(grade=grade, avisos=tuple(avisos), mapa_de_camadas=mapa)


def _aplicar_camada(
    grade: Grade,
    camada: Camada,
    avisos: list[str],
    donos: list[int | None] | None = None,
    indice: int = 0,
    luz: str = "cima-esquerda",
) -> None:
    """Desenha a camada e, se pedido, espelha o que ela pintou.

    As operações rodam sobre uma cópia de trabalho, para que o ``balde`` veja
    o que as operações anteriores — desta e das outras camadas — já pintaram.
    O que a camada escreveu é registrado à parte, espelhado, e só então vai
    para a grade.
    """
    trabalho = grade.copia()
    escritas: dict[Ponto, Celula] = {}
    alheias: dict[Ponto, Celula] = {}
    for op in camada.ops:
        if op.forma in cor_e_luz.EFEITOS:
            proprias, de_outras = _efeito(op, camada, escritas, trabalho, donos, luz)
            for (x, y), valor in proprias.items():
                trabalho.escrever(x, y, valor)
                escritas[(x, y)] = valor
            alheias.update(de_outras)
            continue
        for (x, y), valor in _escritas_da_operacao(op, trabalho, avisos):
            trabalho.escrever(x, y, valor)
            escritas[(x, y)] = valor

    if camada.espelho:
        escritas = _espelhar(escritas, camada.espelho, grade.largura, grade.altura)

    for (x, y), valor in escritas.items():
        grade.escrever(x, y, valor)
        if donos is not None:
            donos[y * grade.largura + x] = None if valor is None else indice
    # A sombra projetada escurece outra camada sem tomar os pixels dela.
    for (x, y), valor in alheias.items():
        grade.escrever(x, y, valor)


def _efeito(
    op: Operacao,
    camada: Camada,
    escritas: dict[Ponto, Celula],
    trabalho: Grade,
    donos: list[int | None] | None,
    luz: str,
) -> tuple[dict[Ponto, Celula], dict[Ponto, Celula]]:
    """Um efeito de cor e luz (lote F2): o que muda nesta camada e em outras."""
    p = op.parametros
    if op.forma == "sombrear":
        return cor_e_luz.sombrear(escritas, p["rampa"], p["volume"], luz, camada.material), {}
    if op.forma == "brilho":
        return cor_e_luz.brilho(escritas, op.cor, p["sobre"], luz, camada.material), {}
    largura = trabalho.largura
    mapa = {
        (i % largura, i // largura): dono
        for i, dono in enumerate(donos or [])
        if dono is not None
    }
    if op.forma == "oclusao":
        return cor_e_luz.oclusao(escritas, mapa, p["camada"], op.cor, p.get("sobre")), {}
    chaves = {
        (x, y): trabalho.ler(x, y) for (x, y) in mapa
    }
    return {}, cor_e_luz.sombra_projetada(
        escritas, mapa, p["camada"], op.cor, luz, p.get("distancia", 1), p.get("sobre"), chaves
    )


def _espelhar(
    escritas: dict[Ponto, Celula], eixos: str, largura: int, altura: int
) -> dict[Ponto, Celula]:
    """Copia o que a camada pintou em torno do centro da grade.

    ``x`` reflete esquerda e direita (a coluna ``c`` vai para
    ``largura - 1 - c``); ``y``, cima e baixo; ``xy``, os dois — primeiro em
    ``x``, depois o resultado em ``y``, o que dá os quatro quadrantes.

    Em largura ímpar a coluna do meio é o próprio espelho e fica como está.

    **A cópia só preenche posições que a camada não pintou.** Se a camada
    pintou os dois lados, o que ela pintou vale: o espelho completa o desenho,
    nunca apaga uma decisão explícita. É o que deixa uma camada espelhada
    ter um detalhe assimétrico sem precisar de outra camada para ele.
    """
    resultado = dict(escritas)
    if "x" in eixos:
        for (x, y), valor in list(resultado.items()):
            resultado.setdefault((largura - 1 - x, y), valor)
    if "y" in eixos:
        for (x, y), valor in list(resultado.items()):
            resultado.setdefault((x, altura - 1 - y), valor)
    return resultado


def _escritas_da_operacao(
    op: Operacao, trabalho: Grade, avisos: list[str]
) -> Iterator[tuple[Ponto, Celula]]:
    """As células que a operação pinta, já recortadas à grade."""
    if op.forma == "balde":
        yield from _balde(op, trabalho)
        return

    if op.forma == "px":
        candidatas = list(_px(op))
    else:
        candidatas = [(ponto, op.cor) for ponto in _pontos_da_forma(op)]

    dentro = [(ponto, valor) for ponto, valor in candidatas if trabalho.contem(*ponto)]
    fora = len(candidatas) - len(dentro)
    if candidatas and not dentro:
        raise ReceitaInvalida(
            f"{op.caminho}: a operação fica inteira fora da grade "
            f"{trabalho.largura}×{trabalho.altura}"
        )
    if fora:
        avisos.append(
            f"{op.caminho}: {fora} pixel(s) fora da grade "
            f"{trabalho.largura}×{trabalho.altura} foram recortados"
        )
    yield from dentro


def _pontos_da_forma(op: Operacao) -> list[Ponto]:
    if op.forma == "ret":
        return _retangulo(*op.numeros, contorno=op.contorno)
    if op.forma == "elipse":
        return _elipse(*op.numeros, contorno=op.contorno)
    if op.forma == "linha":
        return _sem_repetir(_polilinha(_pares(op.numeros), fechar=False))
    if op.forma == "poligono":
        return _poligono(_pares(op.numeros), contorno=op.contorno)
    raise AssertionError(f"forma sem rasterização: {op.forma}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Formas
# ---------------------------------------------------------------------------
def _retangulo(x: int, y: int, largura: int, altura: int, *, contorno: bool) -> list[Ponto]:
    pontos = []
    for j in range(y, y + altura):
        for i in range(x, x + largura):
            borda = i in (x, x + largura - 1) or j in (y, y + altura - 1)
            if not contorno or borda:
                pontos.append((i, j))
    return pontos


def _elipse(x: int, y: int, largura: int, altura: int, *, contorno: bool) -> list[Ponto]:
    cx, cy = x + largura / 2, y + altura / 2
    rx, ry = largura / 2, altura / 2
    cheia = {
        (i, j)
        for j in range(y, y + altura)
        for i in range(x, x + largura)
        if ((i + 0.5 - cx) / rx) ** 2 + ((j + 0.5 - cy) / ry) ** 2 <= 1.0
    }
    if contorno:
        cheia = {
            (i, j)
            for (i, j) in cheia
            if any(viz not in cheia for viz in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)))
        }
    return sorted(cheia, key=lambda p: (p[1], p[0]))


def _poligono(vertices: list[Ponto], *, contorno: bool) -> list[Ponto]:
    arestas = _polilinha(vertices, fechar=True)
    if contorno:
        return _sem_repetir(arestas)

    xs = [vx for vx, _ in vertices]
    ys = [vy for _, vy in vertices]
    pontos = list(arestas)
    for j in range(min(ys), max(ys) + 1):
        for i in range(min(xs), max(xs) + 1):
            # Os vértices são centros de célula, então testar o centro da
            # célula (i + .5, j + .5) contra eles deslocados de .5 é testar
            # (i, j) contra os vértices como vieram.
            if _dentro(i, j, vertices):
                pontos.append((i, j))
    return _sem_repetir(pontos)


def _dentro(px: float, py: float, vertices: list[Ponto]) -> bool:
    """Regra par-ímpar: um raio para a direita cruza a borda quantas vezes?"""
    dentro = False
    quantos = len(vertices)
    for indice in range(quantos):
        x1, y1 = vertices[indice]
        x2, y2 = vertices[(indice + 1) % quantos]
        if (y1 > py) != (y2 > py):
            cruza = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if px < cruza:
                dentro = not dentro
    return dentro


def _polilinha(pontos: list[Ponto], *, fechar: bool) -> list[Ponto]:
    sequencia = list(pontos) + ([pontos[0]] if fechar else [])
    celulas: list[Ponto] = []
    for (x0, y0), (x1, y1) in pairwise(sequencia):
        celulas.extend(_bresenham(x0, y0, x1, y1))
    return celulas


def _bresenham(x0: int, y0: int, x1: int, y1: int) -> list[Ponto]:
    """Segmento de 1 pixel entre dois pontos, **o mesmo nos dois sentidos**.

    O Bresenham puro desempata conforme a direção: de A para B e de B para A
    dão degraus diferentes. Aqui o traçado sempre parte do menor ponto, então
    a aresta de um polígono e uma linha sobre ela coincidem — senão o
    preenchimento vaza um pixel para fora do contorno.
    """
    if (x1, y1) < (x0, y0):
        return _bresenham(x1, y1, x0, y0)[::-1]
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    erro = dx + dy
    pontos = []
    while True:
        pontos.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return pontos
        dobro = 2 * erro
        if dobro >= dy:
            erro += dy
            x0 += sx
        if dobro <= dx:
            erro += dx
            y0 += sy


def _balde(op: Operacao, trabalho: Grade) -> Iterator[tuple[Ponto, Celula]]:
    x, y = op.numeros
    if not trabalho.contem(x, y):
        raise ReceitaInvalida(
            f"{op.caminho}: o ponto ({x}, {y}) está fora da grade "
            f"{trabalho.largura}×{trabalho.altura}"
        )
    alvo = trabalho.ler(x, y)
    if alvo == op.cor:
        return
    visitados = {(x, y)}
    pilha = [(x, y)]
    while pilha:
        cx, cy = pilha.pop()
        yield (cx, cy), op.cor
        for viz in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if viz not in visitados and trabalho.contem(*viz) and trabalho.ler(*viz) == alvo:
                visitados.add(viz)
                pilha.append(viz)


def _px(op: Operacao) -> Iterator[tuple[Ponto, Celula]]:
    ox, oy = op.em
    for j, linha in enumerate(op.linhas):
        for i, caractere in enumerate(linha):
            if caractere == MANTER:
                continue
            yield (ox + i, oy + j), (None if caractere == APAGAR else caractere)


def _pares(numeros: Iterable[int]) -> list[Ponto]:
    lista = list(numeros)
    return [(lista[i], lista[i + 1]) for i in range(0, len(lista), 2)]


def _sem_repetir(pontos: Iterable[Ponto]) -> list[Ponto]:
    return list(dict.fromkeys(pontos))


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------
def para_png(grade: Grade, paleta: dict[str, tuple[int, int, int]]) -> bytes:
    """A grade como PNG RGBA, um pixel por célula, alpha só 0 ou 255."""
    imagem = Image.new("RGBA", (grade.largura, grade.altura), (0, 0, 0, 0))
    imagem.putdata(
        [
            (*paleta[valor], 255) if valor is not None else (0, 0, 0, 0)
            for valor in grade.celulas
        ]
    )
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()
