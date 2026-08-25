"""Quem responde "qual motor?" quando ninguém escolheu (plano de motores §16).

O :class:`~assetflow.generation.spec.resolver.ConstraintResolver` sabe montar
o contrato do job, mas não conhece a estante: perguntar a ele qual gaveta usar
o faria importar registry, health check e política de roteamento — e a camada
que traduz texto em contrato passaria a depender da camada que executa.

Então ele não pergunta a ninguém em particular: ele chama um **conselheiro**,
descrito por este Protocol. Quem o implementa hoje é a
:class:`~assetflow.generation.kernel.auto_policy.AutoEnginePolicy`; amanhã
pode ser outra coisa, e nada aqui muda.

O conselho é sempre **preferência**, nunca ordem: a escolha explícita da
pessoa (nível 3 e 1 da precedência) ganha dele, e um motor sugerido que caia
na hora da geração é substituído pelo fallback sem drama — porque ninguém
tinha escolhido aquele motor.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schemas import EngineAdvice, EngineSuggestion

__all__ = ["EngineAdvisor", "StrategyAdvisor"]


@runtime_checkable
class EngineAdvisor(Protocol):
    """Sugere um motor a partir das características do asset pedido."""

    def suggest(self, advice: EngineAdvice) -> EngineSuggestion | None:
        """O motor preferido para este pedido, ou ``None`` se não houver.

        ``None`` é uma resposta legítima e comum: significa "não tenho regra
        para este caso", e o roteamento por capacidade decide como sempre.
        Uma política que sempre responde algo é uma política que já não é
        configuração.
        """
        ...


@runtime_checkable
class StrategyAdvisor(Protocol):
    """Sugere o **método de criação** quando ninguém escolheu (§40).

    O irmão do :class:`EngineAdvisor`, um nível acima: um responde "com qual
    motor?", o outro responde "por qual caminho?". São perguntas diferentes,
    feitas em momentos diferentes, e a segunda decide se a primeira chega a
    ser feita.

    Diferente do conselheiro de motor, este **sempre responde**: o job precisa
    ser produzido de alguma forma, e devolver "não sei" só empurraria a
    decisão para uma camada com menos informação.

    Quem o implementa é o
    :class:`~assetflow.generation.strategies.resolver.GenerationStrategyResolver`.
    """

    def suggest(self, advice: EngineAdvice):
        """A estratégia preferida para este pedido, com o motivo."""
        ...
