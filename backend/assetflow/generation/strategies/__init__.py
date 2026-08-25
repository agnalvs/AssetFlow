"""Estratégias de criação — a camada que faltava (plano de correção §2).

    base.py       o contrato de uma estratégia          (§12)
    registry.py   quais existem                         (§35)
    resolver.py   `auto` vira uma delas, e diz por quê  (§11, §40)
    model.py      prompt -> motor -> imagem             (§13)

A do agente mora em ``generation/pixel_agent/strategy.py``, junto do agente
que ela encaixa — este pacote guarda o que é comum a todas.

A distinção que tudo isto mantém (plano de correção §51)::

    STRATEGY   = como o asset será criado
    ENGINE     = qual tecnologia/modelo gera uma imagem
    AGENT      = sistema que toma decisões e usa ferramentas

Nunca misturar esses conceitos. Foi misturá-los que pôs "Texel-style Agent" no
mesmo seletor que "FLUX Pixel", sugerindo à pessoa que os dois são a mesma
categoria de coisa.
"""

from .base import GenerationStrategy, StrategyContext
from .model import ModelGenerationStrategy
from .registry import GenerationStrategyRegistry
from .resolver import GenerationStrategyResolver, StrategyRule, StrategySuggestion

__all__ = [
    "GenerationStrategy",
    "GenerationStrategyRegistry",
    "GenerationStrategyResolver",
    "ModelGenerationStrategy",
    "StrategyContext",
    "StrategyRule",
    "StrategySuggestion",
]
