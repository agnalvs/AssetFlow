"""GenerationStrategyRegistry — quais métodos de criação existem (§35).

O paralelo do ``EngineRegistry``, um nível acima. E a razão de existirem dois
registros separados é o próprio erro que o plano de correção veio desfazer:
quando havia um só, o agente de desenho foi registrado como motor, e a
interface passou a oferecer estratégia e tecnologia na mesma lista.

    EngineRegistry               sdxl, flux, sdpixl, pixel-forge
    GenerationStrategyRegistry   auto, model, pixel_agent

``auto`` não está registrado como estratégia, e não é esquecimento: ``auto``
não é um jeito de criar, é a *ausência* de escolha. Quem o resolve é o
:class:`~.resolver.GenerationStrategyResolver`, que devolve uma das
estratégias reais — sempre.
"""

from __future__ import annotations

import logging

from ..schemas import GenerationStrategyType
from .base import GenerationStrategy

__all__ = ["GenerationStrategyRegistry"]

_LOG = logging.getLogger("assetflow.generation.strategies")


class GenerationStrategyRegistry:
    """Registro das estratégias disponíveis."""

    def __init__(self, strategies: list[GenerationStrategy] | None = None) -> None:
        self._strategies: dict[GenerationStrategyType, GenerationStrategy] = {}
        for strategy in strategies or ():
            self.register(strategy)

    def register(self, strategy: GenerationStrategy) -> GenerationStrategy:
        if strategy.strategy_id is GenerationStrategyType.AUTO:
            # `auto` é uma pergunta, não uma resposta. Registrá-lo abriria a
            # porta para o resolvedor devolver "automático" como se fosse uma
            # estratégia executável, e o pipeline não teria o que chamar.
            raise ValueError(
                "'auto' não é uma estratégia executável — ele é resolvido "
                "para uma das outras pelo GenerationStrategyResolver"
            )
        self._strategies[strategy.strategy_id] = strategy
        _LOG.info("estratégia registrada: %s", strategy.strategy_id.value)
        return strategy

    def get(self, strategy_id: GenerationStrategyType | str) -> GenerationStrategy:
        key = GenerationStrategyType(strategy_id)
        strategy = self._strategies.get(key)
        if strategy is None:
            raise KeyError(f"estratégia não registrada: '{key.value}'")
        return strategy

    def find(
        self, strategy_id: GenerationStrategyType | str
    ) -> GenerationStrategy | None:
        try:
            return self.get(strategy_id)
        except (KeyError, ValueError):
            return None

    def list(self) -> list[GenerationStrategy]:
        """As estratégias registradas, em ordem estável.

        A ordem é a da declaração do enum, e não a de registro: é ela que a
        tela usa para desenhar o seletor, e um seletor que muda de ordem entre
        instalações é um seletor em que ninguém confia.
        """
        return [
            self._strategies[key]
            for key in GenerationStrategyType
            if key in self._strategies
        ]

    def ids(self) -> tuple[GenerationStrategyType, ...]:
        return tuple(strategy.strategy_id for strategy in self.list())

    def __contains__(self, strategy_id: object) -> bool:
        if isinstance(strategy_id, GenerationStrategyType):
            return strategy_id in self._strategies
        if isinstance(strategy_id, str):
            try:
                return GenerationStrategyType(strategy_id) in self._strategies
            except ValueError:
                return False
        return False

    def __len__(self) -> int:
        return len(self._strategies)
