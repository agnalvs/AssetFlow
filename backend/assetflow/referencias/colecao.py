"""A coleção ativa: o que os pacotes ativos dizem, somado, para um pedido.

Ela carrega só o que já foi medido (``medidas.json``): nada é medido no boot.
Chegam ao Claude duas coisas, e nenhuma é um desenho de terceiro em forma de
receita:

- a linha ``referências:`` do recorte, em duas partes que somem sozinhas:
  **estilo** (contorno, tons por grupo de matiz), de qualquer tamanho; e
  **porte** (cores, largura, preenchimento), só dos quadros cuja altura de
  conteúdo fica perto da altura do corpo do pedido;
- uma imagem de exemplo, ampliada, por ``ver_referencia``.

Linha de chão, margem e ocupação do quadro não entram: o quadro das
referências é outro, e esses números só fazem sentido dentro do mesmo quadro.

Toda soma dá **peso igual a cada pacote**: um pacote de 2.600 quadros de 16 px
não pode decidir sozinho o estilo de cinco. Cada quadro pesa 1 ÷ (quadros do
seu pacote no conjunto).
"""

from __future__ import annotations

import io
import json
import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .medidor import carregar, detectar_escala
from .pacote import (
    ConfiguracaoDeReferencias,
    Manifesto,
    ReferenciaInvalida,
    ler_configuracao,
    ler_manifesto,
)

__all__ = ["LADO_DA_AMPLIACAO", "QuadroMedido", "ReferenciasAtivas", "quantis"]

_LOG = logging.getLogger("assetflow.referencias")

#: Lado aproximado, em pixels, da imagem que ``ver_referencia`` devolve.
LADO_DA_AMPLIACAO = 256


@dataclass(frozen=True, slots=True)
class QuadroMedido:
    pacote: str
    arquivo: str
    caixa: tuple[int, int, int, int]
    quadro_conhecido: bool
    escala: int
    tipo: str
    corpo: str | None
    altura: int
    largura: int
    cores: int
    preenchimento: float
    tons_por_grupo: float | None
    contorno_tipo: str
    contorno_cor: str


