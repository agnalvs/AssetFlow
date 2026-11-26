"""O olho do app: o desenho novo medido contra as referências, sem IA.

Fase B2 do plano do app (adianta parte da Fase 5 antiga). O mesmo medidor que
mede os pacotes mede o desenho, e o laudo do ``desenhar`` diz **só os
desvios**, em frases curtas, com a posição quando há:

    medida                       comparada com                      posição
    preenchimento da caixa       porte (p_baixo–p_alto)             caixa
    largura ÷ altura             porte                              caixa
    altura do conteúdo           faixa do porte                     caixa
    número de cores              porte                              —
    tons por grupo de matiz      estilo                             grupo de 1 tom
    contorno (tipo, fração       estilo                             pixels de borda
      escura)                                                         mais claros
    rampas prováveis             estilo                             grupo sem rampa
    contraste entre partes       limiar fixo (camadas da receita)   camadas e contato

**O olho só informa.** Nenhum desvio reprova um desenho nem muda a nota: quem
decide é o validador (o que é técnico) e o olhar do Claude (o que é feio). A
única exceção é :func:`repete_o_exemplo`: um desenho cuja silhueta coincide com
a do exemplo de construção mostrado no pedido é não aprovado, porque o exemplo
nunca é base de um asset.

O contraste entre partes vizinhas não se compara com as referências: elas não
têm camadas. Por grupo de matiz ele não serve (pele, couro e madeira caem no
mesmo grupo, e até nas referências o p10 fica perto de zero); por camada da
receita, sim — a gaveta grava de qual camada é cada pixel. Duas camadas que se
tocam (lado a lado, ou através de um contorno de 1 px) com valores medianos
(L*) a menos de ``contraste_minimo`` uma da outra "têm o mesmo valor".

Os limiares estão em ``config/pixel_knowledge/referencias.yaml`` (``olho:``),
todos ``a_calibrar``. Sem um deles, a verificação correspondente não roda.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .colecao import ParteDaLinha, ReferenciasAtivas, distribuicao, quantis
from .medidor import _grupos_de_matiz, _luminancia, medir_quadro
from .pacote import ConfiguracaoDoOlho

__all__ = [
    "MAX_POSICOES",
    "SIMBOLOS_DE_CAMADA",
    "Desvio",
    "RelatorioDoOlho",
    "bordas_claras",
    "contraste_por_camada",
    "iou_com_o_exemplo",
    "olhar_desenho",
    "repete_o_exemplo",
]

#: Teto de posições numa frase.
MAX_POSICOES = 8
#: Pares de camadas que uma frase de contraste lista, no máximo.
MAX_PARES = 4
#: Contato mínimo (pixels) para duas camadas contarem como vizinhas.
CONTATO_MINIMO = 3
#: Os símbolos do mapa de camadas que a gaveta desenhista grava (a camada
#: ``i`` é o i-ésimo). Repetidos aqui porque a estante não importa gaveta; o
#: teste do olho confere que são os mesmos.
SIMBOLOS_DE_CAMADA = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True, slots=True)
class Desvio:
    codigo: str
    texto: str


@dataclass(frozen=True, slots=True)
class RelatorioDoOlho:
    """O que o olho viu: a linha de cabeçalho, os desvios e as medidas cruas."""

    cabecalho: str
    desvios: tuple[Desvio, ...] = ()
    medidas: dict[str, Any] = field(default_factory=dict)

    def linhas(self) -> list[str]:
        if not self.desvios:
            return [f"{self.cabecalho}: nada fora da faixa"]
        return [f"{self.cabecalho}:", *(f"- {d.texto}" for d in self.desvios)]

    def como_dict(self) -> dict[str, Any]:
        return {
            "cabecalho": self.cabecalho,
            "desvios": [{"codigo": d.codigo, "texto": d.texto} for d in self.desvios],
            "medidas": self.medidas,
        }


def olhar_desenho(
    rgba: np.ndarray,
    referencias: ReferenciasAtivas | None,
    *,
    tipo: str,
    corpo: str | None,
    altura_do_corpo: int | None,
    mapa_de_camadas: tuple[Sequence[str], Sequence[str]] | None = None,
) -> RelatorioDoOlho:
    """Os desvios do desenho em relação às referências do mesmo porte."""
    config = referencias.configuracao.olho if referencias is not None else ConfiguracaoDoOlho()
    medidas = medir_quadro(rgba, conhecido=True)
    if medidas is None:
        return RelatorioDoOlho(cabecalho="olho do app: desenho vazio")
    ys, xs = np.nonzero(rgba[..., 3] > 0)
    caixa = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    onde_caixa = f"caixa x{caixa[0]}–{caixa[2]} y{caixa[1]}–{caixa[3]}"
    contorno = medidas["contorno"]
    cor_do_contorno = contorno["cor"] if contorno["tipo"] == "escuro único" else None
    desvios: list[Desvio] = []

    porte = estilo = ParteDaLinha(falta="sem referências")
    if referencias is not None and not referencias.esta_vazia:
        porte = referencias.porte(tipo, corpo, altura_do_corpo)
        estilo = referencias.estilo(tipo, corpo)
    faixa = referencias.faixa(altura_do_corpo) if referencias is not None else None
    tem_faixas = config.p_baixo is not None and config.p_alto is not None
    fracoes = (config.p_baixo or 0.1, config.p_alto or 0.9)

    if porte.suficiente and tem_faixas:
        quadros = list(porte.quadros)
        _comparar(
            desvios, "PREENCHIMENTO", quadros, lambda q: q.preenchimento, medidas["preenchimento"],
            fracoes, lambda v: f"{round(v * 100)}%",
            lambda v, a, b: f"preenchimento {v} da caixa ({onde_caixa}); referências {a}–{b}",
        )
        _comparar(
            desvios, "PROPORCAO", quadros, lambda q: q.largura / q.altura,
            medidas["largura"] / medidas["altura"], fracoes, lambda v: _num(v, 2) + "×",
            lambda v, a, b: f"largura {v} a altura ({onde_caixa}); referências {a}–{b}",
        )
        _comparar(
            desvios, "CORES", quadros, lambda q: q.cores, medidas["cores"], fracoes,
            lambda v: f"{round(v)}", lambda v, a, b: f"{v} cores; referências {a}–{b}",
        )
        if faixa is not None and not faixa[0] <= medidas["altura"] <= faixa[1]:
            desvios.append(
                Desvio(
                    "ALTURA",
                    f"altura do conteúdo {medidas['altura']} px ({onde_caixa}); o porte das "
                    f"referências é {faixa[0]}–{faixa[1]} px",
                )
            )

    if estilo.suficiente:
        quadros = list(estilo.quadros)
        if tem_faixas:
            _tons(desvios, quadros, medidas, fracoes, rgba, cor_do_contorno)
            _rampas(desvios, quadros, medidas, fracoes)
        _contorno(desvios, quadros, contorno, fracoes if tem_faixas else None, rgba)

    pares = []
    if mapa_de_camadas is not None and config.contraste_minimo is not None:
        nomes, linhas = mapa_de_camadas
        pares = contraste_por_camada(rgba, nomes, linhas, cor_do_contorno)
        iguais = [p for p in pares if p["dL"] < config.contraste_minimo]
        if iguais:
            iguais = sorted(iguais, key=lambda p: p["dL"])[:MAX_PARES]
            xs_ = [x for p in iguais for x, _ in p["contato"]]
            ys_ = [y for p in iguais for _, y in p["contato"]]
            texto = ", ".join(f"{p['a']} × {p['b']} (ΔL* {round(p['dL'])})" for p in iguais)
            desvios.append(
                Desvio(
                    "VALOR",
                    f"partes vizinhas com o mesmo valor: {texto}, em x{min(xs_)}–{max(xs_)} "
                    f"y{min(ys_)}–{max(ys_)}",
                )
            )

    if porte.suficiente:
        cabecalho = (
            f"olho do app (contra {len(porte.quadros)} quadros de {porte.pacotes} pacotes do "
            f"mesmo porte, {faixa[0]}–{faixa[1]} px de altura)"
        )
    elif estilo.suficiente:
        cabecalho = (
            f"olho do app (contra o estilo de {len(estilo.quadros)} quadros de "
            f"{estilo.pacotes} pacotes; o porte não tem referências que bastem)"
        )
    else:
        onde = tipo + (f"/{corpo}" if corpo else "")
        cabecalho = f"olho do app (sem referências ativas de {onde}; só o contraste entre partes)"

    cruas = {
        "caixa": list(caixa),
        "altura": medidas["altura"],
        "largura": medidas["largura"],
        "cores": medidas["cores"],
        "preenchimento": medidas["preenchimento"],
        "tons_por_grupo": medidas["tons_por_grupo"],
        "contorno": contorno,
        "contraste_por_camada": [
            {"a": p["a"], "b": p["b"], "dL": round(p["dL"], 1), "contato": len(p["contato"])}
            for p in pares
        ],
    }
    return RelatorioDoOlho(cabecalho=cabecalho, desvios=tuple(desvios), medidas=cruas)


# ---------------------------------------------------------------------------
# Comparações
# ---------------------------------------------------------------------------
def _comparar(desvios, codigo, quadros, valor, medido, fracoes, formato, frase) -> None:
    faixa = quantis(quadros, valor, fracoes)
    if faixa is None:
        return
    baixo, alto = faixa
    if baixo <= medido <= alto:
        return
    desvios.append(Desvio(codigo, frase(formato(medido), formato(baixo), formato(alto))))


def _tons(desvios, quadros, medidas, fracoes, rgba, cor_do_contorno) -> None:
    faixa = quantis(quadros, lambda q: q.tons_por_grupo, fracoes)
    medido = medidas["tons_por_grupo"]
    if faixa is None or medido is None or faixa[0] <= medido <= faixa[1]:
        return
    baixo, alto = faixa
    grupos = _grupos_de_matiz(medidas["paleta"], excluir=cor_do_contorno)
    if medido < baixo:
        sozinhos = [g[0] for g in grupos if len(g) == 1]
        onde = "; ".join(f"{cor} em {_caixa_da_cor(rgba, cor)}" for cor in sozinhos[:4])
        desvios.append(
            Desvio(
                "TONS",
                f"{_num(medido, 1)} tons por grupo de matiz; referências {_num(baixo, 1)}–"
                f"{_num(alto, 1)}" + (f" (1 tom só: {onde})" if onde else ""),
            )
        )
    else:
        desvios.append(
            Desvio(
                "TONS",
                f"{_num(medido, 1)} tons por grupo de matiz; referências {_num(baixo, 1)}–"
                f"{_num(alto, 1)} (o grupo maior tem {max(len(g) for g in grupos)} cores)",
            )
        )


def _rampas(desvios, quadros, medidas, fracoes) -> None:
    rampas = medidas["rampas"]
    if not rampas:
        return
    fracao = sum(1 for r in rampas if r["provavel"]) / len(rampas)
    faixa = quantis(quadros, lambda q: q.rampas_provaveis, fracoes)
    if faixa is None or fracao >= faixa[0]:
        return
    soltas = [" ".join(r["cores"]) for r in rampas if not r["provavel"]][:2]
    desvios.append(
        Desvio(
            "RAMPAS",
            f"{round(fracao * 100)}% dos grupos de cor formam rampa (tons vizinhos se "
            f"encostando); referências a partir de {round(faixa[0] * 100)}%"
            + (f" (sem rampa: {'; '.join(soltas)})" if soltas else ""),
        )
    )


def _contorno(desvios, quadros, contorno, fracoes, rgba) -> None:
    dist = distribuicao(quadros, lambda q: q.contorno_tipo)
    if not dist:
        return
    maioria, fatia = next(iter(dist.items()))
    tipo = contorno["tipo"]
    if dist.get(tipo, 0.0) < 0.2:
        desvios.append(
            Desvio(
                "CONTORNO",
                f"contorno {tipo}; nas referências, {maioria} em {round(fatia * 100)}% "
                f"(o seu tipo em {round(dist.get(tipo, 0.0) * 100)}%)",
            )
        )
        return
    if fracoes is None or contorno.get("escuro") is None:
        return
    mesmo_tipo = [q for q in quadros if q.contorno_tipo == tipo]
    faixa = quantis(mesmo_tipo, lambda q: q.contorno_escuro, fracoes) if mesmo_tipo else None
    if faixa is None or contorno["escuro"] >= faixa[0]:
        return
    claras = bordas_claras(rgba)
    posicoes = " ".join(f"({x},{y})" for x, y in claras[:MAX_POSICOES])
    resto = len(claras) - min(len(claras), MAX_POSICOES)
    desvios.append(
        Desvio(
            "CONTORNO",
            f"{round(contorno['escuro'] * 100)}% da borda é mais escura que o vizinho de dentro; "
            f"referências com contorno {tipo} a partir de {round(faixa[0] * 100)}%"
            + (f" (borda clara em {posicoes}" + (f" +{resto}" if resto > 0 else "") + ")" if posicoes else ""),
        )
    )


# ---------------------------------------------------------------------------
# Medidas que o medidor não tinha
# ---------------------------------------------------------------------------
def bordas_claras(rgba: np.ndarray) -> list[tuple[int, int]]:
    """Pixels da borda externa que **não** são mais escuros que o vizinho de dentro."""
    opaco = rgba[..., 3] > 0
    cerca = np.pad(opaco, 1)
    cercado = cerca[:-2, 1:-1] & cerca[2:, 1:-1] & cerca[1:-1, :-2] & cerca[1:-1, 2:]
    borda = opaco & ~cercado
    miolo = opaco & cercado
    lum = _luminancia(rgba)
    lum_miolo = np.pad(np.where(miolo, lum, 0.0), 1)
    tem_miolo = np.pad(miolo.astype(np.int32), 1)
    soma = np.zeros_like(lum)
    vizinhos = np.zeros(lum.shape, dtype=np.int32)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        fatia = (slice(1 + dy, lum.shape[0] + 1 + dy), slice(1 + dx, lum.shape[1] + 1 + dx))
        soma += lum_miolo[fatia]
        vizinhos += tem_miolo[fatia]
    comparaveis = borda & (vizinhos > 0)
    media = np.divide(soma, np.maximum(vizinhos, 1))
    claras = comparaveis & ~(lum < media - 0.02)
    ys, xs = np.nonzero(claras)
    return sorted(zip(xs.tolist(), ys.tolist()), key=lambda p: (p[1], p[0]))


def _lstar(rgba: np.ndarray) -> np.ndarray:
    y = _luminancia(rgba)
    return np.where(y > 216 / 24389, 116 * np.cbrt(y) - 16, y * 24389 / 27)


def contraste_por_camada(
    rgba: np.ndarray,
    nomes: Sequence[str],
    linhas: Sequence[str],
    cor_do_contorno: str | None,
) -> list[dict[str, Any]]:
    """ΔL* entre camadas vizinhas: lado a lado, ou separadas por 1 px de contorno.

    O valor de uma camada é a mediana de L* dos pixels dela que não são o
    contorno. Duas camadas são vizinhas com ao menos :data:`CONTATO_MINIMO`
    pares de pixels a até 2 de distância (é o que atravessa um contorno).
    """
    altura, largura = rgba.shape[:2]
    if len(linhas) != altura or any(len(linha) != largura for linha in linhas):
        return []
    simbolos = SIMBOLOS_DE_CAMADA
    dono = np.full((altura, largura), -1, dtype=np.int64)
    for y, linha in enumerate(linhas):
        for x, simbolo in enumerate(linha):
            indice = simbolos.find(simbolo)
            if indice >= 0:
                dono[y, x] = indice
    opaco = rgba[..., 3] > 0
    valido = opaco & (dono >= 0)
    if cor_do_contorno:
        codigo = int(cor_do_contorno[1:], 16)
        codigos = (
            (rgba[..., 0].astype(np.int64) << 16) | (rgba[..., 1].astype(np.int64) << 8) | rgba[..., 2]
        )
        valido &= codigos != codigo
    lstar = _lstar(rgba)
    valor = {
        int(i): float(np.median(lstar[valido & (dono == i)]))
        for i in np.unique(dono[valido])
    }
    contatos: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for dy, dx in ((0, 1), (1, 0), (0, 2), (2, 0), (1, 1), (1, -1)):
        y0, y1 = 0, altura - dy
        x0, x1 = max(0, -dx), largura - max(0, dx)
        a = dono[y0:y1, x0:x1]
        b = dono[y0 + dy : y1 + dy, x0 + dx : x1 + dx]
        ok = valido[y0:y1, x0:x1] & valido[y0 + dy : y1 + dy, x0 + dx : x1 + dx] & (a != b)
        for y, x in zip(*np.nonzero(ok)):
            par = (int(min(a[y, x], b[y, x])), int(max(a[y, x], b[y, x])))
            contatos.setdefault(par, []).append((int(x + x0), int(y + y0)))
    pares = []
    for (i, j), pontos in contatos.items():
        if len(pontos) < CONTATO_MINIMO or i >= len(nomes) or j >= len(nomes):
            continue
        pares.append(
            {"a": nomes[i], "b": nomes[j], "dL": abs(valor[i] - valor[j]), "contato": pontos}
        )
    return sorted(pares, key=lambda p: p["dL"])


# ---------------------------------------------------------------------------
# A guarda "repete o exemplo"
# ---------------------------------------------------------------------------
def iou_com_o_exemplo(rgba: np.ndarray, px: Sequence[str]) -> float:
    """O maior IoU entre a silhueta do desenho e a do exemplo, em qualquer posição."""
    desenho = rgba[..., 3] > 0
    largura = max((len(linha) for linha in px), default=0)
    if not desenho.any() or not largura:
        return 0.0
    exemplo = np.array(
        [[c != "." for c in linha.ljust(largura, ".")] for linha in px], dtype=bool
    )
    if not exemplo.any():
        return 0.0
    ys, xs = np.nonzero(desenho)
    desenho = desenho[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    a_d, l_d = desenho.shape
    a_e, l_e = exemplo.shape
    total_d, total_e = int(desenho.sum()), int(exemplo.sum())
    melhor = 0.0
    # O exemplo desliza sobre a caixa do desenho; fora dela não há interseção.
    for dy in range(-(a_e - 1), a_d):
        for dx in range(-(l_e - 1), l_d):
            y0, y1 = max(0, dy), min(a_d, dy + a_e)
            x0, x1 = max(0, dx), min(l_d, dx + l_e)
            if y0 >= y1 or x0 >= x1:
                continue
            comum = int(
                (desenho[y0:y1, x0:x1] & exemplo[y0 - dy : y1 - dy, x0 - dx : x1 - dx]).sum()
            )
            if comum:
                melhor = max(melhor, comum / (total_d + total_e - comum))
    return melhor


def repete_o_exemplo(rgba: np.ndarray, px: Sequence[str], limiar: float | None) -> float | None:
    """O IoU, quando ele passa do limiar (o desenho repete o exemplo); senão ``None``."""
    if limiar is None or not px:
        return None
    iou = iou_com_o_exemplo(rgba, px)
    return iou if iou >= limiar else None


def _caixa_da_cor(rgba: np.ndarray, cor: str) -> str:
    codigo = int(cor[1:], 16)
    codigos = (
        (rgba[..., 0].astype(np.int64) << 16) | (rgba[..., 1].astype(np.int64) << 8) | rgba[..., 2]
    )
    ys, xs = np.nonzero((codigos == codigo) & (rgba[..., 3] > 0))
    if not len(xs):
        return "?"
    return f"x{xs.min()}–{xs.max()} y{ys.min()}–{ys.max()}"


def _num(valor: float, casas: int = 1) -> str:
    texto = f"{valor:.{casas}f}".rstrip("0").rstrip(".") if casas else f"{round(valor)}"
    return texto.replace(".", ",")
