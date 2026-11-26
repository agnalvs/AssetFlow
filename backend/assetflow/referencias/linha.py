"""As medidas de linha do olho do app (lote F1, FUNDAMENTOS_E_FERRAMENTAS §4).

Sobre a máscara da cor do contorno (só quando o contorno é "escuro único":
nos outros tipos a cor mais comum da borda também é mancha, e a medida
acusaria o preenchimento):

* **cantos em L** — o pixel do meio de um degrau que encosta nos dois lados,
  sem ser canto proposital (os dois braços retos com 2 pixels ou mais);
* **dobras** — blocos 2×2 da cor do contorno; só onde a cor não tem miolo;
* **degraus fora de progressão** — nos trechos em escada (trechos de uma
  linha encadeados pela diagonal, num sentido só), o trecho menor ou maior
  que os dois vizinhos: 5, 2, 1, 2 tem um.

Tudo por 100 pixels de contorno, para comparar sprites de tamanhos diferentes.
Os limites do olho (``referencias.yaml``, seção ``olho:``) vieram dos pacotes
de referência: ``scripts/calibrar_linha.py`` os mede de novo.

A gaveta tem a sua própria limpeza (``engines/desenhista/linha.py``), com a
mesma regra de canto: o teste de fronteiras não deixa uma importar a outra, e
``tests/test_linha.py`` confere que as duas concordam.
"""

from __future__ import annotations

from typing import Any

import numpy as np

__all__ = ["medir_linha"]

Ponto = tuple[int, int]
_QUATRO = ((1, 0), (-1, 0), (0, 1), (0, -1))
_OITO = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)


def _mascara(rgba: np.ndarray, cor: str) -> set[Ponto]:
    r, g, b = int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16)
    sim = (rgba[..., 3] > 0) & (rgba[..., 0] == r) & (rgba[..., 1] == g) & (rgba[..., 2] == b)
    ys, xs = np.nonzero(sim)
    return {(int(x), int(y)) for x, y in zip(xs, ys)}


def _vizinhos(p: Ponto, mascara: set[Ponto], direcoes) -> list[Ponto]:
    return [(p[0] + dx, p[1] + dy) for dx, dy in direcoes if (p[0] + dx, p[1] + dy) in mascara]


def _simples(p: Ponto, mascara: set[Ponto]) -> bool:
    """Tirar ``p`` não separa os vizinhos dele (a mesma regra da gaveta)."""
    vizinhos = _vizinhos(p, mascara, _OITO)
    if len(vizinhos) < 2:
        return False
    restantes, pilha, vistos = set(vizinhos), [vizinhos[0]], {vizinhos[0]}
    while pilha:
        for q in _vizinhos(pilha.pop(), restantes, _OITO):
            if q not in vistos:
                vistos.add(q)
                pilha.append(q)
    return vistos == restantes


def _canto_em_l(p: Ponto, mascara: set[Ponto]) -> bool:
    quatro = _vizinhos(p, mascara, _QUATRO)
    if len(quatro) != 2:
        return False
    h = next((q for q in quatro if q[1] == p[1]), None)
    v = next((q for q in quatro if q[0] == p[0]), None)
    if h is None or v is None or (h[0], v[1]) in mascara:
        return False
    if not _simples(p, mascara):
        return False  # junção: tirar o pixel separaria um terceiro traço
    return not ((2 * h[0] - p[0], h[1]) in mascara and (v[0], 2 * v[1] - p[1]) in mascara)


def _trechos(mascara: set[Ponto], eixo: int) -> list[tuple[int, int, int]]:
    """Trechos retos: ``(fixo, de, ate)`` por linha (eixo 1) ou coluna (eixo 0)."""
    por_fixo: dict[int, list[int]] = {}
    for p in mascara:
        por_fixo.setdefault(p[eixo], []).append(p[1 - eixo])
    trechos = []
    for fixo, valores in por_fixo.items():
        valores.sort()
        inicio = anterior = valores[0]
        for valor in valores[1:]:
            if valor != anterior + 1:
                trechos.append((fixo, inicio, anterior))
                inicio = valor
            anterior = valor
        trechos.append((fixo, inicio, anterior))
    return trechos


def _calombos(mascara: set[Ponto]) -> list[Ponto]:
    achados: list[Ponto] = []
    for eixo in (1, 0):
        trechos = _trechos(mascara, eixo)
        por_inicio = {(t[0], t[1]): t for t in trechos}
        por_fim = {(t[0], t[2]): t for t in trechos}
        for sentido in (1, -1):
            seguinte = {}
            for t in trechos:
                proximo = (
                    por_inicio.get((t[0] + 1, t[2] + 1)) if sentido == 1
                    else por_fim.get((t[0] + 1, t[1] - 1))
                )
                if proximo is not None:
                    seguinte[t] = proximo
            tem_anterior = set(seguinte.values())
            for t in trechos:
                if t in tem_anterior or t not in seguinte:
                    continue
                cadeia = [t]
                while cadeia[-1] in seguinte and len(cadeia) < 512:
                    cadeia.append(seguinte[cadeia[-1]])
                tamanhos = [c[2] - c[1] + 1 for c in cadeia]
                for i in range(1, len(cadeia) - 1):
                    a, b, c = tamanhos[i - 1], tamanhos[i], tamanhos[i + 1]
                    if (b < a and b < c) or (b > a and b > c):
                        fixo, de, _ = cadeia[i]
                        achados.append((de, fixo) if eixo == 1 else (fixo, de))
    return achados


def medir_linha(rgba: np.ndarray, cor_do_contorno: str | None) -> dict[str, Any] | None:
    """Cantos em L, dobras e degraus fora de progressão no contorno escuro.

    ``None`` sem contorno de uma cor só, ou com menos de 8 pixels dele.
    """
    if not cor_do_contorno:
        return None
    mascara = _mascara(rgba, cor_do_contorno)
    if len(mascara) < 8:
        return None
    cantos = sorted((p for p in mascara if _canto_em_l(p, mascara)), key=lambda p: (p[1], p[0]))
    com_miolo = any(len(_vizinhos(p, mascara, _QUATRO)) == 4 for p in mascara)
    dobras = (
        None
        if com_miolo
        else sorted(
            ((x, y) for x, y in mascara if {(x + 1, y), (x, y + 1), (x + 1, y + 1)} <= mascara),
            key=lambda p: (p[1], p[0]),
        )
    )
    calombos = sorted(set(_calombos(mascara)), key=lambda p: (p[1], p[0]))
    total = len(mascara)

    def taxa(n: int) -> float:
        return round(100 * n / total, 2)

    return {
        "pixels": total,
        "cantos": cantos,
        "dobras": dobras,
        "calombos": calombos,
        "cantos_por_100": taxa(len(cantos)),
        "dobras_por_100": None if dobras is None else taxa(len(dobras)),
        "degraus_por_100": taxa(len(calombos)),
    }
