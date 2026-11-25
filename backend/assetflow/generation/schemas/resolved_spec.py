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
    "SPEC_CONSTRAINTS",
    "SPEC_PRECEDENCE",
    "BodyType",
    "ConstraintClass",
    "DetailLevel",
    "FinalResolvedSpec",
    "LogicalResolution",
    "OutlineMode",
    "RenderResolution",
    "ResolvedAsset",
    "ResolvedBackground",
    "ResolvedCharacter",
    "ResolvedComposition",
    "ResolvedEngine",
    "ResolvedGeneration",
    "ResolvedOutline",
    "ResolvedPalette",
    "ResolvedPixelPipeline",
    "ResolvedShading",
    "ResolvedStyle",
    "ShadingMode",
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
    #: Deduzido de outro campo já resolvido, não do texto: o corpo que a
    #: categoria implica (``category_body_types`` na taxonomia), quando nenhum
    #: termo do pedido disse a forma. Fica abaixo de ``INFERENCE`` porque é
    #: uma leitura de segunda mão.
    CATEGORY_INFERENCE = "category_inference"
    #: Valor que veio do Generation Profile.
    PROFILE_DEFAULT = "profile_default"
    #: Padrão do próprio contrato, quando nenhuma fonte acima disse nada.
    GLOBAL_DEFAULT = "global_default"


class ConstraintClass(str, Enum):
    """O que o AssetFlow **promete** sobre um campo (pesquisa PixelLab).

    A precedência responde *de onde veio o valor*. Esta pergunta é outra e
    igualmente importante: *o que acontece se o resultado não bater com ele?*

    Sem essa distinção, a interface trata 32×32 e "contorno seletivo" como se
    fossem a mesma promessa — e não são. O primeiro é medido e reprovado; o
    segundo é uma orientação que o motor pode não seguir e que ninguém deveria
    chamar de erro.
    """

    #: O AssetFlow **garante**, deterministicamente. Não bater é reprovação:
    #: resolução lógica, alpha binário, orçamento de cores, paleta travada.
    HARD = "hard"
    #: O motor tenta e o validador **mede**. Não bater é problema de
    #: qualidade do candidato, não erro do sistema: sujeito, tipo, câmera.
    SEMANTIC = "semantic"
    #: Intenção de estilo. O motor tenta, o Pixel Optimizer melhora o que der,
    #: e o validador mede sem reprovar: contorno, sombreamento, detalhe.
    STYLE = "style"
    #: Parâmetro de execução, sem promessa visual: seed, variações, motor.
    ENGINE_HINT = "engine_hint"


#: A classe de cada campo do spec, por caminho pontuado.
#:
#: Ela vive aqui, ao lado da precedência, porque as duas descrevem o mesmo
#: contrato por ângulos diferentes — e porque um campo novo sem classe é um
#: campo sobre o qual o sistema não sabe o que prometer. A interface lê isto
#: para não exibir "contorno: seletivo" com o mesmo peso de "32×32".
SPEC_CONSTRAINTS: dict[str, ConstraintClass] = {
    "logical_resolution": ConstraintClass.HARD,
    "palette": ConstraintClass.HARD,
    "background": ConstraintClass.HARD,
    "asset.type": ConstraintClass.SEMANTIC,
    "asset.subject": ConstraintClass.SEMANTIC,
    "asset.category": ConstraintClass.SEMANTIC,
    "character.body_type": ConstraintClass.SEMANTIC,
    "composition.view": ConstraintClass.SEMANTIC,
    "composition.centered": ConstraintClass.SEMANTIC,
    "composition.margin_ratio": ConstraintClass.SEMANTIC,
    "style.detail": ConstraintClass.STYLE,
    "style.outline": ConstraintClass.STYLE,
    "style.shading": ConstraintClass.STYLE,
    "render_resolution": ConstraintClass.ENGINE_HINT,
    "engine": ConstraintClass.ENGINE_HINT,
    "generation.seed": ConstraintClass.ENGINE_HINT,
    "generation.variations": ConstraintClass.ENGINE_HINT,
    "generation.quality": ConstraintClass.ENGINE_HINT,
}


