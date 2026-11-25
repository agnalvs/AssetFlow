"""O medidor: o que dá para medir num sprite com código comum, sem IA.

Mede o **conteúdo** de cada quadro — os pixels opacos —, nunca o corpo: um
chapéu, um penacho ou uma espada erguida entram na altura. Separar cabeça,
tronco e membros exigiria entender o desenho, e isso o medidor não faz; o
que não dá para medir com confiança fica de fora em vez de virar chute.

    medida               como                                         confiança
    escala do arquivo    blocos k×k iguais em todo o desenho          alta
    quadro               grade informada, "(LxA)" no nome, ou         alta / média
                         recortes separados por linhas transparentes
    altura, largura      caixa dos pixels opacos                      alta (é conteúdo)
    cores, paleta        cores opacas únicas                          alta
    contorno             pixels opacos vizinhos do transparente,      alta (escuro, colorido,
                         comparados com o vizinho de dentro           nenhum); média (seletivo)
    grupos de matiz      cores agrupadas por matiz; neutros à parte   média
    rampas prováveis     grupo ordenado por luminância cujas cores    média
                         vizinhas na rampa se encostam no desenho
    ocupação, chão,      só quando o quadro é conhecido               alta
    folga, margem
"""

from __future__ import annotations

import colorsys
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
from PIL import Image

__all__ = [
    "LIMIAR_ALPHA",
    "MAX_PIXELS",
    "Recorte",
    "carregar",
    "carregar_com_fundo",
    "detectar_escala",
    "fatiar",
    "medir_quadro",
    "quadro_do_nome",
]

#: Alpha a partir do qual o pixel conta como opaco (o mesmo do Pixel Exact).
LIMIAR_ALPHA = 128
#: Teto de pixels por imagem: arquivo baixado é dado não confiável.
MAX_PIXELS = 16_000_000

#: Diferença de luminância para um pixel de borda contar como "mais escuro".
_MARGEM_ESCURO = 0.02
#: Saturação e brilho abaixo dos quais a cor é neutra (cinza, preto, branco).
_NEUTRO_S, _NEUTRO_V = 0.15, 0.12
#: Salto de matiz que separa dois grupos.
_SALTO_DE_MATIZ = 30 / 360


@dataclass(frozen=True, slots=True)
class Recorte:
    """Onde um quadro está na imagem, em pixels lógicos (escala 1×)."""

    x: int
    y: int
    largura: int
    altura: int
    #: ``True`` quando o tamanho do quadro é o de verdade (grade ou imagem
    #: inteira). Um recorte por linhas transparentes é só a caixa do conteúdo:
    #: ocupação, chão e margem não existem para ele.
    conhecido: bool
    #: A linha da folha, para contar frames por animação.
    linha: int = 0


def carregar(caminho: Path) -> np.ndarray:
    """O PNG como RGBA ``(altura, largura, 4)``; transparente vira zero.

    Fundo sólido (ver :func:`carregar_com_fundo`) também vira transparente.
    """
    return carregar_com_fundo(caminho)[0]


def carregar_com_fundo(caminho: Path) -> tuple[np.ndarray, str | None]:
    """O PNG como RGBA, mais a cor do fundo sólido que foi removido, se houve.

    Há pacotes sem transparência: a folha vem em RGB, com uma cor de fundo.
    Sem tirar esse fundo, o "conteúdo" seria o quadro inteiro. Só se remove
    quando não há nenhum pixel transparente, os quatro cantos têm a mesma cor
    e essa cor cobre ao menos 30% da imagem — senão, a cor do canto pode ser
    desenho, e a imagem fica como veio.
    """
    with Image.open(caminho) as imagem:
        if imagem.width * imagem.height > MAX_PIXELS:
            raise ValueError(f"{caminho.name}: {imagem.width}×{imagem.height} passa do teto de pixels")
        rgba = np.asarray(imagem.convert("RGBA"), dtype=np.uint8).copy()
    rgba[rgba[..., 3] < LIMIAR_ALPHA] = 0
    if (rgba[..., 3] == 0).any():
        return rgba, None
    cantos = {tuple(int(v) for v in rgba[y, x, :3]) for y in (0, -1) for x in (0, -1)}
    if len(cantos) != 1:
        return rgba, None
    cor = cantos.pop()
    fundo = (rgba[..., :3] == np.array(cor, dtype=np.uint8)).all(axis=-1)
    if fundo.mean() < 0.3:
        return rgba, None
    rgba[fundo] = 0
    return rgba, _hex((cor[0] << 16) | (cor[1] << 8) | cor[2])


