"""Planejador por LLM — o agente que desenha **qualquer coisa** (§18).

    DrawingBrief
        -> prompt          canvas, sujeito, orçamento de cores, ferramentas
        -> modelo          devolve um plano em JSON
        -> parse estrito   coordenadas, cores e ferramentas conferidas
        -> DrawingPlan     o mesmo objeto que uma receita produz

O que isto muda no agente
-------------------------
As receitas desenham bem oito ou nove objetos e nada além deles. O laço que as
executa — grade exata, paleta fechada, revisão, log reconstruível — nunca teve
esse limite: ele desenha o que o plano mandar. O limite era só o planejador.

Trocando o planejador, o agente passa a atender qualquer sujeito **mantendo**
as garantias: continua sendo pixel na grade, dentro do orçamento de cores, com
silhueta contornada e um histórico que reproduz o desenho.

O que esperar, honestamente
---------------------------
Um LLM colocando retângulos e círculos produz sprites **simples e legíveis**,
não arte detalhada. Para um baú, uma poção, uma placa, uma casa, uma chave, ele
tende a ganhar de um modelo de difusão reduzido a 32×32 — porque cada pixel foi
posto de propósito. Para um personagem com rosto e roupa em 64×64, o modelo de
difusão ganha, e é para isso que existe o método "Modelo de imagem".

Provedor
--------
Qualquer API compatível com OpenAI, inclusive local e gratuita::

    Ollama      http://localhost:11434/v1     (sem chave)
    LM Studio   http://localhost:1234/v1      (sem chave)
    OpenAI      https://api.openai.com/v1     (chave em variável de ambiente)

Sem provedor configurado, o agente usa as receitas — e diz que usou.
"""

from __future__ import annotations

import logging

from ..contracts.plan import DrawingBrief, DrawingPlan
from ..planner import RecipePlanner
from .client import ChatClient, ChatConfig, ChatError
from .prompting import LLMPlanError, build_prompt, parse_plan

__all__ = ["LLMPlanner", "ChatClient", "ChatConfig", "ChatError", "LLMPlanError"]

_LOG = logging.getLogger("assetflow.pixel_agent.llm")


class LLMPlanner:
    """Planeja com um modelo de linguagem, caindo nas receitas se falhar."""

    #: Quantas vezes pedir o plano. A segunda tentativa leva junto o motivo da
    #: recusa da primeira — é barata e resolve a maior parte dos casos, que são
    #: coordenada fora da grade e JSON embrulhado em markdown.
    max_attempts: int = 2

    def __init__(
        self,
        client: ChatClient,
        *,
        fallback: RecipePlanner | None = None,
        max_attempts: int = 2,
    ) -> None:
        self._client = client
        self._fallback = fallback or RecipePlanner()
        self.max_attempts = max(1, max_attempts)
        #: Por que a última chamada caiu para as receitas. Lido pela estratégia
        #: para virar aviso no job — uma queda silenciosa seria o mesmo defeito
        #: que a forma genérica sem explicação.
        self.last_fallback_reason: str | None = None

    # ------------------------------------------------------------------
    @property
    def recipes(self) -> tuple[str, ...]:
        """O vocabulário de reserva. O planejador em si não tem vocabulário."""
        return self._fallback.recipes

    @property
    def client(self) -> ChatClient:
        return self._client

    def recognizes(self, subject: str, asset_type: str = "prop") -> bool:
        """Sim — é a razão de este planejador existir.

        Um modelo de linguagem não tem lista de objetos conhecidos. Responder
        ``True`` aqui é o que faz a escolha automática voltar a mandar
        qualquer sujeito para o agente (plano de correção §40), em vez de
        desviar tudo que não estivesse nas receitas.

        Com o provedor fora do ar a resposta muda: aí o agente vale o que as
        receitas valem, e prometer mais seria mentir para o resolvedor.
        """
        usable, _ = self._client.health()
        if usable:
            return True
        return self._fallback.recognizes(subject, asset_type)

    # ------------------------------------------------------------------
    def plan(self, brief: DrawingBrief) -> DrawingPlan:
        """O plano de desenho deste pedido."""
        self.last_fallback_reason = None
        system, user = build_prompt(brief)
        critique: str | None = None

        for attempt in range(self.max_attempts):
            message = user if critique is None else f"{user}\n\n{critique}"
            try:
                raw = self._client.complete(system, message)
            except ChatError as exc:
                # Provedor fora do ar: insistir não muda nada.
                return self._fall_back(brief, str(exc))

            try:
                plan = parse_plan(raw, brief)
            except LLMPlanError as exc:
                _LOG.info(
                    "plano recusado na tentativa %s/%s: %s",
                    attempt + 1,
                    self.max_attempts,
                    exc,
                )
                critique = (
                    "Your previous plan was rejected: "
                    f"{exc}. Fix exactly that and return the corrected JSON."
                )
                continue

            return plan

        return self._fall_back(
            brief, f"o planejador não produziu um plano válido em {self.max_attempts} tentativas"
        )

    # ------------------------------------------------------------------
    def _fall_back(self, brief: DrawingBrief, reason: str) -> DrawingPlan:
        """Cai para as receitas, guardando o motivo para virar aviso."""
        self.last_fallback_reason = reason
        _LOG.warning("planejador por LLM indisponível (%s); usando receitas", reason)
        return self._fallback.plan(brief)