#: Precedência oficial, da MENOR para a MAIOR (plano T→J §9).
#:
#: A ordem é a regra inteira do módulo; ela está escrita uma vez, aqui, e o
#: resolver apenas percorre esta tupla. Inverter dois itens desta linha é
#: reintroduzir o bug do 32×32 que vira 64×64.
SPEC_PRECEDENCE: tuple[SpecSource, ...] = (
    SpecSource.GLOBAL_DEFAULT,
    SpecSource.PROFILE_DEFAULT,
    SpecSource.CATEGORY_INFERENCE,
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
    def _validate(self) -> ResolvedPalette:
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


class ResolvedPixelPipeline(FrozenModel):
    """O caminho que o asset percorre depois do motor (plano Optimizer §32).

    Um campo do spec que **ninguém escolhe** — e é exatamente isso que ele
    registra. O AssetFlow já teve um seletor de "método de criação" no lugar
    deste bloco, oferecendo "Modelo de imagem" e "Agente Pixel" como se fossem
    alternativas. Não são: o motor produz a imagem, o Optimizer corrige a
    imagem produzida, e os dois acontecem sempre, nesta ordem (§25 e §79).

    Então por que guardá-lo no spec, se o valor é sempre o mesmo? Pelo mesmo
    motivo que o spec guarda a origem de cada campo: um job de seis meses atrás
    precisa dizer, sozinho, por qual pipeline ele passou. Quando o teto de
    iterações mudar, ou quando o revisor por LLM entrar, o histórico continuará
    sabendo o que rodou em cada asset — sem isso, dois assets com notas
    diferentes seriam indistinguíveis quanto à causa.
    """

    #: Sempre ``True`` em geração normal. ``False`` só quando a instalação
    #: desliga o Optimizer em ``config/optimizer.yaml`` — e aí o relatório do
    #: job traz o status ``disabled``, que é a diferença entre uma decisão
    #: registrada e um estágio que sumiu sem aviso.
    optimize: bool = True
    optimizer_id: str = "assetflow_pixel_optimizer"
    #: Teto de voltas do laço de revisão (§19).
    max_iterations: int = Field(default=3, ge=1, le=16)
    #: Quem diagnostica: o revisor determinístico ou um modelo (§42).
    reviewer: str = "heuristic"
    #: ``True`` porque a otimização é imposta pelo servidor, não pedida pelo
    #: cliente (§33 e §34). O campo existe para que o histórico registre que
    #: não houve escolha — não para abrir uma.
    forced: bool = True

    @property
    def optimizes(self) -> bool:
        return self.optimize


class BodyType(str, Enum):
    """A **forma do corpo** do sujeito (pesquisa PixelLab).

    Eixo diferente de ``asset.type`` e de ``asset.category``, e a distinção é
    a mesma que fez uma árvore deixar de virar `character`, um nível abaixo:

        asset.type      que papel o asset cumpre no jogo   -> character
        asset.category  que tipo de coisa é                -> creature
        character.body_type   que forma o corpo tem        -> quadruped

    Um goblin é `creature` de corpo humanoide; um lobo é `creature`
    quadrúpede. Sem este campo os dois chegam ao motor como "character", e
    ele desenha o lobo em pé.

    ``UNKNOWN`` é silêncio honesto: nada no pedido disse a forma do corpo, e
    ele **não** entra no prompt. Chutar `humanoid` seria pior que calar.
    """

    UNKNOWN = "unknown"
    HUMANOID = "humanoid"
    QUADRUPED = "quadruped"
    AVIAN = "avian"
    AQUATIC = "aquatic"
    SERPENTINE = "serpentine"
    AMORPHOUS = "amorphous"

    @property
    def known(self) -> bool:
        return self is not BodyType.UNKNOWN


class ResolvedCharacter(FrozenModel):
    """O que é específico de personagem.

    Preenchido sempre, com o padrão, mesmo em um `prop` — um objeto ausente
    obrigaria cada leitor a tratar ``None`` por um campo que só é lido quando
    o tipo é `character`.
    """

    body_type: BodyType = BodyType.UNKNOWN


class OutlineMode(str, Enum):
    """Como a silhueta é delimitada (pesquisa PixelLab).

    ``AUTO`` não é ausência de escolha: é "o motor decide", que é diferente de
    ``NONE`` ("sem contorno") — e confundir os dois faria "não opinei" virar
    "quero lineless".
    """

    AUTO = "auto"
    NONE = "none"
    BLACK = "black"
    SINGLE_COLOR = "single_color"
    SELECTIVE = "selective"
    ADAPTIVE_DARK = "adaptive_dark"


class ShadingMode(str, Enum):
    """Quanto volume o sprite tem."""

    AUTO = "auto"
    FLAT = "flat"
    BASIC = "basic"
    MEDIUM = "medium"
    DETAILED = "detailed"


class DetailLevel(str, Enum):
    """Densidade de informação — separada de sombreamento de propósito.

    Um sprite pode ser muito detalhado com sombreamento chapado, ou simples
    com sombreamento dramático. Tratá-los como um controle só perde metade
    das combinações.
    """

    AUTO = "auto"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResolvedOutline(FrozenModel):
    """Contorno resolvido."""

    mode: OutlineMode = OutlineMode.AUTO
    #: No Pixel Exact a espessura é sempre um pixel; ``variable`` existe para
    #: quando o modo Studio precisar de outra coisa.
    thickness: Literal["single_pixel", "variable"] = "single_pixel"
    #: Cor fixa do contorno, quando o modo a exige. ``None`` = o motor escolhe.
    color: str | None = None


class ResolvedShading(FrozenModel):
    """Sombreamento resolvido."""

    mode: ShadingMode = ShadingMode.AUTO
    #: De onde vem a luz. Constante em um projeto inteiro é o que faz vários
    #: assets parecerem do mesmo jogo.
    light_direction: str | None = None


class ResolvedStyle(FrozenModel):
    """A intenção de estilo (pesquisa PixelLab).

    Tudo aqui é ``STYLE`` na classificação: o motor tenta, o Pixel Optimizer
    melhora o que der, e o validador mede **sem reprovar**. Um contorno que
    saiu diferente do pedido é um candidato pior, nunca um asset inválido.
    """

    detail: DetailLevel = DetailLevel.AUTO
    outline: ResolvedOutline = Field(default_factory=ResolvedOutline)
    shading: ResolvedShading = Field(default_factory=ResolvedShading)

    @property
    def is_default(self) -> bool:
        """Ninguém opinou sobre estilo neste pedido."""
        return (
            self.detail is DetailLevel.AUTO
            and self.outline.mode is OutlineMode.AUTO
            and self.shading.mode is ShadingMode.AUTO
        )


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
    #: O que é específico de personagem. Lido só quando `asset.type` é
    #: `character`; nos demais tipos fica no padrão e ninguém o consulta.
    character: ResolvedCharacter = Field(default_factory=ResolvedCharacter)
    #: A intenção de estilo — contorno, sombreamento, densidade de detalhe.
    style: ResolvedStyle = Field(default_factory=ResolvedStyle)
    generation: ResolvedGeneration = Field(default_factory=ResolvedGeneration)
    #: A decisão de motor deste job (plano de motores §5). Ela entra no spec, e não fica
    #: só no pedido, porque é uma decisão resolvida por precedência como
    #: qualquer outra — e porque o pipeline não pode reabri-la (§37).
    #:
    #: É a **única** escolha de tecnologia que quem pede um asset faz (plano
    #: Optimizer §25).
    engine: ResolvedEngine = Field(default_factory=ResolvedEngine)
    #: O que acontece depois do motor (plano Optimizer §32). Ninguém escolhe:
    #: está no spec para ficar registrado, não para ser decidido.
    pixel_pipeline: ResolvedPixelPipeline = Field(
        default_factory=ResolvedPixelPipeline
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

        Hoje a resposta é sempre sim: existe **um** caminho de geração, e ele
        começa em um motor (plano Optimizer §25). A propriedade fica porque
        ela é a pergunta certa, e porque o resto do sistema deve continuar
        perguntando ao spec em vez de assumir — foi assumir que produziu o
        seletor que misturava motor e estratégia.
        """
        return True

    def source_of(self, field: str) -> SpecSource:
        """Origem de um campo; ``GLOBAL_DEFAULT`` quando ninguém opinou."""
        return self.sources.get(field, SpecSource.GLOBAL_DEFAULT)

    def constraint_of(self, field: str) -> ConstraintClass:
        """O que o AssetFlow promete sobre este campo.

        Campo sem classe declarada cai em ``SEMANTIC`` — a resposta
        conservadora: promete-se medir, não garantir. Prometer ``HARD`` por
        omissão faria um campo novo nascer com uma garantia que ninguém
        escreveu.
        """
        return SPEC_CONSTRAINTS.get(field, ConstraintClass.SEMANTIC)

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
            },
        )

    def with_identity(self) -> FinalResolvedSpec:
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

    #: Topologia corporal e estilo, corrigidos à mão no JSON final.
    body_type: Literal[
        "unknown", "humanoid", "quadruped", "avian", "aquatic",
        "serpentine", "amorphous",
    ] | None = None
    detail: Literal["auto", "low", "medium", "high"] | None = None
    outline: Literal[
        "auto", "none", "black", "single_color", "selective", "adaptive_dark"
    ] | None = None
    outline_color: str | None = None
    shading: Literal["auto", "flat", "basic", "medium", "detailed"] | None = None
    light_direction: str | None = None

    #: Motor corrigido à mão. É o nível mais alto da precedência também aqui:
    #: um id escrito no JSON final ganha do seletor da tela.
    engine_id: str | None = None
    engine_mode: Literal["auto", "manual"] | None = None
    allow_engine_fallback: bool | None = None

    #: Não existe aqui um campo para o Pixel Optimizer, e a ausência é a
    #: regra: correção manual é o nível mais alto da precedência **entre as
    #: camadas que decidem o asset**, e a otimização não é uma delas — ela é
    #: parte do pipeline (plano Optimizer §33 e §46). Um campo aqui daria a
    #: quem edita o JSON final um poder que nem a interface tem.

    @property
    def is_empty(self) -> bool:
        return not self.model_dump(exclude_none=True)