def detectar_escala(rgba: np.ndarray) -> int:
    """O fator inteiro em que o desenho foi ampliado (1 quando não foi)."""
    altura, largura = rgba.shape[:2]
    if not (rgba[..., 3] > 0).any():
        return 1
    for fator in (8, 6, 5, 4, 3, 2):
        if altura % fator or largura % fator:
            continue
        blocos = rgba.reshape(altura // fator, fator, largura // fator, fator, 4)
        if (blocos == blocos[:, :1, :, :1, :]).all():
            return fator
    return 1


def quadro_do_nome(nome: str) -> tuple[int, int] | None:
    """``Idle (78x58).png`` -> ``(78, 58)``: o tamanho do quadro escrito no nome."""
    casou = re.search(r"\((\d{1,4})\s*[xX]\s*(\d{1,4})\)", nome)
    return (int(casou.group(1)), int(casou.group(2))) if casou else None


def fatiar(rgba: np.ndarray, quadro: tuple[int, int] | None) -> list[Recorte]:
    """Os quadros não vazios da imagem (já em 1×)."""
    altura, largura = rgba.shape[:2]
    opaco = rgba[..., 3] > 0
    if quadro and largura % quadro[0] == 0 and altura % quadro[1] == 0:
        ql, qa = quadro
        recortes = []
        for linha, y in enumerate(range(0, altura, qa)):
            for x in range(0, largura, ql):
                if opaco[y : y + qa, x : x + ql].any():
                    recortes.append(Recorte(x, y, ql, qa, conhecido=True, linha=linha))
        return recortes

    # Sem grade: separa por faixas e colunas totalmente transparentes.
    caixas: list[Recorte] = []
    for linha, (y0, y1) in enumerate(_trechos(opaco.any(axis=1))):
        faixa = opaco[y0:y1]
        for x0, x1 in _trechos(faixa.any(axis=0)):
            ys = np.nonzero(faixa[:, x0:x1].any(axis=1))[0]
            topo, base = int(ys[0]), int(ys[-1])
            caixas.append(Recorte(int(x0), int(y0) + topo, int(x1 - x0), base - topo + 1, False, linha))
    # Fiapo solto (faísca, sombra destacada) não é um quadro.
    caixas = [c for c in caixas if c.altura >= 3 and opaco[c.y : c.y + c.altura, c.x : c.x + c.largura].sum() >= 4]
    if len(caixas) == 1:
        return [Recorte(0, 0, largura, altura, conhecido=True)]
    return caixas


def _trechos(ocupado: np.ndarray) -> list[tuple[int, int]]:
    trechos, inicio = [], None
    for i, valor in enumerate(ocupado):
        if valor and inicio is None:
            inicio = i
        elif not valor and inicio is not None:
            trechos.append((inicio, i))
            inicio = None
    if inicio is not None:
        trechos.append((inicio, len(ocupado)))
    return trechos


# ---------------------------------------------------------------------------
# Medidas de um quadro
# ---------------------------------------------------------------------------
def medir_quadro(rgba: np.ndarray, *, conhecido: bool) -> dict[str, Any] | None:
    """As medidas de um quadro já recortado; ``None`` se ele estiver vazio."""
    opaco = rgba[..., 3] > 0
    if not opaco.any():
        return None
    ys, xs = np.nonzero(opaco)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    altura, largura = y1 - y0 + 1, x1 - x0 + 1
    opacos = int(opaco.sum())

    codigos = (rgba[..., 0].astype(np.int64) << 16) | (rgba[..., 1].astype(np.int64) << 8) | rgba[..., 2]
    unicos, contagens = np.unique(codigos[opaco], return_counts=True)
    paleta = {_hex(int(c)): int(n) for c, n in zip(unicos, contagens)}

    contorno = _contorno(rgba, opaco, codigos)
    grupos = _grupos_de_matiz(paleta, excluir=contorno["cor"] if contorno["tipo"] == "escuro único" else None)
    rampas = _rampas(grupos, paleta, _vizinhas(codigos, opaco))

    medidas: dict[str, Any] = {
        "altura": altura,
        "largura": largura,
        "cores": len(paleta),
        "paleta": dict(sorted(paleta.items(), key=lambda item: -item[1])[:16]),
        "contorno": contorno,
        "grupos": len(grupos),
        "tons_por_grupo": float(median(len(g) for g in grupos)) if grupos else None,
        "rampas": rampas,
        "preenchimento": round(opacos / (altura * largura), 4),
        "hash": hashlib.sha1(rgba[y0 : y1 + 1, x0 : x1 + 1].tobytes()).hexdigest(),
    }
    if conhecido:
        qa, ql = rgba.shape[:2]
        medidas.update(
            ocupacao=round(opacos / (ql * qa), 4),
            chao=y1,
            folga_topo=y0,
            margem=min(x0, y0, ql - 1 - x1, qa - 1 - y1),
        )
    return medidas


def _contorno(rgba: np.ndarray, opaco: np.ndarray, codigos: np.ndarray) -> dict[str, Any]:
    """Tipo e cor do contorno, comparando a borda com o vizinho de dentro."""
    cerca = np.pad(opaco, 1)
    cercado = cerca[:-2, 1:-1] & cerca[2:, 1:-1] & cerca[1:-1, :-2] & cerca[1:-1, 2:]
    borda = opaco & ~cercado
    miolo = opaco & cercado
    contagem = Counter(int(c) for c in codigos[borda])
    cor, vezes = contagem.most_common(1)[0]
    dominante = vezes / sum(contagem.values())

    lum = _luminancia(rgba)
    soma = np.zeros_like(lum)
    vizinhos = np.zeros(lum.shape, dtype=np.int32)
    lum_miolo = np.pad(np.where(miolo, lum, 0.0), 1)
    tem_miolo = np.pad(miolo.astype(np.int32), 1)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        fatia = (slice(1 + dy, lum.shape[0] + 1 + dy), slice(1 + dx, lum.shape[1] + 1 + dx))
        soma += lum_miolo[fatia]
        vizinhos += tem_miolo[fatia]
    comparaveis = borda & (vizinhos > 0)
    if not comparaveis.any():
        return {"tipo": "indefinido", "cor": _hex(cor), "escuro": None, "dominante": round(dominante, 3)}
    media = soma[comparaveis] / vizinhos[comparaveis]
    escuro = float((lum[comparaveis] < media - _MARGEM_ESCURO).mean())

    if escuro >= 0.7 and dominante >= 0.6:
        tipo = "escuro único"
    elif escuro >= 0.7:
        tipo = "colorido"
    elif escuro >= 0.4:
        tipo = "seletivo ou misto"
    else:
        tipo = "nenhum"
    return {"tipo": tipo, "cor": _hex(cor), "escuro": round(escuro, 3), "dominante": round(dominante, 3)}


def _grupos_de_matiz(paleta: dict[str, int], *, excluir: str | None) -> list[list[str]]:
    """Cores agrupadas por matiz, cada grupo do escuro ao claro; neutros à parte."""
    neutros, cromaticas = [], []
    for cor in paleta:
        if cor == excluir:
            continue
        h, s, v = colorsys.rgb_to_hsv(*(int(cor[i : i + 2], 16) / 255 for i in (1, 3, 5)))
        (neutros if s < _NEUTRO_S or v < _NEUTRO_V else cromaticas).append((h, cor))

    grupos: list[list[str]] = []
    if cromaticas:
        cromaticas.sort()
        matizes = [h for h, _ in cromaticas]
        # O círculo de matiz começa no maior salto, para um vermelho não se
        # partir em 0° e 359°.
        saltos = [(matizes[(i + 1) % len(matizes)] - matizes[i]) % 1.0 for i in range(len(matizes))]
        inicio = (int(np.argmax(saltos)) + 1) % len(cromaticas) if len(cromaticas) > 1 else 0
        ordem = cromaticas[inicio:] + cromaticas[:inicio]
        atual = [ordem[0][1]]
        for (h_antes, _), (h, cor) in pairwise(ordem):
            if (h - h_antes) % 1.0 > _SALTO_DE_MATIZ:
                grupos.append(atual)
                atual = []
            atual.append(cor)
        grupos.append(atual)
    if neutros:
        grupos.append([cor for _, cor in neutros])
    return [sorted(grupo, key=_luminancia_hex) for grupo in grupos]


def _vizinhas(codigos: np.ndarray, opaco: np.ndarray) -> set[tuple[int, int]]:
    """Pares de cores diferentes que se encostam (lado a lado ou em cima e embaixo)."""
    pares: set[tuple[int, int]] = set()
    for a, b, ok in (
        (codigos[:, :-1], codigos[:, 1:], opaco[:, :-1] & opaco[:, 1:]),
        (codigos[:-1, :], codigos[1:, :], opaco[:-1, :] & opaco[1:, :]),
    ):
        diferentes = ok & (a != b)
        for x, y in zip(a[diferentes].tolist(), b[diferentes].tolist()):
            pares.add((min(x, y), max(x, y)))
    return pares


def _rampas(grupos: list[list[str]], paleta: dict[str, int], vizinhas: set[tuple[int, int]]) -> list[dict[str, Any]]:
    """Os grupos com mais de uma cor, os mais usados primeiro, e se parecem rampa."""
    rampas = []
    for grupo in sorted(grupos, key=lambda g: -sum(paleta[c] for c in g)):
        if len(grupo) < 2:
            continue
        codigos = [int(c[1:], 16) for c in grupo]
        provavel = all(
            (min(a, b), max(a, b)) in vizinhas for a, b in pairwise(codigos)
        )
        rampas.append({"cores": grupo, "provavel": provavel})
    return rampas[:4]


def _luminancia(rgba: np.ndarray) -> np.ndarray:
    canal = rgba[..., :3].astype(np.float64) / 255
    linear = np.where(canal <= 0.04045, canal / 12.92, ((canal + 0.055) / 1.055) ** 2.4)
    return linear @ np.array([0.2126, 0.7152, 0.0722])


def _luminancia_hex(cor: str) -> float:
    rgb = np.array([[[int(cor[i : i + 2], 16) for i in (1, 3, 5)] + [255]]], dtype=np.uint8)
    return float(_luminancia(rgb)[0, 0])


def _hex(codigo: int) -> str:
    return f"#{codigo:06x}"
