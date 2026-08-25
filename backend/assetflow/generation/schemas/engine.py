"""Schemas que descrevem uma "gaveta" para o AssetFlow.

O manifesto (plano §9) é o único jeito pelo qual o sistema descobre o que um
motor consegue fazer. O AssetFlow lê o manifesto — nunca o código do motor.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator

from .capability import Capability
from .common import AssetFlowModel, utcnow

__all__ = [
    "ENGINE_API_VERSION",
    "SUPPORTED_ENGINE_API_VERSIONS",
    "EngineType",
    "EngineFamily",
    "EngineState",
    "EngineHealthStatus",
    "EngineQualityTier",
    "EngineSpeedTier",
    "EngineSupports",
    "EngineLimits",
    "EngineResources",
    "EngineTimeouts",
    "EngineCatalogInfo",
    "EngineManifest",
    "EngineHealth",
    "EngineDescriptor",
    "EngineRuntimeConfig",
    "EngineRef",
    "EngineAdvice",
    "EngineSuggestion",
]

#: Versão do contrato implementada por este backend (plano §10).
ENGINE_API_VERSION = "1"

#: Versões de contrato que este backend consegue operar. Quando existir a v2,
#: basta acrescentá-la aqui e o registry passa a aceitar as duas gerações.
SUPPORTED_ENGINE_API_VERSIONS: frozenset[str] = frozenset({"1"})


class EngineType(str, Enum):
    """Famílias de gaveta previstas. Só a primeira existe hoje."""

    IMAGE_GENERATION = "image_generation"
    IMAGE_EDITING = "image_editing"
    ANIMATION = "animation"
    UPSCALING = "upscaling"


class EngineFamily(str, Enum):
    """A tecnologia por trás da gaveta, para a vitrine (plano de motores §6).

    Não é um detalhe de implementação vazando: é a informação que impede a
    pessoa de esperar de um agente que desenha pixel a pixel o mesmo tempo de
    resposta de um modelo de difusão. O sistema nunca decide nada por este
    campo — quem decide é capacidade, manifesto e política.
    """

    DIFFUSION = "diffusion"
    #: Modelo nativo de sprites em resolução baixa (Pixel Forge).
    NATIVE_SPRITE = "native_sprite"
    #: Otimização iterativa por imagem (SD-πXL): lento e caro por natureza.
    OPTIMIZATION = "optimization"
    #: Agente que desenha com ferramentas, pixel a pixel (estilo Texel).
    AGENTIC = "agentic"
    #: Gerador determinístico sem IA — as gavetas de referência.
    PROCEDURAL = "procedural"


class EngineQualityTier(str, Enum):
    """Faixa de qualidade esperada. Comparativa, nunca uma promessa."""

    DRAFT = "draft"
    STANDARD = "standard"
    HIGH = "high"
    #: Referência de qualidade máxima, tipicamente às custas de tempo.
    REFERENCE = "reference"


class EngineSpeedTier(str, Enum):
    """Faixa de tempo de resposta, na ordem em que a pessoa a sente."""

    INSTANT = "instant"
    FAST = "fast"
    MODERATE = "moderate"
    SLOW = "slow"
    VERY_SLOW = "very_slow"


class EngineState(str, Enum):
    """Ciclo de vida de um motor (plano §35)."""

    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNLOADING = "unloading"
    DISABLED = "disabled"

    @property
    def is_usable(self) -> bool:
        """Estados a partir dos quais um job pode ser despachado."""
        return self in {
            EngineState.REGISTERED,
            EngineState.INITIALIZING,
            EngineState.READY,
            EngineState.BUSY,
        }


class EngineHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class EngineSupports(AssetFlowModel):
    """Recursos opcionais que a gaveta declara suportar.

    O kernel usa estes flags para validar o request **antes** de despachar,
    e o resolver os usa para descartar motores incompatíveis com o pedido.
    """

    seed: bool = False
    negative_prompt: bool = False
    batch: bool = False
    transparency: bool = False
    progress_reporting: bool = False
    cancellation: bool = False
    # Recursos previstos para fases futuras (planos §29, §30, §31).
    lora: bool = False
    controlnet: bool = False
    image_reference: bool = False
    inpainting: bool = False


class EngineLimits(AssetFlowModel):
    """Limites físicos declarados pela gaveta."""

    min_width: int = Field(default=8, ge=1)
    min_height: int = Field(default=8, ge=1)
    max_width: int = Field(default=2048, ge=1)
    max_height: int = Field(default=2048, ge=1)
    max_variations: int = Field(default=8, ge=1)
    #: Alguns modelos exigem dimensões múltiplas de N (SDXL usa 8).
    dimension_multiple_of: int | None = Field(default=None, ge=1)


class EngineResources(AssetFlowModel):
    """Requisitos aproximados de hardware (plano §38)."""

    gpu_required: bool = False
    recommended_vram_mb: int = Field(default=0, ge=0)
    minimum_vram_mb: int = Field(default=0, ge=0)
    supports_offloading: bool = False
    supports_quantization: bool = False


class EngineTimeouts(AssetFlowModel):
    """Tempos declarados pela gaveta (plano §47)."""

    recommended_timeout_s: int = Field(default=300, ge=1)
    load_timeout_s: int = Field(default=900, ge=1)


class EngineCatalogInfo(AssetFlowModel):
    """A parte do manifesto escrita para ser **lida por gente** (plano de motores §6).

    O resto do manifesto responde "este motor consegue?" — e é o que o
    resolver consulta. Este bloco responde "por que eu escolheria este?", que
    é outra pergunta e tem outro dono: a tela.

    Ele mora no manifesto, junto da gaveta, pelo mesmo motivo que
    ``capabilities`` mora: acrescentar um motor não pode exigir editar uma
    lista em outro lugar do sistema. O ``EngineCatalog`` só lê daqui.
    """

    family: EngineFamily = EngineFamily.PROCEDURAL
    quality_tier: EngineQualityTier = EngineQualityTier.STANDARD
    speed_tier: EngineSpeedTier = EngineSpeedTier.MODERATE
    #: Licença do modelo/projeto operado — ``apache-2.0``, ``mit``, ``unlicense``.
    license_type: str = "unknown"

    #: Resoluções lógicas em que este motor rende bem. Vazio = sem preferência
    #: declarada; **não** é um limite (limite é ``EngineLimits``).
    supported_logical_sizes: tuple[int, ...] = ()

    #: Uma frase. É o que aparece embaixo do seletor quando o motor é escolhido.
    summary: str = ""
    #: Os pontos fortes em tópicos curtos (plano de motores §4.2).
    highlights: tuple[str, ...] = ()
    #: Avisos que precisam viajar com o motor: ``experimental``, ``lento``.
    badges: tuple[str, ...] = ()

    #: O motor entrega a resolução lógica exata sozinho (SD-πXL, Texel-style).
    #: Falso não é defeito: o Pixel Exact é quem garante isso no fim (§8.1).
    exact_resolution: bool = False
    #: O motor aceita um limite de cores como entrada, e não só no pós.
    palette_control: bool = False
    #: O motor também sabe editar uma imagem existente (previsto, não usado).
    image_editing: bool = False

    #: Gavetas de teste não aparecem na vitrine — continuam resolvíveis por
    #: capacidade e continuam sendo escolhíveis por quem souber o id.
    hidden: bool = False

    #: Ferramenta interna: só existe fora de produção (plano de correção §6).
    #:
    #: Diferente de ``hidden``, que é sobre a vitrine. Uma gaveta ``hidden``
    #: continua registrada e resolvível; uma ``dev_only`` **não é registrada**
    #: quando ``ASSETFLOW_APP_ENV=production``. É a diferença entre "não
    #: ofereço" e "não existe aqui".
    dev_only: bool = False


class EngineManifest(AssetFlowModel):
    """Manifesto da gaveta — o "rótulo" que o AssetFlow lê.

    Corresponde ao arquivo ``manifest.json`` dentro do pacote do motor.
    """

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str
    version: str
    engine_api_version: str = ENGINE_API_VERSION
    type: EngineType = EngineType.IMAGE_GENERATION
    provider: str = Field(
        default="local",
        description="Origem da execução: local_cpu, local_gpu, remote_api, ...",
    )
    description: str = ""

    #: Caminho de import no formato ``pacote.modulo:Classe``. É assim que o
    #: sistema instancia a gaveta sem que nenhuma outra camada a importe.
    entrypoint: str = Field(pattern=r"^[\w\.]+:[\w]+$")

    capabilities: tuple[Capability, ...] = ()
    supports: EngineSupports = Field(default_factory=EngineSupports)
    limits: EngineLimits = Field(default_factory=EngineLimits)
    resources: EngineResources = Field(default_factory=EngineResources)
    timeouts: EngineTimeouts = Field(default_factory=EngineTimeouts)
    #: A vitrine desta gaveta (plano de motores §6). Ausente, o catálogo mostra os
    #: padrões conservadores — nunca deixa de listar o motor por isso.
    catalog: EngineCatalogInfo = Field(default_factory=EngineCatalogInfo)

    #: `enabled`/`disabled` no manifesto é apenas o padrão de fábrica; a
    #: configuração de ambiente (engines.yaml) tem a palavra final.
    status: str = "enabled"

    #: Dependências Python opcionais exigidas pela gaveta, apenas informativo.
    requires: tuple[str, ...] = ()

    @field_validator("capabilities", mode="after")
    @classmethod
    def _require_capabilities(cls, value: tuple[Capability, ...]) -> tuple[Capability, ...]:
        if not value:
            raise ValueError("um motor precisa declarar ao menos uma capacidade")
        return value

    def declares(self, capability: Capability | str) -> bool:
        """Diz se o motor declara atender a capacidade pedida."""
        return any(declared.matches(capability) for declared in self.capabilities)

    @property
    def is_api_compatible(self) -> bool:
        return self.engine_api_version in SUPPORTED_ENGINE_API_VERSIONS


class EngineHealth(AssetFlowModel):
    """Resposta de ``health_check()`` (plano §43)."""

    status: EngineHealthStatus = EngineHealthStatus.HEALTHY
    model_loaded: bool = False
    gpu_available: bool = False
    detail: str | None = None
    checked_at: datetime = Field(default_factory=utcnow)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_usable(self) -> bool:
        return self.status is not EngineHealthStatus.UNAVAILABLE


class EngineRef(AssetFlowModel):
    """Referência mínima ao motor que executou algo.

    Vai junto de todo resultado e de todo registro persistido — nunca confiar
    apenas no nome do modelo (plano §42).
    """

    id: str
    version: str
    model_id: str | None = None
    model_revision: str | None = None
    provider: str | None = None
    #: Versão do adapter da gaveta — o código que traduz AssetFlow → modelo.
    #: Separado de ``version`` de propósito (plano §18): o mesmo modelo com
    #: outro adapter produz outro resultado, e sem este campo a diferença
    #: some do histórico.
    adapter_version: str | None = None
    #: LoRA aplicada por cima do modelo-base, quando houver (plano de motores §18).
    lora_id: str | None = None


class EngineDescriptor(AssetFlowModel):
    """Visão pública de um motor registrado (o que a API expõe)."""

    manifest: EngineManifest
    state: EngineState
    enabled: bool
    api_compatible: bool
    health: EngineHealth | None = None
    last_error: str | None = None
    registered_at: datetime = Field(default_factory=utcnow)
    source: str | None = Field(
        default=None, description="Origem do registro: caminho do manifesto ou 'programmatic'."
    )


class EngineModelConfig(AssetFlowModel):
    """Identificação do modelo operado pela gaveta (plano §42)."""

    id: str | None = None
    revision: str | None = None
    variant: str | None = None
    path: str | None = None


class EngineDeviceConfig(AssetFlowModel):
    type: str = "auto"
    index: int | None = None


class EnginePrecisionConfig(AssetFlowModel):
    type: str = "fp16"


class EngineRuntimeConfig(AssetFlowModel):
    """Configuração externa entregue à gaveta na inicialização (plano §65).

    O motor recebe isto e mais nada: nenhuma referência ao AssetFlow, a jobs,
    a storage ou a projetos.
    """

    engine_id: str
    enabled: bool = True
    model: EngineModelConfig = Field(default_factory=EngineModelConfig)
    device: EngineDeviceConfig = Field(default_factory=EngineDeviceConfig)
    precision: EnginePrecisionConfig = Field(default_factory=EnginePrecisionConfig)
    runtime: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    #: Diretório de trabalho isolado para caches do motor.
    workspace_dir: str | None = None

    #: Sobrescrevem os tempos do manifesto. O manifesto diz o que é razoável
    #: no hardware de referência; o ambiente sabe o que é razoável *aqui*
    #: (uma GPU modesta com offload pode precisar de bem mais tempo).
    timeout_s: float | None = Field(default=None, gt=0)
    load_timeout_s: float | None = Field(default=None, gt=0)


class EngineAdvice(AssetFlowModel):
    """O que a política de seleção automática precisa saber (plano de motores §16).

    Deliberadamente pequeno e sem nada de motor dentro: é o *pedido* descrito
    em termos de asset. Quem responde é uma política, e a política pode ser
    trocada sem que o resolver de spec saiba disso.

    Ele existe em ``schemas/`` porque as duas pontas falam por ele — o
    ``ConstraintResolver``, que pergunta, e a ``AutoEnginePolicy``, que
    responde — e nenhuma das duas pode passar a depender da outra.
    """

    capability: Capability
    asset_type: str
    #: O que está sendo desenhado — "tree", "small medieval house".
    #:
    #: Importa porque nem toda estratégia atende todo sujeito: o Pixel Agent
    #: desenha por receitas, e um sujeito fora do vocabulário dele produz uma
    #: forma genérica. Sem este campo, a escolha automática mandaria para ele
    #: coisas que ele não sabe desenhar (plano de correção §40).
    subject: str = ""
    mode: str
    logical_width: int | None = None
    logical_height: int | None = None
    max_colors: int | None = None
    transparent: bool = True
    quality: str = "standard"
    variations: int = 1

    @property
    def logical_size(self) -> int | None:
        """O maior lado do grid lógico — a medida usada pelas regras."""
        sides = [side for side in (self.logical_width, self.logical_height) if side]
        return max(sides) if sides else None


class EngineSuggestion(AssetFlowModel):
    """A resposta da política: um motor e o porquê, em português (plano de motores §17).

    O motivo não é enfeite. Sem ele, "Auto" é uma caixa preta e a pessoa só
    descobre o que ele significava depois de gerar — que é exatamente a
    experiência que o §17 existe para acabar.
    """

    engine_id: str
    reason: str = ""
    rule_id: str | None = None
