"""Engine Catalog — a vitrine das gavetas (plano de motores §6).

O AssetFlow já tinha duas visões de motor, e nenhuma servia para a tela:

``EngineManifest``
    o que a gaveta **consegue** fazer. É o que o resolver consulta, e está
    escrito para uma máquina decidir roteamento.
``EngineDescriptor``
    o estado operacional dela — registrada, habilitada, saudável. É
    diagnóstico de administrador.

Falta a terceira pergunta, que é a da pessoa na frente do seletor: *por que
eu escolheria este?* Nenhum dos dois responde, e responder isso com um
``if engine_id == "flux-pixel-v1"`` em algum componente é exatamente o que o
plano de motores §24 proíbe.

Este módulo resolve a lacuna somando as três fontes em uma entrada só:

    manifest.catalog   (a vitrine, escrita junto da gaveta)
  + manifest.supports  (o que ela sabe fazer, já declarado)
  + estado + health    (se dá para usar agora)
  = EngineCatalogEntry

O catálogo **não decide nada**. Ele descreve. Quem escolhe é a pessoa (modo
manual), a :class:`~.auto_policy.AutoEnginePolicy` (modo auto) ou o
roteamento por capacidade — nesta ordem de precedência.

Uma nota sobre o layout: o plano de motores §23 sugere ``assetflow/engines/catalog/``.
Aqui o catálogo mora dentro do kernel porque é uma **leitura** da estante que
já existe (registry + manifestos), e movê-lo para fora exigiria que ele
importasse o registry de cima para baixo — invertendo a dependência que o
teste de fronteiras protege. A estrutura muda; a regra do plano, não: nenhum
motor concreto é importado aqui.
"""

from __future__ import annotations

import logging

from ..schemas import (
    AssetFlowModel,
    Capability,
    EngineFamily,
    EngineHealthStatus,
    EngineQualityTier,
    EngineSpeedTier,
    EngineState,
)
from .registry import EngineRecord, EngineRegistry

__all__ = ["EngineCatalogEntry", "EngineCatalog"]

_LOG = logging.getLogger("assetflow.generation.catalog")


class EngineCatalogEntry(AssetFlowModel):
    """Um motor como a interface precisa vê-lo (plano de motores §6).

    Todo campo aqui é **derivado** do manifesto e do estado — nada é digitado
    duas vezes. Acrescentar uma gaveta preenche esta entrada sozinha; é o que
    permite que a tela ofereça um motor novo sem nenhuma alteração no
    frontend.
    """

    engine_id: str
    display_name: str
    engine_family: EngineFamily
    version: str
    description: str = ""
    summary: str = ""
    highlights: tuple[str, ...] = ()
    badges: tuple[str, ...] = ()

    # -- O que ele sabe fazer (plano de motores §6) ---------------------------------
    supports_pixel_art: bool = False
    supports_image_editing: bool = False
    supports_reference_image: bool = False
    supports_palette_control: bool = False
    supports_exact_resolution: bool = False
    supports_background_transparency: bool = False
    supports_seed: bool = False
    supported_logical_sizes: tuple[int, ...] = ()

    quality_tier: EngineQualityTier = EngineQualityTier.STANDARD
    speed_tier: EngineSpeedTier = EngineSpeedTier.MODERATE
    license_type: str = "unknown"

    # -- Se dá para usar agora -------------------------------------------
    #: ``active`` | ``disabled`` | ``unavailable`` | ``incompatible``.
    #: Diferente do ``EngineState``, que é ciclo de vida interno: aqui a
    #: pergunta é só "posso oferecer este motor no seletor?".
    status: str = "active"
    available: bool = True
    #: Por que não dá para usar, em português. ``None`` quando dá.
    unavailable_reason: str | None = None

    capabilities: tuple[str, ...] = ()
    model_id: str | None = None
    provider: str = "local"
    gpu_required: bool = False
    recommended_vram_mb: int = 0
    #: Tempo típico declarado pela gaveta — a tela usa para avisar de espera.
    recommended_timeout_s: int = 300

    def serves(self, capability: Capability | str) -> bool:
        return str(Capability.parse(capability)) in self.capabilities


