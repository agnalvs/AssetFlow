"""AutoEnginePolicy — o que "Auto" significa, por escrito (plano de motores §16 e §17).

Antes desta política, ``auto`` queria dizer "o primeiro motor da lista de
``capabilities.yaml`` que estiver de pé". Isso continua valendo como último
recurso, e é o que impede o sistema de ficar sem resposta — mas é uma regra
cega: ela não sabe que um sprite de 16×16 tem mais chance com um motor nativo
de sprites do que com um modelo de difusão de 1024 px.

A política preenche essa lacuna com **regras declaradas em configuração**,
não em código::

    prop 32×32 com 16 cores  ->  pixel-forge-v1, texel-style-v1
    character 64×64          ->  flux-pixel-v1
    qualidade máxima + lento ->  sdpixl-v1

Três propriedades que valem mais do que a esperteza das regras:

* **Ela nunca obriga.** A resposta é uma preferência com motivo. Se o motor
  preferido estiver fora do ar na hora da geração, o fallback entra — em
  ``auto`` ninguém escolheu, então não há escolha para desrespeitar (§25).
* **Ela sempre explica.** Toda regra carrega uma frase em português, e é ela
  que a tela mostra no "Engine resolvido: X — Motivo: Y" do §17. Uma escolha
  automática que não sabe se justificar é uma caixa preta.
* **Ela é configuração.** Acrescentar uma regra é editar
  ``config/engine_policy.yaml``. Nenhum ``if engine == ...`` em lugar nenhum.

A política também **verifica antes de sugerir**: um motor só é sugerido se
estiver registrado, habilitado e declarando a capacidade pedida. Sugerir um
motor inexistente encheria a tela de promessas que a geração não cumpre.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..schemas import Capability, EngineAdvice, EngineSuggestion
from .registry import EngineRegistry

__all__ = ["EngineRule", "AutoEnginePolicy"]

_LOG = logging.getLogger("assetflow.generation.auto_policy")


@dataclass(frozen=True, slots=True)
class EngineRule:
    """Uma regra do ``engine_policy.yaml``.

    Todos os critérios são opcionais e combinam por **E**: uma regra sem
    critério nenhum casa com tudo e serve de padrão. Vazio significa "não me
    importo com este eixo", nunca "nenhum valor serve".
    """

    #: Identificador legível, usado no log e no motivo. Não é obrigatório.
    id: str = ""
    #: Motivo em português. É o que a interface mostra no §17.
    reason: str = ""
    #: Ordem de preferência entre motores, do melhor para o pior.
    prefer: tuple[str, ...] = ()

    asset_types: frozenset[str] = frozenset()
    modes: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()
    qualities: frozenset[str] = frozenset()
    #: Faixa fechada do maior lado do grid lógico.
    min_logical: int | None = None
    max_logical: int | None = None
    max_colors_at_most: int | None = None
    requires_transparency: bool | None = None

    def matches(self, advice: EngineAdvice) -> bool:
        """A regra se aplica a este pedido?"""
        if self.asset_types and advice.asset_type not in self.asset_types:
            return False
        if self.modes and advice.mode not in self.modes:
            return False
        if self.capabilities and str(advice.capability) not in self.capabilities:
            return False
        if self.qualities and advice.quality not in self.qualities:
            return False
        if self.requires_transparency is not None:
            if advice.transparent is not self.requires_transparency:
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
    def from_config(cls, data: dict[str, Any], *, index: int) -> "EngineRule":
        """Constrói a regra a partir de um item do YAML."""
        when = data.get("when") or {}
        return cls(
            id=str(data.get("id") or f"regra_{index + 1}"),
            reason=str(data.get("reason") or ""),
            prefer=tuple(str(item) for item in (data.get("prefer") or ())),
            asset_types=_as_set(when.get("asset_type")),
            modes=_as_set(when.get("mode")),
            capabilities=_as_set(when.get("capability")),
            qualities=_as_set(when.get("quality")),
            min_logical=_as_int(when.get("min_logical")),
            max_logical=_as_int(when.get("max_logical")),
            max_colors_at_most=_as_int(when.get("max_colors_at_most")),
            requires_transparency=_as_bool(when.get("transparent")),
        )


@dataclass(slots=True)
class AutoEnginePolicy:
    """Sugere um motor para o modo ``auto`` (plano de motores §16).

    Implementa o Protocol ``EngineAdvisor`` de ``generation/spec/`` sem
    importá-lo: a dependência é estrutural, e é assim que a camada que resolve
    o contrato continua sem conhecer registry nem health check.
    """

    registry: EngineRegistry
    rules: tuple[EngineRule, ...] = ()
    #: Preferência final quando nenhuma regra casa. Vazia por padrão: sem
    #: regra aplicável, é melhor deixar o roteamento por capacidade decidir
    #: do que inventar uma preferência que ninguém escreveu.
    default_prefer: tuple[str, ...] = ()
    default_reason: str = ""
    enabled: bool = True
    _cached_capabilities: dict[str, tuple[Capability, ...]] = field(
        default_factory=dict, init=False, repr=False
    )

    # ------------------------------------------------------------------
    def suggest(self, advice: EngineAdvice) -> EngineSuggestion | None:
        """O motor preferido para este pedido, ou ``None``."""
        if not self.enabled:
            return None

        for rule in self.rules:
            if not rule.matches(advice):
                continue
            engine_id = self._first_usable(rule.prefer, advice.capability)
            if engine_id is None:
                # A regra casou mas nenhum motor dela está de pé. Seguir para
                # a próxima é melhor do que sugerir algo indisponível: o
                # objetivo é escolher um motor que vai rodar.
                _LOG.debug(
                    "regra '%s' casou mas nenhum motor preferido atende '%s'",
                    rule.id,
                    advice.capability,
                )
                continue
            return EngineSuggestion(
                engine_id=engine_id,
                reason=rule.reason or _default_reason(engine_id, advice),
                rule_id=rule.id,
            )

        engine_id = self._first_usable(self.default_prefer, advice.capability)
        if engine_id is None:
            return None
        return EngineSuggestion(
            engine_id=engine_id,
            reason=self.default_reason or _default_reason(engine_id, advice),
            rule_id="default",
        )

    # ------------------------------------------------------------------
    def _first_usable(
        self, engine_ids: Sequence[str], capability: Capability
    ) -> str | None:
        """O primeiro motor da lista que existe, está ligado e atende."""
        for engine_id in engine_ids:
            record = self.registry.find(engine_id)
            if record is None or not record.enabled:
                continue
            if not record.manifest.is_api_compatible:
                continue
            if not record.declares(capability):
                continue
            return engine_id
        return None

    # ------------------------------------------------------------------
    @classmethod
    def from_config(
        cls, registry: EngineRegistry, data: dict[str, Any] | None
    ) -> "AutoEnginePolicy":
        """Carrega de ``config/engine_policy.yaml``.

        Arquivo ausente devolve uma política vazia e desligada — o modo
        ``auto`` volta a ser exatamente o que era antes dela existir, que é o
        comportamento correto para "não configurei isso".
        """
        data = data or {}
        raw_rules = data.get("rules") or []
        rules = tuple(
            EngineRule.from_config(item, index=index)
            for index, item in enumerate(raw_rules)
            if isinstance(item, dict)
        )
        default = data.get("default") or {}
        return cls(
            registry=registry,
            rules=rules,
            default_prefer=tuple(str(item) for item in (default.get("prefer") or ())),
            default_reason=str(default.get("reason") or ""),
            enabled=bool(data.get("enabled", True)),
        )


def _default_reason(engine_id: str, advice: EngineAdvice) -> str:
    """Motivo genérico, para a regra que esqueceu de escrever o seu.

    Genérico, mas nunca vazio: uma escolha automática sem motivo é a caixa
    preta que o §17 existe para acabar.
    """
    size = advice.logical_size
    detalhe = f"{advice.asset_type}"
    if size:
        detalhe += f" {size}×{size}"
    return f"'{engine_id}' é o motor preferido para {detalhe}"


def _as_set(value: Any) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, (str, bytes)):
        return frozenset({str(value)})
    return frozenset(str(item) for item in value)


def _as_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _as_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)
