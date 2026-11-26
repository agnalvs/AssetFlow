"""A coleção ativa: o que os pacotes ativos dizem, somado, para um pedido.

Ela carrega só o que já foi medido (``medidas.json``): nada é medido no boot.
Chegam ao Claude três coisas:

- a linha ``referências:`` do recorte, em duas partes que somem sozinhas:
  **estilo** (contorno, tons por grupo de matiz), de qualquer tamanho; e
  **porte** (cores, largura, preenchimento), só dos quadros cuja altura de
  conteúdo fica perto da altura do corpo do pedido;
- uma imagem de exemplo, ampliada, por ``ver_referencia``;
- desde a Fase B2, **um exemplo de construção**: um quadro CC0 convertido para
  o formato de receita (:mod:`.exemplo`). Ele mostra como o pacote resolve o
  porte; nunca é a base de um asset nem entra em remendo, e um desenho que o
  repita é não aprovado (a guarda de :mod:`.olho`).

As mesmas somas servem ao **olho do app** (:mod:`.olho`), que compara o desenho
novo com as referências do mesmo porte e aponta só os desvios.

Linha de chão, margem e ocupação do quadro não entram: o quadro das
referências é outro, e esses números só fazem sentido dentro do mesmo quadro.

Toda soma dá **peso igual a cada pacote**: um pacote de 2.600 quadros de 16 px
não pode decidir sozinho o estilo de cinco. Cada quadro pesa 1 ÷ (quadros do
seu pacote no conjunto).

O peso igual tem o defeito simétrico — um quadro solto pesaria como 400 — e
duas regras de ``referencias.yaml`` o fecham, parte a parte:

- ``minimo_por_pacote``: pacote com menos quadros que isso **na parte** sai
  dela (um pacote pode estar no estilo e fora do porte);
- ``minimo_de_pacotes``: parte que fique com menos pacotes que isso some da
  linha e do ``ver_referencia``. Um pacote só não é estilo, é o estilo dele.
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

__all__ = [
    "LADO_DA_AMPLIACAO",
    "ParteDaLinha",
    "QuadroMedido",
    "ReferenciasAtivas",
    "distribuicao",
    "quantis",
]

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
    #: Fração da borda mais escura que o vizinho de dentro (o medidor a grava).
    contorno_escuro: float | None = None
    #: Fração dos grupos de matiz com mais de uma cor cujos tons vizinhos se
    #: encostam no desenho (rampa provável); ``None`` sem grupo assim.
    rampas_provaveis: float | None = None


@dataclass(frozen=True, slots=True)
class ParteDaLinha:
    """Os quadros de uma parte (estilo ou porte), já sem os pacotes pequenos."""

    quadros: tuple[QuadroMedido, ...] = ()
    #: Pacote -> quadros que ele tinha na parte, abaixo de ``minimo_por_pacote``.
    fora: tuple[tuple[str, int], ...] = ()
    #: Vazio quando a parte basta; senão, por que não basta.
    falta: str = ""

    @property
    def suficiente(self) -> bool:
        return not self.falta

    @property
    def pacotes(self) -> int:
        return len({q.pacote for q in self.quadros})


@dataclass(frozen=True, slots=True)
class ReferenciasAtivas:
    """Os quadros dos pacotes ativos e autorizados, prontos para somar."""

    raiz: Path | None = None
    configuracao: ConfiguracaoDeReferencias = field(default_factory=ConfiguracaoDeReferencias)
    pacotes: tuple[Manifesto, ...] = ()
    quadros: tuple[QuadroMedido, ...] = ()
    avisos: tuple[str, ...] = ()
    #: Os "bons exemplos" (lote 13): ``(pacote, arquivo, caixa)`` dos quadros
    #: que o estudo escolheu, lidos de ``<raiz>/bons_exemplos.json``. Vazio sem
    #: o arquivo — o exemplo volta a escolher entre todos.
    bons: frozenset[tuple[str, str, tuple[int, int, int, int]]] = frozenset()

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
        bons = _bons_exemplos(raiz / "bons_exemplos.json", avisos)
        for aviso in avisos:
            _LOG.warning("referências: %s", aviso)
        return cls(
            raiz=raiz,
            configuracao=config,
            pacotes=tuple(pacotes),
            quadros=tuple(quadros),
            avisos=tuple(avisos),
            bons=bons,
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

    def parte(self, quadros: list[QuadroMedido]) -> ParteDaLinha:
        """Tira os pacotes com amostra pequena e diz se o que sobra basta."""
        config = self.configuracao
        por_pacote = Counter(q.pacote for q in quadros)
        minimo_pacote = config.minimo_por_pacote or 1
        fora = tuple(
            sorted(
                ((p, n) for p, n in por_pacote.items() if n < minimo_pacote),
                key=lambda item: (-item[1], item[0]),
            )
        )
        excluidos = {p for p, _ in fora}
        ficam = tuple(q for q in quadros if q.pacote not in excluidos)
        pacotes = len(por_pacote) - len(fora)
        minimo_quadros = config.minimo_de_quadros or 1
        minimo_pacotes = config.minimo_de_pacotes or 1
        falta = ""
        if not ficam:
            falta = "sem quadros"
        elif len(ficam) < minimo_quadros:
            falta = f"{len(ficam)} quadros, mínimo {minimo_quadros}"
        elif pacotes < minimo_pacotes:
            falta = f"{_pacotes_n(pacotes)}, mínimo {minimo_pacotes}"
        return ParteDaLinha(quadros=ficam, fora=fora, falta=falta)

    def estilo(self, tipo: str, corpo: str | None) -> ParteDaLinha:
        """A parte de estilo: quadros do tipo (e corpo), de qualquer tamanho."""
        return self.parte(self.candidatos(tipo, corpo))

    def porte(self, tipo: str, corpo: str | None, altura: int | None) -> ParteDaLinha:
        """A parte de porte: só os de altura parecida; o mínimo por pacote conta aqui dentro."""
        return self.parte(self.do_mesmo_porte(self.candidatos(tipo, corpo), altura))

    def linha(self, tipo: str, corpo: str | None, altura: int | None) -> str:
        """``referências: estilo …; porte …`` — cada parte some se não bastar."""
        estilo = self.estilo(tipo, corpo)
        partes = []

        if estilo.suficiente:
            candidatos = list(estilo.quadros)
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

        parte_porte = self.porte(tipo, corpo, altura)
        if parte_porte.suficiente:
            porte = list(parte_porte.quadros)
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

        Típico é o mais perto das medianas do conjunto. O conjunto segue a
        regra da linha: o porte, se ele bastar; senão o estilo, de qualquer
        tamanho; senão nenhum. A escolha é determinística.
        """
        parte = self.porte(tipo, corpo, altura)
        if not parte.suficiente:
            parte = self.estilo(tipo, corpo)
        if not parte.suficiente or self.raiz is None:
            return None
        candidatos = list(parte.quadros)
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


    # ------------------------------------------------------------------
    # Fase B2: exemplo de construção e olho do app
    # ------------------------------------------------------------------
    def manifesto(self, pacote: str) -> Manifesto | None:
        return next((p for p in self.pacotes if p.id == pacote), None)

    def parte_do_exemplo(
        self, tipo: str, corpo: str | None, altura: int | None, *, por_estilo: bool = False
    ) -> ParteDaLinha:
        """De onde sai o exemplo: o porte, se bastar; senão (ou em ``ousado``) o estilo."""
        if not por_estilo:
            parte = self.porte(tipo, corpo, altura)
            if parte.suficiente:
                return parte
        return self.estilo(tipo, corpo)

    def recortar(self, quadro: QuadroMedido) -> np.ndarray:
        """Os pixels do conteúdo de um quadro, em 1×, recortados na caixa opaca."""
        if self.raiz is None:
            raise ReferenciaInvalida("coleção sem pasta de pacotes")
        rgba = carregar(self.raiz / quadro.pacote / "original" / quadro.arquivo)
        escala = detectar_escala(rgba)
        if escala > 1:
            rgba = rgba[::escala, ::escala]
        x, y, largura, altura = quadro.caixa
        pedaco = rgba[y : y + altura, x : x + largura]
        opaco = pedaco[..., 3] > 0
        if not opaco.any():
            return np.ascontiguousarray(pedaco[:0, :0])
        ys, xs = np.nonzero(opaco)
        return np.ascontiguousarray(pedaco[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1])