class EngineCatalog:
    """Monta as entradas de catálogo a partir do registry."""

    def __init__(self, registry: EngineRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> EngineRegistry:
        return self._registry

    # ------------------------------------------------------------------
    async def entries(
        self,
        *,
        capability: Capability | str | None = None,
        include_hidden: bool = False,
        check_health: bool = True,
    ) -> list[EngineCatalogEntry]:
        """O catálogo, opcionalmente filtrado por capacidade.

        ``include_hidden`` traz as gavetas marcadas ``catalog.hidden`` — os
        motores de teste. Elas continuam registradas, resolvíveis e
        escolhíveis por id; apenas não são oferecidas na vitrine, porque
        oferecer "Mock Image Engine" a quem quer um sprite é ruído.
        """
        entries: list[EngineCatalogEntry] = []
        for record in self._registry.list(capability=capability):
            if record.manifest.catalog.hidden and not include_hidden:
                continue
            entries.append(await self.entry(record, check_health=check_health))
        return entries

    async def entry(
        self, record: EngineRecord, *, check_health: bool = True
    ) -> EngineCatalogEntry:
        """Uma entrada de catálogo a partir de um registro da estante."""
        manifest = record.manifest
        info = manifest.catalog
        supports = manifest.supports

        status, available, reason = await self._availability(
            record, check_health=check_health
        )

        return EngineCatalogEntry(
            engine_id=manifest.id,
            display_name=manifest.name,
            engine_family=info.family,
            version=manifest.version,
            description=manifest.description,
            summary=info.summary,
            highlights=info.highlights,
            badges=info.badges,
            supports_pixel_art=any(
                capability.variant == "pixel" for capability in manifest.capabilities
            ),
            supports_image_editing=info.image_editing or supports.inpainting,
            supports_reference_image=supports.image_reference,
            supports_palette_control=info.palette_control,
            supports_exact_resolution=info.exact_resolution,
            supports_background_transparency=supports.transparency,
            supports_seed=supports.seed,
            supported_logical_sizes=info.supported_logical_sizes,
            quality_tier=info.quality_tier,
            speed_tier=info.speed_tier,
            license_type=info.license_type,
            status=status,
            available=available,
            unavailable_reason=reason,
            capabilities=tuple(str(item) for item in manifest.capabilities),
            model_id=record.handle.config.model.id,
            provider=manifest.provider,
            gpu_required=manifest.resources.gpu_required,
            recommended_vram_mb=manifest.resources.recommended_vram_mb,
            recommended_timeout_s=manifest.timeouts.recommended_timeout_s,
        )

    async def find(
        self, engine_id: str, *, check_health: bool = True
    ) -> EngineCatalogEntry | None:
        record = self._registry.find(engine_id)
        if record is None:
            return None
        return await self.entry(record, check_health=check_health)

    # ------------------------------------------------------------------
    async def _availability(
        self, record: EngineRecord, *, check_health: bool
    ) -> tuple[str, bool, str | None]:
        """Traduz estado + saúde em "posso oferecer isto?", em português.

        A mensagem é escrita para ser lida na tela: quem escolheu um motor que
        não está pronto precisa saber o que falta — e "engine_state=failed"
        não diz a ninguém que basta instalar uma dependência.
        """
        if not record.manifest.is_api_compatible:
            return (
                "incompatible",
                False,
                "este motor foi escrito para outra versão do AssetFlow",
            )
        if not record.enabled:
            return ("disabled", False, "motor desabilitado na configuração")
        if record.state is EngineState.FAILED:
            return (
                "unavailable",
                False,
                record.handle.last_error or "o motor falhou na última tentativa",
            )

        if not check_health:
            return ("active", True, None)

        try:
            health = await record.handle.health()
        except Exception as exc:  # pragma: no cover - defensivo
            _LOG.debug("health check falhou para %s: %s", record.id, exc)
            return ("unavailable", False, "não foi possível verificar o motor")

        if not health.is_usable:
            return (
                "unavailable",
                False,
                health.detail or "o motor não está disponível agora",
            )
        degraded = health.status is EngineHealthStatus.DEGRADED
        # Degradado é oferecível: o motor roda, só não no melhor estado. O
        # detalhe sobe junto para que a tela possa dizer o que está pior.
        return ("active", True, health.detail if degraded else None)
