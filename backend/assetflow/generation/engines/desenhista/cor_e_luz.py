"""Cor e luz na receita (lote F2 do FUNDAMENTOS_E_FERRAMENTAS.md, seções 3 e 5).

Comandos opcionais: a receita continua podendo pintar tudo à mão. Estes deixam
o Claude pedir o resultado — "sombreie esta camada como uma esfera" — e o app
aplica a regra sempre do mesmo jeito:

``rampas`` (na raiz)
    ``[{"chaves": "abc", "base": "#rrggbb", "desvio": 12}]``: gera os tons do
    escuro ao claro em volta da cor base. Ao escurecer, o matiz caminha para o
    azul; ao clarear, para o amarelo, ``desvio`` graus por passo (até 20, o
    máximo do Pixelblog); a saturação cai nas pontas.
``luz`` (na raiz)
    de onde vem a luz: ``cima-esquerda`` (padrão), ``cima-direita``, ``cima``,
    ``esquerda`` ou ``direita``.
``material`` (na camada)
    ``metal``, ``vidro``, ``tecido``, ``pele``, ``madeira``, ``pelo`` ou
    ``pedra``: muda o contraste do ``sombrear`` e o tamanho do ``brilho``.
``{"sombrear": volume, "rampa": "abc"}``
    redistribui os tons da rampa nos pixels **desta camada** que já usam uma
    das chaves dela, pela direção da luz e pelo volume: ``esfera``,
    ``cilindro`` (vertical), ``caixa`` (topo claro, frente média, lado oposto à
    luz escuro) ou ``plano``. A luz vem de um lado, nunca acompanha o contorno.
``{"brilho": "c", "sobre": "ab"}``
    o ponto de brilho do lado da luz, do tamanho que o material pede (metal e
    vidro, 2 px; o vidro ganha um segundo brilho do lado oposto; os foscos, 1).
``{"oclusao": "camada", "cor": "a"}``
    a sombra de contato: os pixels desta camada que encostam na outra (já
    desenhada) ficam com a cor mais escura.
``{"sombra_projetada": "camada de trás", "cor": "a", "distancia": 1}``
    esta camada escurece a de trás, do lado oposto à luz.

Os efeitos de luz não valem em camada com ``espelho``: a cópia levaria a luz
para o lado errado. Sombreie numa camada sem espelho, depois dela.
"""

from __future__ import annotations

import colorsys
from collections.abc import Iterable, Mapping

__all__ = [
    "EFEITOS",
    "LUZES",
    "MATERIAIS",
    "VOLUMES",
    "brilho",
    "gerar_rampa",
    "oclusao",
    "sombra_projetada",
    "sombrear",
    "vetor_da_luz",
]

RGB = tuple[int, int, int]
Ponto = tuple[int, int]

EFEITOS = ("sombrear", "brilho", "oclusao", "sombra_projetada")
VOLUMES = ("esfera", "cilindro", "caixa", "plano")
LUZES = {
    "cima-esquerda": (-1.0, -1.0),
    "cima-direita": (1.0, -1.0),
    "cima": (0.0, -1.0),
    "esquerda": (-1.0, 0.0),
    "direita": (1.0, 0.0),
}
#: Material -> (fator de contraste do sombrear, tamanho do brilho, segundo brilho).
MATERIAIS = {
    "metal": (1.5, 2, False),
    "vidro": (1.4, 2, True),
    "tecido": (0.7, 1, False),
    "pele": (0.75, 1, False),
    "madeira": (0.8, 1, False),
    "pelo": (0.7, 1, False),
    "pedra": (1.1, 1, False),
}
#: Desvio de matiz máximo por passo de rampa (Raymond Schlitter, Pixelblog 1).
DESVIO_MAXIMO = 20


def vetor_da_luz(luz: str) -> tuple[float, float]:
    """O vetor normalizado que aponta **para** a luz."""
    x, y = LUZES[luz]
    norma = (x * x + y * y) ** 0.5
    return (x / norma, y / norma)


# ---------------------------------------------------------------------------
# Rampa
# ---------------------------------------------------------------------------
def _caminhar_matiz(h: float, alvo: float, passo: float) -> float:
    """Anda ``passo`` graus de ``h`` para ``alvo`` pelo arco menor, sem passar dele."""
    diferenca = (alvo - h + 540) % 360 - 180
    if abs(diferenca) <= passo:
        return alvo % 360
    return (h + passo * (1 if diferenca > 0 else -1)) % 360


