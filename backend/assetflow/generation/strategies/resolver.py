"""GenerationStrategyResolver — de `auto` a uma estratégia real (§11 e §40).

Duas responsabilidades, e elas acontecem em momentos diferentes:

``suggest``
    roda na **resolução do spec**, antes de existir job. Recebe as
    características do asset e devolve *qual estratégia* e *por quê* — é o que
    a tela mostra em "Estratégia escolhida: Modelo de imagem", antes de gerar
    (plano de correção §5 e §41).
``resolve``
    roda na **execução**, e devolve o objeto que vai produzir os pixels.

As regras de ``suggest`` são configuração (``config/strategies.yaml``), pelo
mesmo motivo que a política de motores é: acrescentar uma regra não pode
exigir alterar código, senão as regras param de crescer.

Exemplo do §40, escrito no YAML::

    tile até 32×32          -> pixel_agent
    prop até 32×32          -> pixel_agent
    character a partir de 64 -> model
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..schemas import EngineAdvice, FinalResolvedSpec, GenerationStrategyType
from .base import GenerationStrategy
from .registry import GenerationStrategyRegistry

__all__ = ["StrategyRule", "StrategySuggestion", "GenerationStrategyResolver"]

_LOG = logging.getLogger("assetflow.generation.strategies.resolver")


@dataclass(frozen=True, slots=True)
class StrategySuggestion:
    """Uma estratégia preferida, com o motivo em português."""

    strategy: GenerationStrategyType
    reason: str = ""
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class StrategyRule:
    """Uma regra do ``strategies.yaml``.

    Critérios opcionais que combinam por **E**. Regra sem critério casa com
    tudo e serve de padrão.
    """

    id: str = ""
    reason: str = ""
    #: Estratégias preferidas, da melhor para a pior. A primeira registrada,
    #: disponível e capaz de atender o pedido responde.
    prefer: tuple[GenerationStrategyType, ...] = ()

    asset_types: frozenset[str] = frozenset()
    modes: frozenset[str] = frozenset()
    qualities: frozenset[str] = frozenset()
    min_logical: int | None = None
    max_logical: int | None = None
    max_colors_at_most: int | None = None

    def matches(self, advice: EngineAdvice) -> bool:
        if self.asset_types and advice.asset_type not in self.asset_types:
            return False
        if self.modes and advice.mode not in self.modes:
            return False
        if self.qualities and advice.quality not in self.qualities:
            return False

        size = advice.logical_size
        if self.min_logical is not None:
            # Sem grid lógico, uma regra que fala de tamanho não se aplica —
            # e não vale tratar "não existe" como 0, que casaria com tudo.
            if size is None or size < self.min_logical:
                return False
        if self.max_logical is not None:
            if size is None or size > self.max_logical:
                return False
        if self.max_colors_at_most is not None:
            if advice.max_colors is None or advice.max_colors > self.max_colors_at_most:
                return False
        return True

    @classmethod
    def from_config(cls, data: dict[str, Any], *, index: int) -> "StrategyRule":
        when = data.get("when") or {}
        prefer: list[GenerationStrategyType] = []
        for item in data.get("prefer") or ():
            try:
                prefer.append(GenerationStrategyType(str(item)))
            except ValueError:
                _LOG.warning("estratégia desconhecida na regra %s: %r", index + 1, item)
        return cls(
            id=str(data.get("id") or f"regra_{index + 1}"),
            reason=str(data.get("reason") or ""),
            prefer=tuple(prefer),
            asset_types=_as_set(when.get("asset_type")),
            modes=_as_set(when.get("mode")),
            qualities=_as_set(when.get("quality")),
            min_logical=_as_int(when.get("min_logical")),
            max_logical=_as_int(when.get("max_logical")),
            max_colors_at_most=_as_int(when.get("max_colors_at_most")),
        )


@dataclass(slots=True)
class GenerationStrategyResolver:
    """Escolhe a estratégia e entrega o objeto que executa (§11)."""

    registry: GenerationStrategyRegistry
    rules: tuple[StrategyRule, ...] = ()
    #: Para onde ``auto`` cai quando nenhuma regra se aplica. ``model`` é o
    #: padrão certo: é o caminho geral do sistema e atende qualquer pedido.
    default: GenerationStrategyType = GenerationStrategyType.MODEL
    default_reason: str = ""
    _spec_cache: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    # ------------------------------------------------------------------
    def suggest(self, advice: EngineAdvice) -> StrategySuggestion:
        """Qual estratégia para este pedido, e por quê.

        Sempre responde: diferente da política de motores, aqui não existe
        "não opino" — o job precisa ser produzido de alguma forma, e devolver
        ``None`` só empurraria a decisão para uma camada com menos informação.
        """
        for rule in self.rules:
            if not rule.matches(advice):
                continue
            chosen = self._first_usable(rule.prefer, advice)
            if chosen is None:
                _LOG.debug(
                    "regra '%s' casou mas nenhuma estratégia dela atende", rule.id
                )
                continue
            return StrategySuggestion(
                strategy=chosen,
                reason=rule.reason or _default_reason(chosen, advice),
                rule_id=rule.id,
            )

        fallback = self._first_usable((self.default,), advice) or self.default
        return StrategySuggestion(
            strategy=fallback,
            reason=self.default_reason or _default_reason(fallback, advice),
            rule_id="default",
        )

    def resolve(self, spec: FinalResolvedSpec) -> GenerationStrategy:
        """A estratégia que vai produzir os pixels deste job.

        O spec já chega com ``strategy.mode`` resolvido — ``auto`` virou
        ``model`` ou ``pixel_agent`` lá atrás, na resolução do contrato. Se
        um ``auto`` chegasse aqui, seria sinal de que alguém montou o spec à
        mão e pulou o resolvedor; a mensagem diz isso em vez de escolher por
        conta própria e esconder o problema.
        """
        mode = spec.strategy.mode
        if mode is GenerationStrategyType.AUTO:  # pragma: no cover - defensivo
            raise ValueError(
                "o spec chegou com strategy.mode='auto' — ele deveria ter sido "
                "resolvido na submissão do job"
            )
        return self.registry.get(mode)

    # ------------------------------------------------------------------
    def _first_usable(
        self, candidates: Sequence[GenerationStrategyType], advice: EngineAdvice
    ) -> GenerationStrategyType | None:
        """A primeira estratégia registrada que aceita este pedido.

        Quem decide se aceita é a **própria estratégia**, por ``accepts()``.
        Antes havia aqui um ``if candidate is PIXEL_AGENT`` com as regras do
        agente escritas dentro do resolvedor — e o resolvedor não tem como
        saber, por exemplo, que o vocabulário de receitas não cobre "house".
        """
        for candidate in candidates:
            strategy = self.registry.find(candidate)
            if strategy is None:
                continue
            if not strategy.accepts(advice):
                continue
            return candidate
        return None

    @classmethod
    def from_config(
        cls, registry: GenerationStrategyRegistry, data: dict[str, Any] | None
    ) -> "GenerationStrategyResolver":
        """Carrega as regras de ``config/strategies.yaml``."""
        auto = ((data or {}).get("auto")) or {}
        raw_rules = auto.get("rules") or []
        rules = tuple(
            StrategyRule.from_config(item, index=index)
            for index, item in enumerate(raw_rules)
            if isinstance(item, dict)
        )
        default = auto.get("default") or {}
        try:
            fallback = GenerationStrategyType(str(default.get("strategy", "model")))
        except ValueError:
            fallback = GenerationStrategyType.MODEL
        return cls(
            registry=registry,
            rules=rules,
            default=fallback,
            default_reason=str(default.get("reason") or ""),
        )


def _default_reason(
    strategy: GenerationStrategyType, advice: EngineAdvice
) -> str:
    """Motivo genérico, para a regra que esqueceu de escrever o seu.

    Genérico, mas nunca vazio: uma escolha automática sem motivo é a caixa
    preta que o §41 existe para acabar.
    """
    size = advice.logical_size
    detalhe = advice.asset_type + (f" {size}×{size}" if size else "")
    if strategy is GenerationStrategyType.PIXEL_AGENT:
        return f"{detalhe}: desenho pixel a pixel entrega a grade exata"
    return f"{detalhe}: geração por modelo é o caminho mais direto"


def _as_set(value: Any) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, (str, bytes)):
        return frozenset({str(value)})
    return frozenset(str(item) for item in value)


def _as_int(value: Any) -> int | None:
    return None if value is None else int(value)
