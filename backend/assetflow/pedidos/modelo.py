"""O pedido: o que a tela pediu e onde ele está (Fase B do plano do app).

Um pedido nasce na tela, espera na fila, é desenhado pelo Claude pela conversa
e volta para a tela pronto. O registro guarda o que foi pedido (o corpo, como a
tela mandou), o que o AssetFlow entendeu (a leitura, com o spec resolvido uma
vez, na criação) e o que aconteceu (situação, tentativas, eventos, asset).

As situações e como se passa de uma a outra (Fase B2: aprovado no
validador não é pronto; o pedido só conclui depois do olhar)::

    pendente ──reserva──▶ em_desenho ──aprovado no validador──▶ em_revisao
                            ├─ não aprovado (antes do teto) ──▶ em_desenho
                            ├─ não aprovado (no teto) ────────▶ falhou
                            └─ devolvido à fila ──────────────▶ pendente
    em_revisao ──concluir (o olhar)───────────▶ concluido
    em_revisao ──remendo do olhar (até o teto)─▶ em_desenho ─▶ aprovado: em_revisao
                                                └ não aprovado: em_revisao, com o
                                                  candidato de antes
    em_revisao ──reserva vencida ou devolvido──▶ pendente, com os candidatos
    pendente, em_desenho, em_revisao ──cancelar──▶ cancelado

Um pendente com candidato, quando reservado, volta direto para
``em_revisao``: falta o olhar, não um desenho novo.

**A etapa de conceito** (lote 1 do plano de fundamentos) vem antes do
desenho, conforme o ``modo_conceito`` do pedido::

    eu_escolho:     em_desenho ──propor_conceitos──▶ escolhendo
                    escolhendo ──a autora escolhe──▶ pendente, com conceito
                    escolhendo ──"outros três"─────▶ pendente, conceitos recusados
    claude_escolhe: em_desenho ──propor_conceitos(escolhido)──▶ em_desenho, com conceito
    sem_conceito:   o fluxo de sempre

Enquanto o pedido precisa de conceito, ``desenhar`` é recusado.

A **etapa** é o que a tela mostra, e é mais fina que a situação: um pedido
``em_desenho`` pode estar só reservado ("na vez do Claude"), sendo desenhado
agora, ou esperando uma correção depois de um desenho não aprovado; um
``em_revisao`` está "esperando o olhar".
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..generation.schemas import FinalResolvedSpec, SemanticPrompt
from ..pixel_knowledge import Liberdade

__all__ = [
    "CAMPOS_DO_CONCEITO",
    "Etapa",
    "Evento",
    "Liberdade",
    "ModoConceito",
    "Pedido",
    "Situacao",
    "Tipo",
    "texto_do_conceito",
]

#: Os campos de um conceito, na ordem em que aparecem.
CAMPOS_DO_CONCEITO = ("traco", "silhueta", "objeto", "pose", "simplificar")
_ROTULOS = {
    "traco": "traço",
    "silhueta": "silhueta",
    "objeto": "objeto",
    "pose": "pose",
    "simplificar": "se faltar espaço, simplifique",
}


def texto_do_conceito(conceito: dict[str, Any]) -> str:
    """Um conceito em uma linha: ``traço: … · silhueta: … · …``."""
    return " · ".join(
        f"{_ROTULOS[campo]}: {conceito[campo]}"
        for campo in CAMPOS_DO_CONCEITO
        if conceito.get(campo)
    )


class ModoConceito(str, Enum):
    """Quem escolhe o conceito antes do desenho (lote 1)."""

    #: O Claude propõe três; a autora escolhe na tela, edita ou pede outros.
    EU_ESCOLHO = "eu_escolho"
    #: O Claude propõe três, escolhe o mais forte, grava o motivo e desenha.
    CLAUDE_ESCOLHE = "claude_escolhe"
    #: Sem etapa de conceito (itens simples).
    SEM_CONCEITO = "sem_conceito"


class Situacao(str, Enum):
    PENDENTE = "pendente"
    EM_DESENHO = "em_desenho"
    #: Há desenho aprovado no validador; falta o olhar do Claude (Fase B2).
    EM_REVISAO = "em_revisao"
    #: Há três conceitos propostos; falta a escolha da autora (lote 1).
    ESCOLHENDO = "escolhendo"
    CONCLUIDO = "concluido"
    FALHOU = "falhou"
    CANCELADO = "cancelado"

    @property
    def ativa(self) -> bool:
        """Ainda pode mudar: pendente, em desenho, em revisão ou escolhendo conceito."""
        return self in (
            Situacao.PENDENTE,
            Situacao.EM_DESENHO,
            Situacao.EM_REVISAO,
            Situacao.ESCOLHENDO,
        )


class Tipo(str, Enum):
    #: Um desenho novo, a partir de uma descrição.
    DESENHO = "desenho"
    #: Um remendo sobre um asset que já existe; ``texto`` é o que mudar.
    AJUSTE = "ajuste"


class Etapa(str, Enum):
    """O que a tela diz sobre o pedido."""

    NA_FILA = "na_fila"
    #: Reservado por uma conversa, ainda sem desenho começado.
    NA_VEZ = "na_vez"
    #: Um ``desenhar(pedido_id)`` está rodando agora.
    DESENHANDO = "desenhando"
    #: Houve desenho não aprovado; a conversa ainda pode corrigir.
    CORRIGINDO = "corrigindo"
    #: Há desenho aprovado no validador; o Claude ainda vai olhá-lo (Fase B2).
    OLHANDO = "olhando"
    #: Reservado, e o Claude ainda vai propor os conceitos (lote 1).
    CONCEITUANDO = "conceituando"
    #: Três conceitos esperando a escolha da autora (lote 1).
    ESCOLHA_CONCEITO = "escolha_conceito"
    PRONTO = "pronto"
    NAO_APROVADO = "nao_aprovado"
    CANCELADO = "cancelado"


class Evento(BaseModel):
    """Um passo do andamento, como a tela o lista."""

    model_config = ConfigDict(frozen=True)

    em: datetime
    situacao: Situacao
    nota: str = ""


class Pedido(BaseModel):
    """Uma linha da fila, já lida."""

    model_config = ConfigDict(frozen=True)

    id: str
    tipo: Tipo
    situacao: Situacao
    projeto: str
    texto: str
    #: Quanto o desenho pode se afastar da base. Muda o recorte que o Claude
    #: recebe, nunca o spec: grade, cores, fundo e validação são os mesmos.
    liberdade: Liberdade = Liberdade.EQUILIBRADO
    #: Texto livre, entregue ao Claude como está. O app não o interpreta.
    direcao_de_arte: str | None = None
    #: O corpo como a tela mandou (num ajuste, ``origem_asset_id`` e ``texto``).
    corpo: dict[str, Any]
    #: O que o AssetFlow entendeu na criação: ``resolved`` (o spec) e
    #: ``semantic``. É o spec que o desenho executa, sem resolver de novo.
    leitura: dict[str, Any]
    origem_asset_id: str | None = None
    #: O desenho ligado ao pedido: o que o concluiu, ou o último não aprovado.
    asset_id: str | None = None
    job_id: str | None = None
    asset_projeto: str | None = None
    tentativas: int = 0
    max_tentativas: int
    #: Remendos pedidos pelo olhar, e o teto (``settings.pedidos.remendos``).
    remendos: int = 0
    max_remendos: int = 0
    #: Um desenho começado com candidato — um remendo — está rodando.
    remendando: bool = False
    #: Os desenhos do pedido aprovados no validador, na ordem; o último é o
    #: que ``asset_id`` aponta enquanto o pedido espera o olhar.
    candidatos: tuple[str, ...] = ()
    #: A linha do olhar que concluiu o pedido.
    olhar: str | None = None
    #: O que foi entregue ao Claude com o pedido: o exemplo convertido, as
    #: lições e os interruptores (para medir se ajudam). Gravado também no
    #: asset (``olhar.json``).
    envio: dict[str, Any] | None = None
    #: A etapa de conceito: o modo, os três propostos, os recusados, o
    #: escolhido (com os campos de :data:`CAMPOS_DO_CONCEITO`) e, no modo
    #: ``claude_escolhe``, o motivo da escolha.
    modo_conceito: ModoConceito = ModoConceito.SEM_CONCEITO
    conceitos: tuple[dict[str, Any], ...] = ()
    conceitos_recusados: tuple[dict[str, Any], ...] = ()
    conceito: dict[str, Any] | None = None
    motivo_conceito: str | None = None
    #: Numa rodada da banca de teste: ``{"rodada", "item", "ordem", "total"}``.
    banca: dict[str, Any] | None = None
    #: O que passou pela conversa por este pedido, em caracteres e imagens.
    custo: dict[str, Any] = {}
    ultimo_laudo: str | None = None
    #: A reserva: qual leva de ``pedidos_pendentes`` o pegou, e até quando.
    leva: str | None = None
    reservado_ate: datetime | None = None
    #: Um desenho rodando agora, desde quando.
    desenhando_desde: datetime | None = None
    motivo: str | None = None
    eventos: tuple[Evento, ...] = ()
    criado_em: datetime
    atualizado_em: datetime

    @property
    def spec(self) -> FinalResolvedSpec:
        """O spec gravado na criação — o mesmo objeto, a mesma identidade."""
        return FinalResolvedSpec.model_validate(self.leitura["resolved"])

    @property
    def semantica(self) -> SemanticPrompt | None:
        bruta = self.leitura.get("semantic")
        return SemanticPrompt.model_validate(bruta) if bruta else None

    @property
    def precisa_conceito(self) -> bool:
        return self.modo_conceito is not ModoConceito.SEM_CONCEITO and self.conceito is None

    def reserva_vencida(self, agora: datetime) -> bool:
        return self.reservado_ate is not None and self.reservado_ate < agora

    def etapa(self, agora: datetime) -> Etapa:
        if self.situacao is Situacao.CONCLUIDO:
            return Etapa.PRONTO
        if self.situacao is Situacao.FALHOU:
            return Etapa.NAO_APROVADO
        if self.situacao is Situacao.CANCELADO:
            return Etapa.CANCELADO
        if self.situacao is Situacao.ESCOLHENDO:
            return Etapa.ESCOLHA_CONCEITO
        if self.situacao is Situacao.PENDENTE:
            return Etapa.NA_FILA
        if self.desenhando_desde is not None:
            return Etapa.DESENHANDO
        if self.reserva_vencida(agora):
            # A reserva venceu: o próximo pedidos_pendentes o devolve à fila.
            return Etapa.NA_FILA
        if self.situacao is Situacao.EM_REVISAO:
            return Etapa.OLHANDO
        if self.precisa_conceito:
            return Etapa.CONCEITUANDO
        return Etapa.CORRIGINDO if self.tentativas else Etapa.NA_VEZ
