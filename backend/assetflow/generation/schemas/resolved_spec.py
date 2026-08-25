"""Final Resolved Spec — o contrato determinístico de geração (plano T→J §15).

O que este módulo muda de fundamental: o JSON que o AssetFlow monta a partir
da descrição deixa de ser uma **sugestão** e passa a ser um **contrato**.
Antes, cada camada consultava a fonte que tinha à mão — o pipeline olhava o
profile, o pós-processamento olhava o profile de novo, a validação olhava o
profile mais uma vez — e uma correção feita à mão não tinha por onde entrar.
Era assim que um pedido de 32×32 saía 64×64 sem ninguém mentir: cada camada
respondia com o que sabia, e o que a pessoa pediu não estava em lugar nenhum.

Agora existe **um** objeto, resolvido uma vez, imutável durante o job::

    ParsedSpec  ->  ConstraintResolver  ->  FinalResolvedSpec  ->  Job

Regra que acompanha o objeto (plano T→J §37): nenhum componente recalcula ou
reinfere um campo que já exista aqui. Pipeline, pós-processamento, validação
e interface **leem**; nenhum deles reinterpreta o prompt.

Estes modelos ficam em ``schemas/`` porque são linguagem comum — API, job,
pipeline e storage falam todos por eles. A *lógica* que os produz
(taxonomia, classificador, extrator, resolver) mora em
``generation/spec/``, que é onde ela pode importar profile sem que os
contratos passem a depender de produto.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from .capability import Capability
from .common import AssetFlowModel, AssetMode, AssetType, FrozenModel, QualityLevel
from .strategy import AgentQualityMode, GenerationStrategyType

__all__ = [
    "SPEC_PRECEDENCE",
    "FinalResolvedSpec",
    "LogicalResolution",
    "RenderResolution",
    "ResolvedAsset",
    "ResolvedBackground",
    "ResolvedComposition",
    "ResolvedConceptReference",
    "ResolvedEngine",
    "ResolvedGeneration",
    "ResolvedPixelAgent",
    "ResolvedStrategy",
    "ResolvedPalette",
    "SpecOverrides",
    "SpecSource",
]


class SpecSource(str, Enum):
    """De onde veio o valor de um campo (plano T→J §16 e §23).

    Guardar a origem não é luxo de observabilidade: é o que separa "o usuário
    pediu 64×64" de "ninguém disse nada e o profile respondeu 64×64". Sem
    essa distinção, o sistema não tem como saber o que pode sobrescrever — e
    passa a tratar o próprio padrão como se fosse pedido explícito.
    """

    #: Edição manual do spec, feita na interface. Ganha de tudo.
    MANUAL_OVERRIDE = "manual_override"
    #: Restrição escrita na própria descrição ("32x32", "8 colors").
    EXPLICIT_PROMPT = "explicit_prompt"
    #: Controle escolhido na interface (dropdown de tipo, resolução, paleta).
    UI_SELECTION = "ui_selection"
    #: Leitura do AssetFlow — classificador semântico e prompt builder.
    INFERENCE = "inference"
    #: Valor que veio do Generation Profile.
    PROFILE_DEFAULT = "profile_default"
    #: Padrão do próprio contrato, quando nenhuma fonte acima disse nada.
    GLOBAL_DEFAULT = "global_default"


#: Precedência oficial, da MENOR para a MAIOR (plano T→J §9).
#:
#: A ordem é a regra inteira do módulo; ela está escrita uma vez, aqui, e o
#: resolver apenas percorre esta tupla. Inverter dois itens desta linha é
#: reintroduzir o bug do 32×32 que vira 64×64.
SPEC_PRECEDENCE: tuple[SpecSource, ...] = (
    SpecSource.GLOBAL_DEFAULT,
    SpecSource.PROFILE_DEFAULT,
    SpecSource.INFERENCE,
    SpecSource.UI_SELECTION,
    SpecSource.EXPLICIT_PROMPT,
    SpecSource.MANUAL_OVERRIDE,
)


class ResolvedAsset(FrozenModel):
    """O que está sendo desenhado (plano T→J §6).

    ``type`` e ``subject`` são conceitos separados de propósito.
    ``{"asset_type": "character"}`` sozinho não descreve nada: não diz se é um
    cavaleiro ou uma bruxa. E uma árvore não vira personagem só porque o
    profile pedido se chama `pixel_character_64`.
    """

    type: AssetType = AssetType.PROP
    #: O sujeito em si — "tree", "female mage". Vem da descrição da pessoa.
    subject: str = ""
    #: Categoria dentro do tipo — "vegetation", "weapon", "humanoid".
    category: str | None = None
    mode: AssetMode = AssetMode.PIXEL


class LogicalResolution(FrozenModel):
    """Resolução **do asset** — o tamanho real do arquivo entregue.

    Nome longo por decisão de projeto (plano T→J §12 e §13): existiam dois
    conceitos disputando as palavras ``width``/``height``, e é dessa
    ambiguidade que nasce a classe inteira de bugs em que 32 vira 64. O
    tamanho em que o motor gera é :class:`RenderResolution`, e os dois nunca
    mais compartilham um nome.
    """

    width: int = Field(ge=8, le=1024)
    height: int = Field(ge=8, le=1024)

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)


class RenderResolution(FrozenModel):
    """Resolução **do motor** — em quantos pixels a imagem bruta é gerada.

    Não é o tamanho do asset: em Pixel Art o motor gera em 512 ou 1024 e o
    AssetFlow reduz para o grid lógico com as regras dele.
    """

    width: int = Field(ge=64, le=4096)
    height: int = Field(ge=64, le=4096)

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)


class ResolvedPalette(FrozenModel):
    """Paleta resolvida do asset."""

    mode: Literal["max_colors", "locked"] = "max_colors"
    max_colors: int | None = Field(default=None, ge=2, le=256)
    colors: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate(self) -> "ResolvedPalette":
        if self.mode == "locked" and not self.colors:
            raise ValueError("paleta 'locked' exige a lista de cores")
        return self


class ResolvedBackground(FrozenModel):
    """Fundo resolvido do asset."""

    mode: Literal["transparent", "solid"] = "transparent"

    @property
    def transparent(self) -> bool:
        return self.mode == "transparent"


class ResolvedComposition(FrozenModel):
    """Como o sujeito ocupa o quadro."""

    view: str | None = None
    centered: bool = True
    margin_ratio: float | None = Field(default=None, ge=0.0, le=0.4)


class ResolvedEngine(FrozenModel):
    """Qual motor vai atender este job, e por quê (plano de motores §5 e §17).

    Este campo é o que separa "o AssetFlow escolheu" de "eu escolhi": sem ele,
    a seleção do usuário era um parâmetro solto no pedido, que cada camada
    podia reinterpretar — e a interface não tinha como afirmar qual motor
    seria usado antes de gerar.

    ``engine_id`` está preenchido nos dois modos, e significa coisas
    diferentes em cada um:

    ``manual``
        o motor **exigido**. Se ele não puder atender, o job falha com a razão
        — trocar por outro em silêncio é o que o plano de motores §24 proíbe.
    ``auto``
        o motor **preferido** pela :class:`AutoEnginePolicy`, com o motivo em
        ``reason``. É preferência, não exigência: se ele cair, o fallback
        entra, porque em ``auto`` a escolha nunca foi da pessoa (plano de motores §25, regra 2).

    ``None`` significa que ninguém opinou e nenhuma política respondeu — o
    roteamento por capacidade decide sozinho, como sempre decidiu.
    """

    selection_mode: Literal["auto", "manual"] = "auto"
    engine_id: str | None = None
    #: Trocar de motor quando o escolhido falhar. Em ``manual`` o padrão é
    #: ``False``: respeitar a escolha é a regra 1 do plano de motores §25.
    allow_fallback: bool = True
    #: Por que este motor, em português. Vazio em seleção manual: o motivo é
    #: "foi pedido", e escrever isso seria ruído.
    reason: str = ""


class ResolvedStrategy(FrozenModel):
    """Como este asset será criado (plano de correção §7 e §41).

    ``requested`` guarda o que a pessoa escolheu — inclusive ``auto`` — e
    ``mode`` guarda o que isso virou depois da resolução. Os dois, e não só o
    segundo: sem o pedido original não há como saber, olhando um job antigo,
    se a estratégia foi decidida por alguém ou pelo sistema. É a mesma razão
    pela qual o spec guarda a *origem* de cada campo.
    """

    requested: GenerationStrategyType = GenerationStrategyType.AUTO
    mode: GenerationStrategyType = GenerationStrategyType.MODEL
    #: Por que esta estratégia, em português. Vazio quando foi escolhida à mão:
    #: o motivo é "foi pedida", e escrevê-lo seria ruído.
    reason: str = ""

    @property
    def was_automatic(self) -> bool:
        return self.requested is GenerationStrategyType.AUTO

    @property
    def uses_engine(self) -> bool:
        return self.mode.uses_engine


class ResolvedPixelAgent(FrozenModel):
    """A configuração do agente, quando a estratégia for ``pixel_agent``.

    Fica preenchida sempre — inclusive em ``model`` —, com os padrões. Um
    objeto ausente obrigaria cada leitor a lidar com ``None``, e o campo que
    importa (``agent_id``) só é lido quando a estratégia é a do agente.
    """

    agent_id: str = "assetflow_pixel_agent"
    quality_mode: AgentQualityMode = AgentQualityMode.AUTO
    #: ``None`` deixa o modo de qualidade decidir (plano de correção §25).
    max_iterations: int | None = Field(default=None, ge=0, le=32)
    auto_review: bool = True


class ResolvedConceptReference(FrozenModel):
    """Referência visual opcional para o agente (plano de correção §26 e §27).

    Quando ligada, um motor de imagem gera uma referência que o agente usa
    como inspiração — e **a referência não é o asset**. O motor entra como
    *supporting engine*, nunca como gerador final, e é por isso que este campo
    existe separado de ``engine``: no mesmo campo, "o FLUX me ajudou a pensar"
    e "o FLUX gerou isto" ficariam indistinguíveis no histórico.

    Previsto no contrato, ainda não executado: o agente de hoje desenha sem
    referência. O campo existe para que ligá-lo depois não mude o formato do
    spec nem do histórico.
    """

    enabled: bool = False
    engine_id: str | None = None


class ResolvedGeneration(FrozenModel):
    """Parâmetros da execução em si."""

    variations: int = Field(default=1, ge=1, le=32)
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    quality: QualityLevel = QualityLevel.STANDARD


class FinalResolvedSpec(FrozenModel):
    """A especificação final — a única verdade da geração (plano T→J §15).

    É **imutável** (``FrozenModel``) porque a imutabilidade é o mecanismo, não
    um detalhe de estilo: depois de resolvido, nenhuma camada tem como mudar
    32 para 64, nem por engano nem por um `model_copy` bem-intencionado.
    Quem precisar de outro valor precisa resolver outro spec, e resolver
    outro spec muda o ``spec_hash``.
    """

    #: Identidade determinística: o mesmo conteúdo sempre gera o mesmo id.
    #: Não é UUID de propósito — dois pedidos equivalentes precisam ser
    #: reconhecíveis como equivalentes (plano T→J §34).
    spec_id: str = ""
    spec_hash: str = ""

    profile_id: str
    pipeline_id: str
    capability: Capability

    asset: ResolvedAsset = Field(default_factory=ResolvedAsset)
    #: ``None`` em arte 2D convencional, onde não existe grid lógico.
    logical_resolution: LogicalResolution | None = None
    render_resolution: RenderResolution
    #: ``None`` quando o modo não impõe limite de cores.
    palette: ResolvedPalette | None = None
    background: ResolvedBackground = Field(default_factory=ResolvedBackground)
    composition: ResolvedComposition = Field(default_factory=ResolvedComposition)
    generation: ResolvedGeneration = Field(default_factory=ResolvedGeneration)
    #: **Como** o asset será criado (plano de correção §7). Vem antes do
    #: motor porque decide se existe motor: em ``pixel_agent`` não existe.
    strategy: ResolvedStrategy = Field(default_factory=ResolvedStrategy)
    #: A decisão de motor deste job (plano de motores §5). Ela entra no spec, e não fica
    #: só no pedido, porque é uma decisão resolvida por precedência como
    #: qualquer outra — e porque o pipeline não pode reabri-la (§37).
    #:
    #: Só é lida quando ``strategy.mode`` usa motor. Em ``pixel_agent`` ela
    #: fica no padrão e ninguém a consulta.
    engine: ResolvedEngine = Field(default_factory=ResolvedEngine)
    #: A configuração do agente, quando a estratégia for a dele.
    pixel_agent: ResolvedPixelAgent = Field(default_factory=ResolvedPixelAgent)
    #: Referência visual opcional do agente (plano de correção §39).
    concept_reference: ResolvedConceptReference = Field(
        default_factory=ResolvedConceptReference
    )

    #: Origem de cada campo resolvido (plano T→J §16). Chaves usam caminho
    #: pontuado: ``"logical_resolution"``, ``"asset.type"``, ``"palette"``.
    sources: dict[str, SpecSource] = Field(default_factory=dict)

    #: Decisões que valem registro em texto — "profile default overridden by
    #: user" e afins (plano T→J §31). Nunca contêm erro: erro é exceção.
    notes: tuple[str, ...] = ()

    @property
    def mode(self) -> AssetMode:
        return self.asset.mode

    @property
    def is_pixel(self) -> bool:
        return self.logical_resolution is not None

    @property
    def uses_engine(self) -> bool:
        """Este job vai despachar para um motor de imagem?

        Perguntar isto ao spec, e não ao pedido, é o que impede o resto do
        sistema de reabrir a decisão (plano T→J §37).
        """
        return self.strategy.uses_engine

    def source_of(self, field: str) -> SpecSource:
        """Origem de um campo; ``GLOBAL_DEFAULT`` quando ninguém opinou."""
        return self.sources.get(field, SpecSource.GLOBAL_DEFAULT)

    def fingerprint(self) -> dict[str, Any]:
        """Os valores que definem a geração — sem identidade nem rastro.

        ``sources`` e ``notes`` ficam de fora porque descrevem *como* se
        chegou ao valor, não *qual* é o valor. Dois pedidos que resultam em
        64×64 com 16 cores produzem o mesmo asset, tenham vindo do profile ou
        da mão do usuário — e por isso precisam ter o mesmo hash.
        """
        return self.model_dump(
            mode="json",
            exclude={
                "spec_id": True,
                "spec_hash": True,
                "sources": True,
                "notes": True,
                # O motor entra no hash — dois specs iguais em tudo menos no
                # motor produzem assets diferentes, e precisam ser
                # distinguíveis. O *motivo* da escolha, não: ele descreve
                # como se chegou ao motor, igual a `sources`.
                "engine": {"reason"},
                # Mesmo argumento para a estratégia: o modo resolvido entra no
                # hash (ele muda o asset), o motivo não (ele explica a
                # escolha). `requested` fica de fora porque dois pedidos que
                # chegam ao mesmo modo produzem o mesmo asset, tendo um vindo
                # de "auto" e o outro de escolha explícita.
                "strategy": {"reason", "requested"},
            },
        )

    def with_identity(self) -> "FinalResolvedSpec":
        """Devolve o spec com ``spec_id``/``spec_hash`` calculados."""
        payload = json.dumps(self.fingerprint(), sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return self.model_copy(
            update={"spec_id": f"spec_{digest[:12]}", "spec_hash": digest}
        )


class SpecOverrides(AssetFlowModel):
    """Correção feita **à mão** sobre o spec (plano T→J §9, nível 1).

    É o nível de precedência mais alto que existe: o que estiver aqui ganha da
    descrição, da interface, da leitura do AssetFlow e do profile. Todos os
    campos são opcionais — o que não for dito continua sendo resolvido pelas
    camadas de baixo.

    Por que este objeto é separado de ``AssetOutputOverrides``, que tem campos
    parecidos: eles não representam a mesma coisa. ``output`` é *o que a
    interface selecionou* (nível 3); este é *o que a pessoa corrigiu na mão*
    (nível 1). Colapsar os dois em um só apagaria a diferença entre "o
    dropdown estava em 64" e "eu digitei 32 e quero 32".
    """

    asset_type: AssetType | None = None
    subject: str | None = None
    category: str | None = None
    mode: AssetMode | None = None

    logical_width: int | None = Field(default=None, ge=8, le=1024)
    logical_height: int | None = Field(default=None, ge=8, le=1024)
    render_width: int | None = Field(default=None, ge=64, le=4096)
    render_height: int | None = Field(default=None, ge=64, le=4096)

    palette_max_colors: int | None = Field(default=None, ge=2, le=256)
    background: Literal["transparent", "solid"] | None = None

    view: str | None = None
    variations: int | None = Field(default=None, ge=1, le=32)

    #: Motor corrigido à mão. É o nível mais alto da precedência também aqui:
    #: um id escrito no JSON final ganha do seletor da tela.
    engine_id: str | None = None
    engine_mode: Literal["auto", "manual"] | None = None
    allow_engine_fallback: bool | None = None

    #: Método de criação corrigido à mão (plano de correção §7).
    strategy: Literal["auto", "model", "pixel_agent"] | None = None
    agent_id: str | None = None
    agent_quality: Literal["auto", "fast", "balanced", "detailed"] | None = None
    agent_max_iterations: int | None = Field(default=None, ge=0, le=32)
    agent_auto_review: bool | None = None
    concept_reference_enabled: bool | None = None
    concept_reference_engine_id: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.model_dump(exclude_none=True)
