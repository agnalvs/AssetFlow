"""O pedido: o que a tela pediu e onde ele está (Fase B do plano do app).

Um pedido nasce na tela, espera na fila, é desenhado pelo Claude pela conversa
e volta para a tela pronto. O registro guarda o que foi pedido (o corpo, como a
tela mandou), o que o AssetFlow entendeu (a leitura, com o spec resolvido uma
vez, na criação) e o que aconteceu (situação, tentativas, eventos, asset).

As situações e como se passa de uma a outra::

    pendente ──reserva──▶ em_desenho ──aprovado──▶ concluido
       │                     │  ├─ não aprovado (antes do teto) ─▶ em_desenho
       │                     │  ├─ não aprovado (no teto) ───────▶ falhou
       │                     │  └─ devolvido à fila ─────────────▶ pendente
       └──cancelar───────────┴──cancelar──▶ cancelado

A **etapa** é o que a tela mostra, e é mais fina que a situação: um pedido
``em_desenho`` pode estar só reservado ("na vez do Claude"), sendo desenhado
agora, ou esperando uma correção depois de um desenho não aprovado.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..generation.schemas import FinalResolvedSpec, SemanticPrompt
from ..pixel_knowledge import Liberdade

__all__ = ["Etapa", "Evento", "Liberdade", "Pedido", "Situacao", "Tipo"]


class Situacao(str, Enum):
    PENDENTE = "pendente"
    EM_DESENHO = "em_desenho"
    CONCLUIDO = "concluido"
    FALHOU = "falhou"
    CANCELADO = "cancelado"

    @property
    def ativa(self) -> bool:
        """Ainda pode mudar: pendente ou em desenho."""
        return self in (Situacao.PENDENTE, Situacao.EM_DESENHO)


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

    def reserva_vencida(self, agora: datetime) -> bool:
        return self.reservado_ate is not None and self.reservado_ate < agora

    def etapa(self, agora: datetime) -> Etapa:
        if self.situacao is Situacao.CONCLUIDO:
            return Etapa.PRONTO
        if self.situacao is Situacao.FALHOU:
            return Etapa.NAO_APROVADO
        if self.situacao is Situacao.CANCELADO:
            return Etapa.CANCELADO
        if self.situacao is Situacao.PENDENTE:
            return Etapa.NA_FILA
        if self.desenhando_desde is not None:
            return Etapa.DESENHANDO
        if self.reserva_vencida(agora):
            # A reserva venceu: o próximo pedidos_pendentes o devolve à fila.
            return Etapa.NA_FILA
        return Etapa.CORRIGINDO if self.tentativas else Etapa.NA_VEZ
