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

__all__ = [
    "SPEC_PRECEDENCE",
    "FinalResolvedSpec",
    "LogicalResolution",
    "RenderResolution",
    "ResolvedAsset",
    "ResolvedBackground",
    "ResolvedComposition",
    "ResolvedGeneration",
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
            mode="json", exclude={"spec_id", "spec_hash", "sources", "notes"}
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

    @property
    def is_empty(self) -> bool:
        return not self.model_dump(exclude_none=True)