def _bons_exemplos(
    arquivo: Path, avisos: list[str]
) -> frozenset[tuple[str, str, tuple[int, int, int, int]]]:
    """A lista de bons exemplos do estudo (lote 13); vazia sem o arquivo."""
    if not arquivo.is_file():
        return frozenset()
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        return frozenset(
            (q["pacote"], q["arquivo"], tuple(int(v) for v in q["caixa"]))
            for q in dados.get("quadros") or []
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        avisos.append(f"bons_exemplos.json ilegível, ignorado: {exc}")
        return frozenset()


def _quadro(pacote: str, bruto: dict[str, Any]) -> QuadroMedido:
    contorno = bruto.get("contorno") or {}
    rampas = [r for r in bruto.get("rampas") or [] if isinstance(r, dict)]
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
        contorno_escuro=contorno.get("escuro"),
        rampas_provaveis=(
            sum(1 for r in rampas if r.get("provavel")) / len(rampas) if rampas else None
        ),
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


def quantis(
    quadros: list[QuadroMedido], valor, fracoes: tuple[float, ...] = (0.25, 0.5, 0.75)
) -> tuple[float, ...] | None:
    """Os quantis de ``valor(q)`` (p25, mediana e p75, por padrão), com peso igual por pacote.

    ``None`` quando nenhum quadro tem o valor.
    """
    pares = sorted(
        (v, peso) for q, peso in zip(quadros, _pesos(quadros)) if (v := valor(q)) is not None
    )
    if not pares:
        return None
    total = sum(peso for _, peso in pares)
    resultado = []
    for fracao in fracoes:
        acumulado = 0.0
        for v, peso in pares:
            acumulado += peso
            if acumulado >= fracao * total - 1e-9:
                resultado.append(float(v))
                break
    return tuple(resultado)


def distribuicao(quadros: list[QuadroMedido], valor) -> dict[str, float]:
    """A fração (peso igual por pacote) de cada valor de ``valor(q)``."""
    contagem: Counter = Counter()
    for q, peso in zip(quadros, _pesos(quadros)):
        contagem[valor(q)] += peso
    total = sum(contagem.values()) or 1.0
    return {chave: soma / total for chave, soma in contagem.most_common()}


def _pacotes(quadros: list[QuadroMedido]) -> str:
    n = len({q.pacote for q in quadros})
    return "1 pacote" if n == 1 else f"{n} pacotes, peso igual"


def _pacotes_n(n: int) -> str:
    return "1 pacote" if n == 1 else f"{n} pacotes"


def _pct(fracao: float) -> str:
    return f"{round(fracao * 100)}%"


def _num(valor: float, casas: int = 1) -> str:
    texto = f"{valor:.{casas}f}".rstrip("0").rstrip(".") if casas else f"{round(valor)}"
    return texto.replace(".", ",")
