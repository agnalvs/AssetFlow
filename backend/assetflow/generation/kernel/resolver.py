"""Engine Resolver — quem decide qual gaveta será usada (planos §12, §13, §44).

O resolver é o motivo pelo qual trocar de modelo é uma alteração de
configuração, e não de código. Ele recebe uma **capacidade** e devolve uma
**cadeia ordenada de candidatos**:

    text_to_image.pixel  ->  [pixel-specialist-v2, diffusers-sdxl-v1]

O primeiro candidato é o preferido; os demais existem para o fallback
automático quando o preferido falha ou está indisponível.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from ..schemas import (
    Capability,
    EngineSelector,
    EngineState,
    ImageGenerationRequest,
)
from .exceptions import (
    EngineDisabled,
    EngineNotFound,
    NoEngineAvailable,
)
from .registry import EngineRecord, EngineRegistry

__all__ = ["RoutingPolicy", "EngineCandidate", "EngineResolution", "EngineResolver"]

_LOG = logging.getLogger("assetflow.generation.resolver")


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """Política de prioridade por capacidade (plano §13).

    Carregada de ``config/capabilities.yaml``. Reordenar a lista de um
    capability troca o motor de produção sem tocar em uma linha de código.
    """

    routing: dict[Capability, tuple[str, ...]] = field(default_factory=dict)
    fallback_enabled: bool = True
    max_engine_attempts: int = 3
    allow_degraded_as_last_resort: bool = True
    allow_unlisted_engines: bool = True

    def preferred_for(self, capability: Capability | str) -> tuple[str, ...]:
        return self.routing.get(Capability.parse(capability), ())

    @classmethod
    def from_config(cls, data: dict) -> "RoutingPolicy":
        """Constrói a partir do dicionário lido do YAML."""
        routing: dict[Capability, tuple[str, ...]] = {}
        for raw_capability, entry in (data.get("routing") or {}).items():
            engines = tuple(entry.get("engines", ())) if isinstance(entry, dict) else tuple(entry)
            routing[Capability.parse(raw_capability)] = engines

        fallback = data.get("fallback") or {}
        return cls(
            routing=routing,
            fallback_enabled=bool(fallback.get("enabled", True)),
            max_engine_attempts=int(fallback.get("max_engine_attempts", 3)),
            allow_degraded_as_last_resort=bool(
                fallback.get("allow_degraded_as_last_resort", True)
            ),
            allow_unlisted_engines=bool(data.get("allow_unlisted_engines", True)),
        )


@dataclass(frozen=True, slots=True)
class EngineCandidate:
    """Uma gaveta apta a atender o pedido, com sua posição na fila."""

    record: EngineRecord
    rank: int
    reason: str
    degraded: bool = False

    @property
    def engine_id(self) -> str:
        return self.record.id


@dataclass(frozen=True, slots=True)
class EngineResolution:
    """Resultado da resolução: quem pode atender, em que ordem e por quê."""

    capability: Capability
    candidates: tuple[EngineCandidate, ...]
    rejected: tuple[tuple[str, str], ...] = ()
    requested_engine_id: str | None = None
    fallback_allowed: bool = True

    @property
    def primary(self) -> EngineCandidate:
        if not self.candidates:
            raise NoEngineAvailable(
                f"nenhuma gaveta disponível para '{self.capability}'",
                detail={"rejected": dict(self.rejected)},
            )
        return self.candidates[0]

    @property
    def engine_ids(self) -> tuple[str, ...]:
        return tuple(candidate.engine_id for candidate in self.candidates)

    def chain(self) -> tuple[EngineCandidate, ...]:
        """Cadeia efetiva de tentativa (respeitando a permissão de fallback)."""
        if not self.fallback_allowed:
            return self.candidates[:1]
        return self.candidates


class EngineResolver:
    """Traduz capacidade + preferências em uma cadeia de motores."""

    def __init__(self, registry: EngineRegistry, policy: RoutingPolicy | None = None) -> None:
        self._registry = registry
        self._policy = policy or RoutingPolicy()

    @property
    def policy(self) -> RoutingPolicy:
        return self._policy

    def set_policy(self, policy: RoutingPolicy) -> None:
        """Permite recarregar a política sem recriar o resolver."""
        self._policy = policy

    # ------------------------------------------------------------------
    # API principal
    # ------------------------------------------------------------------
    async def resolve(
        self,
        capability: Capability | str,
        *,
        selector: EngineSelector | None = None,
        request: ImageGenerationRequest | None = None,
        exclude: Iterable[str] = (),
    ) -> EngineResolution:
        """Resolve a capacidade em uma cadeia ordenada de gavetas.

        Args:
            capability: capacidade pedida, ex.: ``text_to_image.pixel``.
            selector: modo ``auto``/``manual`` vindo do request (plano §14).
            request: quando informado, o resolver também valida limites e
                recursos declarados no manifesto contra o pedido.
            exclude: motores a ignorar (usado pelo fallback já em curso).

        Raises:
            NoEngineAvailable: se nada puder atender.
            EngineNotFound / EngineDisabled: no modo manual.
        """
        capability = Capability.parse(capability)
        selector = selector or EngineSelector()
        excluded = set(exclude)
        rejected: list[tuple[str, str]] = []

        if selector.mode == "manual" and selector.engine_id:
            return await self._resolve_manual(capability, selector, request, excluded)

        ordered = self._ordered_ids(capability, excluded)
        candidates = await self._build_candidates(ordered, capability, request, rejected)

        if not candidates:
            raise NoEngineAvailable(
                f"nenhuma gaveta disponível para a capacidade '{capability}'",
                detail={
                    "capability": str(capability),
                    "rejected": dict(rejected),
                    "registered": list(self._registry.ids()),
                },
            )

        limit = self._policy.max_engine_attempts if self._policy.fallback_enabled else 1
        return EngineResolution(
            capability=capability,
            candidates=tuple(candidates[: max(1, limit)]),
            rejected=tuple(rejected),
            requested_engine_id=candidates[0].engine_id,
            fallback_allowed=self._policy.fallback_enabled and selector.allow_fallback,
        )

    async def _resolve_manual(
        self,
        capability: Capability,
        selector: EngineSelector,
        request: ImageGenerationRequest | None,
        excluded: set[str],
    ) -> EngineResolution:
        """Seleção explícita de motor por usuário avançado (plano §14)."""
        engine_id = selector.engine_id or ""
        record = self._registry.find(engine_id)
        if record is None:
            raise EngineNotFound(
                f"motor '{engine_id}' não está registrado", engine_id=engine_id
            )
        if not record.enabled:
            raise EngineDisabled(
                f"motor '{engine_id}' está desabilitado", engine_id=engine_id
            )
        if not record.declares(capability):
            raise NoEngineAvailable(
                f"motor '{engine_id}' não declara a capacidade '{capability}'",
                engine_id=engine_id,
            )

        rejected: list[tuple[str, str]] = []
        candidates = await self._build_candidates([engine_id], capability, request, rejected)
        if not candidates:
            raise NoEngineAvailable(
                f"motor '{engine_id}' não pode atender este pedido: "
                f"{dict(rejected).get(engine_id, 'motivo desconhecido')}",
                engine_id=engine_id,
                detail={"rejected": dict(rejected)},
            )

        chain = list(candidates)
        if selector.allow_fallback and self._policy.fallback_enabled:
            others = self._ordered_ids(capability, excluded | {engine_id})
            chain.extend(await self._build_candidates(others, capability, request, rejected))

        limit = self._policy.max_engine_attempts if selector.allow_fallback else 1
        return EngineResolution(
            capability=capability,
            candidates=tuple(chain[: max(1, limit)]),
            rejected=tuple(rejected),
            requested_engine_id=engine_id,
            fallback_allowed=selector.allow_fallback and self._policy.fallback_enabled,
        )

    # ------------------------------------------------------------------
    # Ordenação e filtragem
    # ------------------------------------------------------------------
    def _ordered_ids(self, capability: Capability, excluded: set[str]) -> list[str]:
        """Ordem de preferência: política primeiro, depois o resto."""
        preferred = [
            engine_id
            for engine_id in self._policy.preferred_for(capability)
            if engine_id not in excluded
        ]

        declaring = [
            record.id
            for record in self._registry.list(capability=capability)
            if record.id not in excluded
        ]

        ordered = [engine_id for engine_id in preferred if engine_id in set(declaring)]
        if self._policy.allow_unlisted_engines:
            ordered.extend(engine_id for engine_id in declaring if engine_id not in ordered)
        return ordered

    async def _build_candidates(
        self,
        engine_ids: Sequence[str],
        capability: Capability,
        request: ImageGenerationRequest | None,
        rejected: list[tuple[str, str]],
    ) -> list[EngineCandidate]:
        """Filtra por habilitação, compatibilidade, limites e saúde."""
        healthy: list[EngineCandidate] = []
        degraded: list[EngineCandidate] = []

        for rank, engine_id in enumerate(engine_ids):
            record = self._registry.find(engine_id)
            if record is None:
                rejected.append((engine_id, "não registrado"))
                continue
            if not record.enabled:
                rejected.append((engine_id, "desabilitado"))
                continue
            if not record.manifest.is_api_compatible:
                rejected.append(
                    (
                        engine_id,
                        f"engine_api_version incompatível "
                        f"({record.manifest.engine_api_version})",
                    )
                )
                continue
            if not record.declares(capability):
                rejected.append((engine_id, f"não declara '{capability}'"))
                continue

            if request is not None:
                incompatibility = _incompatibility(record, request)
                if incompatibility:
                    rejected.append((engine_id, incompatibility))
                    continue

            state = record.state
            if state in {EngineState.FAILED, EngineState.UNLOADING}:
                rejected.append((engine_id, f"estado {state.value}"))
                continue

            health = await record.handle.health()
            if not health.is_usable:
                rejected.append((engine_id, health.detail or "health check indisponível"))
                continue

            is_degraded = (
                record.state is EngineState.DEGRADED or health.status.value == "degraded"
            )
            candidate = EngineCandidate(
                record=record,
                rank=rank,
                reason="preferência de configuração" if rank == 0 else "fallback",
                degraded=is_degraded,
            )
            (degraded if is_degraded else healthy).append(candidate)

        if degraded and not self._policy.allow_degraded_as_last_resort:
            for candidate in degraded:
                rejected.append((candidate.engine_id, "degradado"))
            degraded = []

        return healthy + degraded


def _incompatibility(record: EngineRecord, request: ImageGenerationRequest) -> str | None:
    """Checa o pedido contra ``limits``/``supports`` do manifesto.

    Só rejeita o que o motor **fisicamente não consegue** fazer ou o que
    silenciaria a intenção do usuário. Recursos meramente ausentes (ex.:
    ``negative_prompt``) viram aviso no resultado, não rejeição — o kernel
    é quem os anota.
    """
    limits = record.manifest.limits
    supports = record.manifest.supports
    output = request.output

    if not (limits.min_width <= output.width <= limits.max_width):
        return f"largura {output.width} fora dos limites [{limits.min_width}, {limits.max_width}]"
    if not (limits.min_height <= output.height <= limits.max_height):
        return (
            f"altura {output.height} fora dos limites "
            f"[{limits.min_height}, {limits.max_height}]"
        )
    if limits.dimension_multiple_of:
        step = limits.dimension_multiple_of
        if output.width % step or output.height % step:
            return f"dimensões devem ser múltiplas de {step}"

    if request.reference_images and not supports.image_reference:
        return "não suporta imagens de referência"
    if request.structural_controls and not supports.controlnet:
        return "não suporta controle estrutural"

    return None