def gerar_rampa(base: RGB, tons: int, desvio: float = 12, base_em: int | None = None) -> list[RGB]:
    """Os ``tons`` da rampa, do escuro ao claro, com ``base`` na posição ``base_em``."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in base))
    h *= 360
    meio = (tons - 1) // 2 if base_em is None else base_em
    rampa: list[RGB] = []
    for i in range(tons):
        passo = i - meio
        hi, si, vi = h, s, v
        for _ in range(abs(passo)):
            if passo < 0:  # mais escuro: para o azul, brilho cai
                hi = _caminhar_matiz(hi, 240, desvio)
                vi = vi * 0.72
            else:  # mais claro: para o amarelo, brilho sobe
                hi = _caminhar_matiz(hi, 60, desvio)
                vi = vi + (1 - vi) * 0.5
        si = max(0.0, min(1.0, s * (1 - 0.12 * abs(passo))))
        r, g, b = colorsys.hsv_to_rgb(hi / 360, si, max(0.0, min(1.0, vi)))
        rampa.append((round(r * 255), round(g * 255), round(b * 255)))
    return rampa


# ---------------------------------------------------------------------------
# Efeitos sobre as escritas de uma camada
# ---------------------------------------------------------------------------
def _caixa(pontos: Iterable[Ponto]) -> tuple[int, int, int, int]:
    xs = [x for x, _ in pontos]
    ys = [y for _, y in pontos]
    return min(xs), min(ys), max(xs), max(ys)


def _uv(ponto: Ponto, caixa: tuple[int, int, int, int]) -> tuple[float, float]:
    x0, y0, x1, y1 = caixa
    return (
        (ponto[0] - x0 + 0.5) / (x1 - x0 + 1),
        (ponto[1] - y0 + 0.5) / (y1 - y0 + 1),
    )


def sombrear(
    escritas: Mapping[Ponto, str | None],
    rampa: str,
    volume: str,
    luz: str,
    material: str | None = None,
) -> dict[Ponto, str]:
    """As novas chaves dos pixels desta camada que usam a rampa."""
    regiao = [p for p, chave in escritas.items() if chave is not None and chave in rampa]
    if not regiao:
        return {}
    caixa = _caixa(regiao)
    lx, ly = vetor_da_luz(luz)
    contraste = MATERIAIS.get(material or "", (1.0, 1, False))[0]
    tons = len(rampa)
    novas: dict[Ponto, str] = {}
    for ponto in regiao:
        u, v = _uv(ponto, caixa)
        if volume == "esfera":
            hx, hy = 0.5 + 0.3 * lx, 0.5 + 0.3 * ly
            intensidade = 1 - (((u - hx) ** 2 + (v - hy) ** 2) ** 0.5) / 0.85
        elif volume == "cilindro":
            if abs(lx) > 0.1:
                hx = 0.5 + 0.3 * lx
                intensidade = 1 - abs(u - hx) / 0.75
            else:
                intensidade = 1 - v
        elif volume == "caixa":
            longe = u > 0.72 if lx <= 0 else u < 0.28
            if v < 0.28 and ly < 0:
                intensidade = 0.95
            elif longe and abs(lx) > 0.1:
                intensidade = 0.1
            else:
                intensidade = 0.55
        else:  # plano
            produto = (u - 0.5) * lx + (v - 0.5) * ly
            intensidade = 0.5 + produto * 0.8
        intensidade = 0.5 + (intensidade - 0.5) * contraste
        intensidade = max(0.0, min(1.0, intensidade))
        novas[ponto] = rampa[min(tons - 1, max(0, round(intensidade * (tons - 1))))]
    return novas


def brilho(
    escritas: Mapping[Ponto, str | None],
    chave: str,
    sobre: str,
    luz: str,
    material: str | None = None,
) -> dict[Ponto, str]:
    """O ponto de brilho do lado da luz (e o reflexo do vidro, do lado oposto)."""
    regiao = [p for p, c in escritas.items() if c is not None and c in sobre]
    if not regiao:
        return {}
    caixa = _caixa(regiao)
    lx, ly = vetor_da_luz(luz)
    _, tamanho, segundo = MATERIAIS.get(material or "", (1.0, 1, False))

    def para_a_luz(p: Ponto) -> float:
        u, v = _uv(p, caixa)
        # Perto da borda do lado da luz, mas não em cima dela: o miolo do
        # canto iluminado (um passo para dentro).
        return (u - 0.5) * lx + (v - 0.5) * ly - 0.15 * abs((u - 0.5) * lx + (v - 0.5) * ly - 0.3)

    ordenados = sorted(regiao, key=lambda p: (-para_a_luz(p), p[1], p[0]))
    escolhidos = [ordenados[0]]
    for p in ordenados[1:]:
        if len(escolhidos) >= tamanho:
            break
        if any(abs(p[0] - q[0]) + abs(p[1] - q[1]) == 1 for q in escolhidos):
            escolhidos.append(p)
    novas = dict.fromkeys(escolhidos, chave)
    if segundo:
        oposto = min(regiao, key=lambda p: (para_a_luz(p), p[1], p[0]))
        novas[oposto] = chave
    return novas


def _vizinhos(p: Ponto) -> tuple[Ponto, ...]:
    x, y = p
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def oclusao(
    escritas: Mapping[Ponto, str | None],
    donos: Mapping[Ponto, int | None],
    outra: int,
    cor: str,
    sobre: str | None = None,
) -> dict[Ponto, str]:
    """Os pixels desta camada que encostam (pelos 4 lados) na camada ``outra``."""
    novas: dict[Ponto, str] = {}
    for ponto, chave in escritas.items():
        if chave is None or (sobre and chave not in sobre):
            continue
        if any(donos.get(v) == outra for v in _vizinhos(ponto)):
            novas[ponto] = cor
    return novas


def sombra_projetada(
    escritas: Mapping[Ponto, str | None],
    donos: Mapping[Ponto, int | None],
    atras: int,
    cor: str,
    luz: str,
    distancia: int = 1,
    sobre: str | None = None,
    chaves: Mapping[Ponto, str | None] | None = None,
) -> dict[Ponto, str]:
    """Os pixels da camada de trás que esta camada sombreia, do lado oposto à luz."""
    lx, ly = LUZES[luz]
    dx = 0 if lx == 0 else (1 if lx < 0 else -1)
    dy = 0 if ly == 0 else (1 if ly < 0 else -1)
    novas: dict[Ponto, str] = {}
    minhas = {p for p, c in escritas.items() if c is not None}
    for x, y in minhas:
        for passo in range(1, distancia + 1):
            alvo = (x + dx * passo, y + dy * passo)
            if alvo in minhas or donos.get(alvo) != atras:
                continue
            if sobre and chaves is not None and (chaves.get(alvo) or "") not in sobre:
                continue
            novas[alvo] = cor
    return novas
