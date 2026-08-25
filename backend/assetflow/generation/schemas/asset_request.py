"""Pedido no nível do produto (plano §52).

Este é o objeto que a API recebe do frontend. Ele fala a língua do AssetFlow
— projeto, tipo de asset, profile — e **não** a língua da IA. É o pipeline
que o traduz para um :class:`ImageGenerationRequest`.

Repare que não existe aqui nenhum campo de motor obrigatório: o padrão é
``auto`` e o EngineResolver decide.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .capability import Capability
from .common import AssetFlowModel, AssetMode, AssetType, QualityLevel, new_id
from .request import EngineSelector, ReferenceImage, StructuralControl
from .resolved_spec import SpecOverrides
from .semantic_prompt import SemanticPrompt
from .strategy import AgentQualityMode, GenerationStrategyType

__all__ = [
    "AssetOutputOverrides",
    "AssetGenerationRequest",
    "ConceptReferenceSelection",
    "GenerationStrategySelection",
    "PixelAgentSelection",
]


class AssetOutputOverrides(AssetFlowModel):
    """O que a **interface** selecionou (plano T→J §9, nível 3).

    São os controles da tela: resolução, paleta, fundo, quantas variações.
    Ficam acima do profile e da leitura do AssetFlow na precedência, e abaixo
    de uma restrição escrita na descrição ou de uma correção manual do spec
    (``AssetGenerationRequest.spec_overrides``).
    """

    variations: int | None = Field(default=None, ge=1, le=32)
    logical_width: int | None = Field(default=None, ge=8, le=1024)
    logical_height: int | None = Field(default=None, ge=8, le=1024)
    render_width: int | None = Field(default=None, ge=64, le=4096)
    render_height: int | None = Field(default=None, ge=64, le=4096)
    palette_size: int | None = Field(default=None, ge=2, le=256)
    transparent: bool | None = None
    #: Vista escolhida no controle de perspectiva (plano T→J §18 e §19).
    #:
    #: Fica neste objeto — e não em ``spec_overrides`` — porque é uma escolha
    #: de *interface*, e a interface é o nível 3 da precedência: uma vista
    #: escrita na descrição ("vista lateral") continua ganhando dela. O nome
    #: da classe fala de saída e esta é a exceção; a alternativa era um quinto
    #: objeto de pedido só para carregar um campo.
    view: str | None = Field(default=None, max_length=40)


class GenerationStrategySelection(AssetFlowModel):
    """O método de criação escolhido na tela (plano de correção §7).

    Um objeto de um campo só, e não um campo solto, porque o plano de correção
    o desenha assim e porque ele vai crescer: prioridade declarada pelo
    usuário (exatidão × velocidade) é o próximo candidato, e ela pertence à
    escolha do método, não ao pedido inteiro.
    """

    mode: GenerationStrategyType = GenerationStrategyType.AUTO


class PixelAgentSelection(AssetFlowModel):
    """A configuração do agente, quando o método for ``pixel_agent`` (§10)."""

    agent_id: str = "assetflow_pixel_agent"
    quality_mode: AgentQualityMode = AgentQualityMode.AUTO
    #: ``None`` deixa o modo de qualidade decidir (plano de correção §25).
    max_iterations: int | None = Field(default=None, ge=0, le=32)
    auto_review: bool = True


class ConceptReferenceSelection(AssetFlowModel):
    """Referência visual opcional para o agente (plano de correção §39).

    Separada de ``engine`` de propósito: o motor que gera uma referência é um
    *supporting engine*, e nunca o gerador do asset (§27).
    """

    enabled: bool = False
    engine_id: str | None = None


class AssetGenerationRequest(AssetFlowModel):
    """Pedido de criação de asset feito por um usuário do AssetFlow."""

    request_id: str = Field(default_factory=lambda: new_id("areq"))
    project_id: str
    user_id: str | None = None

    #: Profile é o caminho recomendado: ele carrega capability + pipeline.
    profile: str | None = None

    #: Alternativa de baixo nível, para diagnóstico ou fluxos avançados.
    capability: Capability | None = None
    pipeline: str | None = None

    asset_type: AssetType | None = None
    mode: AssetMode | None = None

    prompt: str = Field(description="Descrição em linguagem natural feita pelo usuário.")
    negative_prompt: str | None = None

    #: Atributos estruturados que o PromptBuilder converte em SemanticPrompt,
    #: ex.: {"view": "side", "pose": "idle", "appearance": {"armor": "blue"}}.
    attributes: dict[str, Any] = Field(default_factory=dict)

    #: Semântica pronta, escrita por quem pede (plano §26 e §28).
    #:
    #: Quando presente, ela **substitui** o PromptBuilder: o pedido deixa de
    #: dizer "interprete esta frase" e passa a dizer "gere exatamente isto".
    #: É o que permite corrigir uma leitura errada da descrição — trocar
    #: `view` de "side" para "front", tirar um termo do `avoid` — sem
    #: reescrever a frase até o builder concordar.
    #:
    #: O preço é explícito: os padrões de produto do builder (a lista de
    #: `avoid` que barra folha de sprite, a composição centralizada) não são
    #: reaplicados por cima. Quem manda a semântica manda inteira, e o que
    #: não estiver nela não vale. Por isso a interface mostra o JSON completo
    #: antes de deixar editar — o que ela exibe é literalmente o que vai.
    semantic_prompt: SemanticPrompt | None = None

    output: AssetOutputOverrides = Field(default_factory=AssetOutputOverrides)

    #: Correção manual do Final Resolved Spec (plano T→J §9, nível 1).
    #:
    #: É o que a interface envia quando alguém edita o JSON do spec: o nível
    #: de precedência mais alto que existe. O que estiver aqui ganha da
    #: descrição, dos controles da tela, da leitura do AssetFlow e do profile
    #: — e nenhuma camada posterior pode desfazer.
    #:
    #: Diferente de ``semantic_prompt``, que substitui o builder inteiro,
    #: este objeto é **esparso**: o que ele não disser continua sendo
    #: resolvido normalmente pelas camadas de baixo.
    spec_overrides: SpecOverrides | None = None
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    quality: QualityLevel = QualityLevel.STANDARD

    #: **Como** criar (plano de correção §7). Vem antes do motor porque
    #: decide se existe motor: em ``pixel_agent`` não existe.
    #:
    #: ``None`` significa "não opino" e é lido como ``auto`` — que é diferente
    #: de mandar ``auto`` explicitamente só na origem registrada no spec.
    generation_strategy: GenerationStrategySelection | None = None
    #: Configuração do agente. Ignorada quando o método não é o dele.
    pixel_agent: PixelAgentSelection | None = None
    #: Referência conceitual opcional (plano de correção §26).
    concept_reference: ConceptReferenceSelection | None = None

    #: Seleção de motor. Só se aplica ao método ``model`` — pedir motor com
    #: ``pixel_agent`` é recusado pelo resolver, e não ignorado (§38).
    engine: EngineSelector = Field(default_factory=EngineSelector)
    engine_options: dict[str, dict[str, Any]] = Field(default_factory=dict)

    reference_images: tuple[ReferenceImage, ...] = ()
    structural_controls: tuple[StructuralControl, ...] = ()

    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