@dataclass(frozen=True, slots=True)
class ReferenciasAtivas:
    """Os quadros dos pacotes ativos e autorizados, prontos para somar."""

    raiz: Path | None = None
    configuracao: ConfiguracaoDeReferencias = field(default_factory=ConfiguracaoDeReferencias)
    pacotes: tuple[Manifesto, ...] = ()
    quadros: tuple[QuadroMedido, ...] = ()
    avisos: tuple[str, ...] = ()

    @classmethod
    def vazia(cls) -> ReferenciasAtivas:
        return cls()

    @property
    def esta_vazia(self) -> bool:
        return not self.quadros

    @classmethod
    def carregar(cls, raiz: Path, configuracao: Path) -> ReferenciasAtivas:
        """Os pacotes ativos de ``raiz``, filtrados pela licença e pelo aceite."""
        config = ler_configuracao(configuracao)
        avisos = list(config.problemas)
        pacotes: list[Manifesto] = []
        quadros: list[QuadroMedido] = []
        for ativo in config.ativos:
            pasta = raiz / ativo.pacote
            try:
                manifesto = ler_manifesto(pasta)
            except ReferenciaInvalida as exc:
                avisos.append(f"pacote ativo '{ativo.pacote}' não está em {raiz}: {exc}")
                continue
            if manifesto.attribution_required and not ativo.aceitar_atribuicao:
                avisos.append(
                    f"pacote '{ativo.pacote}' ({manifesto.license_id}) exige atribuição e não "
                    "foi aceito: marque aceitar_atribuicao: true para usá-lo"
                )
                continue
            try:
                medidas = json.loads((pasta / "medidas.json").read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                avisos.append(f"pacote '{ativo.pacote}' sem medidas: rode 'medir' ({exc})")
                continue
            pacotes.append(manifesto)
            quadros.extend(_quadro(manifesto.id, bruto) for bruto in medidas.get("quadros") or [])
        for aviso in avisos:
            _LOG.warning("referências: %s", aviso)
        return cls(
            raiz=raiz,
            configuracao=config,
            pacotes=tuple(pacotes),
            quadros=tuple(quadros),
            avisos=tuple(avisos),
        )

    # ------------------------------------------------------------------
    def candidatos(self, tipo: str, corpo: str | None) -> list[QuadroMedido]:
        """Quadros do tipo do pedido; com corpo conhecido, só os do mesmo corpo."""
        return [
            q for q in self.quadros if q.tipo == tipo and (corpo is None or q.corpo == corpo)
        ]

    def faixa(self, altura: int | None) -> tuple[int, int] | None:
        """A faixa de altura de conteúdo que conta como "porte parecido"."""
        fracao = self.configuracao.faixa_altura
        if altura is None or fracao is None:
            return None
        return math.ceil(altura * (1 - fracao)), math.floor(altura * (1 + fracao))

    def do_mesmo_porte(self, quadros: list[QuadroMedido], altura: int | None) -> list[QuadroMedido]:
        faixa = self.faixa(altura)
        if faixa is None:
            return []
        return [q for q in quadros if faixa[0] <= q.altura <= faixa[1]]

    def linha(self, tipo: str, corpo: str | None, altura: int | None) -> str:
        """``referências: estilo …; porte …`` — cada parte some sem dados."""
        minimo = self.configuracao.minimo_de_quadros or 1
        candidatos = self.candidatos(tipo, corpo)
        partes = []

        if len(candidatos) >= minimo:
            pesos = _pesos(candidatos)
            tipos: Counter = Counter()
            for q, peso in zip(candidatos, pesos):
                tipos[q.contorno_tipo] += peso
            contorno, fatia = tipos.most_common(1)[0]
            cores_de_contorno: Counter = Counter()
            for q, peso in zip(candidatos, pesos):
                if q.contorno_tipo == contorno:
                    cores_de_contorno[q.contorno_cor] += peso
            texto = (
                f"estilo de {len(candidatos)} quadros ({_pacotes(candidatos)}): "
                f"contorno {contorno} em {_pct(fatia / sum(pesos))}"
                f" (cor mais comum {cores_de_contorno.most_common(1)[0][0]})"
            )
            tons = quantis(candidatos, lambda q: q.tons_por_grupo)
            if tons:
                texto += f" · {_num(tons[1])} tons por grupo de matiz (mediana)"
            partes.append(texto)

        porte = self.do_mesmo_porte(candidatos, altura)
        if len(porte) >= minimo:
            faixa = self.faixa(altura)
            cores = quantis(porte, lambda q: q.cores)
            razao = quantis(porte, lambda q: q.largura / q.altura)[1]
            preenchimento = quantis(porte, lambda q: q.preenchimento)[1]
            partes.append(
                f"porte de {faixa[0]}–{faixa[1]} px de altura, {len(porte)} quadros"
                f" ({_pacotes(porte)}): "
                f"{_num(cores[0], 0)}–{_num(cores[2], 0)} cores (mediana {_num(cores[1], 0)})"
                f" · largura {_num(razao, 2)}× a altura · preenchimento {_pct(preenchimento)} da caixa"
            )
        return f"referências: {'; '.join(partes)}" if partes else ""

    # ------------------------------------------------------------------
    def exemplo(self, tipo: str, corpo: str | None, altura: int | None) -> tuple[bytes, str] | None:
        """UM quadro típico, ampliado, e a legenda com origem e licença.

        Típico é o mais perto das medianas do conjunto (de preferência do
        mesmo porte). A escolha é determinística.
        """
        candidatos = self.do_mesmo_porte(self.candidatos(tipo, corpo), altura) or self.candidatos(
            tipo, corpo
        )
        if not candidatos or self.raiz is None:
            return None
        alvo = (
            quantis(candidatos, lambda q: q.altura)[1],
            quantis(candidatos, lambda q: q.cores)[1],
            quantis(candidatos, lambda q: q.preenchimento)[1],
        )

        def distancia(q: QuadroMedido) -> tuple[float, str, str, tuple[int, ...]]:
            d = (
                abs(q.altura - alvo[0]) / max(alvo[0], 1)
                + abs(q.cores - alvo[1]) / max(alvo[1], 1)
                + abs(q.preenchimento - alvo[2])
            )
            return (round(d, 6), q.pacote, q.arquivo, q.caixa)

        escolhido = min(candidatos, key=distancia)
        manifesto = next(p for p in self.pacotes if p.id == escolhido.pacote)
        png, lado, fator = _ampliar(self.raiz / escolhido.pacote / "original" / escolhido.arquivo, escolhido)
        legenda = (
            f"referência de estilo, não para copiar · {manifesto.nome} ({manifesto.id}) · "
            f"{manifesto.autor} · {manifesto.license_id} · {escolhido.arquivo} · "
            f"conteúdo {escolhido.largura}×{escolhido.altura}, {escolhido.cores} cores · "
            f"{lado} ampliado {fator}×"
        )
        return png, legenda


def _quadro(pacote: str, bruto: dict[str, Any]) -> QuadroMedido:
    contorno = bruto.get("contorno") or {}
    return QuadroMedido(
        pacote=pacote,
        arquivo=str(bruto["arquivo"]),
        caixa=tuple(int(v) for v in bruto["caixa"]),
        quadro_conhecido=bool(bruto.get("quadro_conhecido")),
        escala=int(bruto.get("escala") or 1),
        tipo=str(bruto["tipo"]),
        corpo=bruto.get("corpo"),
        altura=int(bruto["altura"]),
        largura=int(bruto["largura"]),
        cores=int(bruto["cores"]),
        preenchimento=float(bruto["preenchimento"]),
        tons_por_grupo=bruto.get("tons_por_grupo"),
        contorno_tipo=str(contorno.get("tipo") or "indefinido"),
        contorno_cor=str(contorno.get("cor") or ""),
    )


def _ampliar(arquivo: Path, quadro: QuadroMedido) -> tuple[bytes, str, int]:
    rgba = carregar(arquivo)
    escala = detectar_escala(rgba)
    if escala > 1:
        rgba = rgba[::escala, ::escala]
    x, y, largura, altura = quadro.caixa
    if not quadro.quadro_conhecido:  # caixa do conteúdo: 1 px de folga em volta
        x0, y0 = max(x - 1, 0), max(y - 1, 0)
        x1, y1 = min(x + largura + 1, rgba.shape[1]), min(y + altura + 1, rgba.shape[0])
        x, y, largura, altura = x0, y0, x1 - x0, y1 - y0
    pedaco = np.ascontiguousarray(rgba[y : y + altura, x : x + largura])
    fator = max(1, LADO_DA_AMPLIACAO // max(largura, altura))
    imagem = Image.fromarray(pedaco, "RGBA").resize((largura * fator, altura * fator), Image.NEAREST)
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue(), f"{largura}×{altura}", fator


def _pesos(quadros: list[QuadroMedido]) -> list[float]:
    """Peso de cada quadro: 1 ÷ (quadros do seu pacote no conjunto)."""
    por_pacote = Counter(q.pacote for q in quadros)
    return [1 / por_pacote[q.pacote] for q in quadros]


def quantis(quadros: list[QuadroMedido], valor) -> tuple[float, float, float] | None:
    """p25, mediana e p75 de ``valor(q)``, com peso igual por pacote.

    ``None`` quando nenhum quadro tem o valor.
    """
    pares = sorted(
        (v, peso) for q, peso in zip(quadros, _pesos(quadros)) if (v := valor(q)) is not None
    )
    if not pares:
        return None
    total = sum(peso for _, peso in pares)
    resultado = []
    for fracao in (0.25, 0.5, 0.75):
        acumulado = 0.0
        for v, peso in pares:
            acumulado += peso
            if acumulado >= fracao * total - 1e-9:
                resultado.append(float(v))
                break
    return tuple(resultado)


def _pacotes(quadros: list[QuadroMedido]) -> str:
    n = len({q.pacote for q in quadros})
    return "1 pacote" if n == 1 else f"{n} pacotes, peso igual"


def _pct(fracao: float) -> str:
    return f"{round(fracao * 100)}%"


def _num(valor: float, casas: int = 1) -> str:
    texto = f"{valor:.{casas}f}".rstrip("0").rstrip(".") if casas else f"{round(valor)}"
    return texto.replace(".", ",")
