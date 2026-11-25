"""ConstraintResolver — onde a precedência vira código (plano T→J §11).

Este módulo é a resposta ao segundo bug do plano: o usuário edita a resolução
lógica para 32×32 e o asset sai 64×64 assim mesmo. A causa não era um valor
errado em lugar nenhum — era **não existir uma ordem**. O profile respondia
por último porque era quem estava mais perto na hora de perguntar.

A ordem passa a ser explícita, e é única (plano T→J §9)::

    manual override  >  restrição no prompt  >  seleção da interface
                     >  leitura do AssetFlow  >  dedução pela categoria
                     >  profile  >  padrão global

Cada campo é resolvido por um :class:`_Slot`, que guarda valor **e** origem.
Aplicar as camadas de baixo para cima é o algoritmo inteiro: quem chega
depois ganha, e o slot registra quem foi.

Duas garantias que o resolver assume junto (plano T→J §30):

* **nada é corrigido em silêncio.** Um pedido que não pode ser atendido vira
  ``InvalidGenerationRequest`` com o motivo em português — nunca um valor
  trocado por outro sem aviso;
* **nada é inventado.** Campo que ninguém informou continua vazio, com a
  origem que tiver, e o prompt builder decide depois — como *inferência*, e
  não fingindo que a pessoa pediu (plano T→J §23).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Generic, TypeVar

from ..kernel.exceptions import InvalidGenerationRequest
from ..profiles import GenerationProfile
from ..schemas import (
    SPEC_PRECEDENCE,
    AssetGenerationRequest,
    AssetMode,
    AssetType,
    BodyType,
    DetailLevel,
    FinalResolvedSpec,
    LogicalResolution,
    OutlineMode,
    RenderResolution,
    ResolvedAsset,
    ResolvedBackground,
    ResolvedCharacter,
    ResolvedComposition,
    ResolvedEngine,
    ResolvedGeneration,
    ResolvedOutline,
    ResolvedPalette,
    ResolvedShading,
    ResolvedStyle,
    ShadingMode,
    SpecSource,
)
from .classifier import AssetTypeClassifier, Classification
from .constraints import ExplicitConstraintExtractor, ExplicitConstraints

_LOG = logging.getLogger("assetflow.generation.spec")

__all__ = ["ConstraintResolver", "SpecResolution"]

T = TypeVar("T")

#: Origens que representam uma decisão de quem pediu — e não um padrão do
#: sistema. É a fronteira que separa "ninguém disse nada" de "foi pedido".
_USER_SOURCES = frozenset(
    {
        SpecSource.MANUAL_OVERRIDE,
        SpecSource.EXPLICIT_PROMPT,
        SpecSource.UI_SELECTION,
    }
)


@dataclass(slots=True)
class _Slot(Generic[T]):
    """Um campo em resolução: o valor atual e de onde ele veio."""

    value: T | None = None
    source: SpecSource = SpecSource.GLOBAL_DEFAULT

    def set(self, value: T | None, source: SpecSource) -> None:
        """Aplica um valor de uma camada. ``None`` significa "não opino"."""
        if value is None:
            return
        self.value = value
        self.source = source

    @property
    def by_user(self) -> bool:
        return self.source in _USER_SOURCES


@dataclass(frozen=True, slots=True)
class SpecResolution:
    """O spec resolvido junto com o material que o produziu.

    O classificador e o extrator saem daqui porque o resto do sistema ainda
    os aproveita: o prompt builder escolhe o vocabulário pelo tipo
    classificado, e o trace mostra qual termo decidiu.
    """

    spec: FinalResolvedSpec
    classification: Classification
    constraints: ExplicitConstraints


class ConstraintResolver:
    """Transforma pedido + profile em :class:`FinalResolvedSpec`."""

    def __init__(
        self,
        classifier: AssetTypeClassifier | None = None,
        extractor: ExplicitConstraintExtractor | None = None,
    ) -> None:
        self._classifier = classifier or AssetTypeClassifier()
        self._extractor = extractor or ExplicitConstraintExtractor()

    @property
    def classifier(self) -> AssetTypeClassifier:
        return self._classifier

    # ------------------------------------------------------------------
    def resolve(
        self,
        request: AssetGenerationRequest,
        profile: GenerationProfile,
        *,
        pipeline_id: str | None = None,
    ) -> SpecResolution:
        """Resolve o contrato final deste pedido."""
        constraints = self._extractor.extract(request.prompt)
        classification = self._classifier.classify(constraints.subject or request.prompt)

        ui = request.output
        manual = request.spec_overrides

        # -- asset ------------------------------------------------------
        asset_type: _Slot[AssetType] = _Slot()
        asset_type.set(profile.asset.type, SpecSource.PROFILE_DEFAULT)
        asset_type.set(classification.asset_type, SpecSource.INFERENCE)
        asset_type.set(request.asset_type, SpecSource.UI_SELECTION)

        mode: _Slot[AssetMode] = _Slot()
        mode.set(profile.asset.mode, SpecSource.PROFILE_DEFAULT)
        mode.set(request.mode, SpecSource.UI_SELECTION)

        subject: _Slot[str] = _Slot()
        subject.set(request.prompt.strip() or None, SpecSource.EXPLICIT_PROMPT)
        subject.set(constraints.subject or None, SpecSource.EXPLICIT_PROMPT)

        category: _Slot[str] = _Slot()
        category.set(classification.category, SpecSource.INFERENCE)

        # -- resolução lógica -------------------------------------------
        logical_width: _Slot[int] = _Slot()
        logical_height: _Slot[int] = _Slot()
        logical_width.set(profile.output.logical_width, SpecSource.PROFILE_DEFAULT)
        logical_height.set(profile.output.logical_height, SpecSource.PROFILE_DEFAULT)
        logical_width.set(ui.logical_width, SpecSource.UI_SELECTION)
        logical_height.set(ui.logical_height, SpecSource.UI_SELECTION)
        logical_width.set(constraints.logical_width, SpecSource.EXPLICIT_PROMPT)
        logical_height.set(constraints.logical_height, SpecSource.EXPLICIT_PROMPT)

        # -- resolução de render ----------------------------------------
        render_width: _Slot[int] = _Slot(value=512)
        render_height: _Slot[int] = _Slot(value=512)
        render_width.set(profile.output.render_width, SpecSource.PROFILE_DEFAULT)
        render_height.set(profile.output.render_height, SpecSource.PROFILE_DEFAULT)
        render_width.set(ui.render_width, SpecSource.UI_SELECTION)
        render_height.set(ui.render_height, SpecSource.UI_SELECTION)

        # -- paleta ------------------------------------------------------
        locked_colors = (
            tuple(profile.palette.fixed_colors)
            if profile.palette.strategy == "fixed" and profile.palette.fixed_colors
            else ()
        )
        max_colors: _Slot[int] = _Slot()
        if not locked_colors:
            max_colors.set(profile.palette.size, SpecSource.PROFILE_DEFAULT)
            max_colors.set(ui.palette_size, SpecSource.UI_SELECTION)
            max_colors.set(constraints.max_colors, SpecSource.EXPLICIT_PROMPT)

        # -- fundo -------------------------------------------------------
        background: _Slot[str] = _Slot()
        background.set(
            "transparent" if profile.output.transparent else "solid",
            SpecSource.PROFILE_DEFAULT,
        )
        if ui.transparent is not None:
            background.set(
                "transparent" if ui.transparent else "solid", SpecSource.UI_SELECTION
            )
        background.set(constraints.background, SpecSource.EXPLICIT_PROMPT)

        # -- composição / geração ----------------------------------------
        view: _Slot[str] = _Slot()
        view.set(ui.view, SpecSource.UI_SELECTION)
        view.set(constraints.view, SpecSource.EXPLICIT_PROMPT)

        variations: _Slot[int] = _Slot(value=1)
        variations.set(profile.output.variations, SpecSource.PROFILE_DEFAULT)
        variations.set(ui.variations, SpecSource.UI_SELECTION)

        # -- topologia corporal e estilo (pesquisa PixelLab) --------------
        #
        # A topologia é **inferida** do sujeito: quem escreve "um lobo" não
        # precisa dizer quadrúpede num dropdown. Mas inferência é o nível 3 da
        # precedência e a interface é o 4 — então uma escolha explícita na tela
        # ganha, como em qualquer outro campo. É o que permite pedir um lobo
        # antropomórfico sem reescrever a frase.
        body_type: _Slot[str] = _Slot()
        body_type.set(classification.body_type, SpecSource.INFERENCE)
        body_type.set(ui.body_type, SpecSource.UI_SELECTION)

        detail: _Slot[str] = _Slot()
        detail.set(ui.detail, SpecSource.UI_SELECTION)

        outline: _Slot[str] = _Slot()
        outline.set(ui.outline, SpecSource.UI_SELECTION)
        outline_color: _Slot[str] = _Slot()

        shading: _Slot[str] = _Slot()
        shading.set(ui.shading, SpecSource.UI_SELECTION)

        light_direction: _Slot[str] = _Slot()
        light_direction.set(ui.light_direction, SpecSource.UI_SELECTION)

        # -- camada 1: correção manual, que ganha de todas as anteriores --
        if manual is not None:
            asset_type.set(manual.asset_type, SpecSource.MANUAL_OVERRIDE)
            mode.set(manual.mode, SpecSource.MANUAL_OVERRIDE)
            subject.set(
                manual.subject.strip() if manual.subject else None,
                SpecSource.MANUAL_OVERRIDE,
            )
            category.set(manual.category, SpecSource.MANUAL_OVERRIDE)
            logical_width.set(manual.logical_width, SpecSource.MANUAL_OVERRIDE)
            logical_height.set(manual.logical_height, SpecSource.MANUAL_OVERRIDE)
            render_width.set(manual.render_width, SpecSource.MANUAL_OVERRIDE)
            render_height.set(manual.render_height, SpecSource.MANUAL_OVERRIDE)
            if manual.palette_max_colors is not None and locked_colors:
                raise InvalidGenerationRequest(
                    f"o profile '{profile.id}' usa paleta travada; um limite de "
                    "cores não se aplica a ele",
                    detail=_field_error("palette", "o estilo usa uma paleta fixa"),
                )
            max_colors.set(manual.palette_max_colors, SpecSource.MANUAL_OVERRIDE)
            background.set(manual.background, SpecSource.MANUAL_OVERRIDE)
            view.set(manual.view, SpecSource.MANUAL_OVERRIDE)
            variations.set(manual.variations, SpecSource.MANUAL_OVERRIDE)
            body_type.set(manual.body_type, SpecSource.MANUAL_OVERRIDE)
            detail.set(manual.detail, SpecSource.MANUAL_OVERRIDE)
            outline.set(manual.outline, SpecSource.MANUAL_OVERRIDE)
            outline_color.set(manual.outline_color, SpecSource.MANUAL_OVERRIDE)
            shading.set(manual.shading, SpecSource.MANUAL_OVERRIDE)
            light_direction.set(manual.light_direction, SpecSource.MANUAL_OVERRIDE)

        resolved_type = asset_type.value or AssetType.PROP
        resolved_mode = mode.value or AssetMode.PIXEL

        # Categoria inferida pertence ao tipo que a inferiu. Se outra camada
        # trocou o tipo, a categoria antiga descreve outra coisa e não pode
        # sobreviver — "vegetation" em um `character` seria ruído com cara de
        # dado (plano T→J §36).
        if (
            category.source is SpecSource.INFERENCE
            and classification.asset_type is not resolved_type
        ):
            category = _Slot()

        # A topologia corporal é inferida do **sujeito**, e por isso a regra
        # dela é ancorada no sujeito — não no tipo. Um "sprite sheet de um
        # lobo" continua sendo quadrúpede, mesmo com o tipo virando
        # `spritesheet`; mas se alguém trocou o sujeito à mão, `quadruped`
        # passou a descrever um bicho que saiu do pedido.
        if (
            body_type.source is SpecSource.INFERENCE
            and subject.source is SpecSource.MANUAL_OVERRIDE
        ):
            body_type = _Slot()

        # Corpo implícito na categoria: quando nenhuma camada disse a forma do
        # corpo, a categoria resolvida responde — se a tabela do vocabulário
        # (`category_body_types`) diz que todo membro dela tem o mesmo corpo.
        # É aqui, uma vez, e não no recorte nem no prompt: eles só leem o
        # spec. A categoria inferida do texto antigo não deduz nada quando o
        # sujeito foi trocado à mão — a mesma defasagem que descartou o corpo
        # logo acima. E um `unknown` escolhido por alguém não é vazio.
        categoria_defasada = (
            category.source is SpecSource.INFERENCE
            and subject.source is SpecSource.MANUAL_OVERRIDE
        )
        if body_type.value is None and category.value is not None and not categoria_defasada:
            body_type.set(
                self._classifier.taxonomy.body_type_for_category(
                    resolved_type, category.value
                ),
                SpecSource.CATEGORY_INFERENCE,
            )

        sources: dict[str, SpecSource] = {
            "asset.type": asset_type.source,
            "asset.mode": mode.source,
            "asset.subject": subject.source,
            "render_resolution": _strongest(render_width.source, render_height.source),
            "background": background.source,
            "generation.variations": variations.source,
        }
        if category.value is not None:
            sources["asset.category"] = category.source
        if view.value is not None:
            sources["composition.view"] = view.source
        if body_type.value is not None:
            sources["character.body_type"] = body_type.source
        for nome, slot in (
            ("style.detail", detail),
            ("style.outline", outline),
            ("style.shading", shading),
        ):
            if slot.value is not None:
                sources[nome] = slot.source

        notes: list[str] = []

        # -- resolução lógica: existe? é coerente com o modo? -------------
        logical = self._resolve_logical(
            profile=profile,
            mode=resolved_mode,
            width=logical_width,
            height=logical_height,
            sources=sources,
            notes=notes,
        )

        palette = self._resolve_palette(
            profile=profile,
            mode=resolved_mode,
            locked_colors=locked_colors,
            max_colors=max_colors,
            sources=sources,
        )
        if (
            asset_type.source is not SpecSource.PROFILE_DEFAULT
            and asset_type.value is not profile.asset.type
        ):
            notes.append(
                f"tipo do profile ('{profile.asset.type.value}') substituído por "
                f"'{resolved_type.value}' — origem: {asset_type.source.value}"
            )

        capability = request.capability or profile.capability

        engine = self._resolve_engine(request=request, sources=sources)

        spec = FinalResolvedSpec(
            profile_id=profile.id,
            pipeline_id=pipeline_id or request.pipeline or profile.pipeline,
            capability=capability,
            asset=ResolvedAsset(
                type=resolved_type,
                subject=subject.value or "",
                category=category.value,
                mode=resolved_mode,
            ),
            logical_resolution=logical,
            render_resolution=RenderResolution(
                width=render_width.value or 512, height=render_height.value or 512
            ),
            palette=palette,
            background=ResolvedBackground(mode=background.value or "transparent"),
            composition=ResolvedComposition(
                view=view.value,
                centered=True,
                margin_ratio=None,
            ),
            character=ResolvedCharacter(
                body_type=_body_type(body_type.value)
            ),
            style=ResolvedStyle(
                detail=_enum_or_auto(DetailLevel, detail.value),
                outline=ResolvedOutline(
                    mode=_enum_or_auto(OutlineMode, outline.value),
                    color=outline_color.value,
                ),
                shading=ResolvedShading(
                    mode=_enum_or_auto(ShadingMode, shading.value),
                    light_direction=light_direction.value,
                ),
            ),
            generation=ResolvedGeneration(
                variations=variations.value or 1,
                seed=request.seed,
                quality=request.quality,
            ),
            engine=engine,
            sources=sources,
            notes=tuple(notes),
        ).with_identity()

        return SpecResolution(
            spec=spec, classification=classification, constraints=constraints
        )

    # ------------------------------------------------------------------
    def _resolve_engine(
        self,
        *,
        request: AssetGenerationRequest,
        sources: dict[str, SpecSource],
    ) -> ResolvedEngine:
        """Resolve **qual motor** por precedência, como qualquer outro campo.

        A escolha de motor entra na mesma esteira dos demais campos de
        propósito (plano de motores §24): tratá-la como um parâmetro à parte é o que
        produz ``if engine == ...`` espalhado pelo sistema e o que permite que
        uma camada troque em silêncio o motor que a pessoa pediu.

        Duas regras de governança viram código aqui:

        * **plano de motores §25, regra 1** — em ``manual``, o motor pedido é o motor usado. Se
          ele não puder atender, o job falha dizendo isso; não vira outro.
        * **plano de motores §25, regra 2** — por isso o fallback nasce **desligado** em
          ``manual`` e ligado em ``auto``. Quem quiser o contrário escreve
          ``allow_fallback``, e aí a troca passa a ser decisão de quem pediu.
        """
        selector = request.engine
        manual = request.spec_overrides

        # -- nível 3: o seletor da interface -----------------------------
        source = SpecSource.GLOBAL_DEFAULT
        selection_mode = "auto"
        engine_id: str | None = None
        allow_fallback: bool | None = None

        if selector is not None and (
            selector.mode == "manual" or "mode" in selector.model_fields_set
        ):
            selection_mode = selector.mode
            engine_id = selector.engine_id if selector.mode == "manual" else None
            source = SpecSource.UI_SELECTION
        if selector is not None and selector.fallback_explicitly_set:
            allow_fallback = selector.allow_fallback

        # -- nível 1: correção manual do JSON ----------------------------
        if manual is not None:
            if manual.engine_mode is not None:
                selection_mode = manual.engine_mode
                if manual.engine_mode == "auto":
                    engine_id = None
                source = SpecSource.MANUAL_OVERRIDE
            if manual.engine_id is not None:
                engine_id = manual.engine_id
                selection_mode = "manual"
                source = SpecSource.MANUAL_OVERRIDE
            if manual.allow_engine_fallback is not None:
                allow_fallback = manual.allow_engine_fallback

        if selection_mode == "manual" and not engine_id:
            raise InvalidGenerationRequest(
                "seleção manual de motor exige o id do motor",
                detail=_field_error("engine", "faltou o id do motor"),
            )

        if selection_mode == "auto" and source is SpecSource.UI_SELECTION:
            # `auto` explícito é o mesmo que não dizer nada: ninguém decidiu
            # motor, e o roteamento por capacidade decide sozinho. Marcar isso
            # como escolha de interface faria a tela dizer "escolhido" ao lado
            # de um motor que ninguém escolheu.
            source = SpecSource.GLOBAL_DEFAULT

        if allow_fallback is None:
            allow_fallback = selection_mode == "auto"

        sources["engine"] = source
        return ResolvedEngine(
            selection_mode=selection_mode,
            engine_id=engine_id,
            allow_fallback=allow_fallback,
        )

    # ------------------------------------------------------------------
    def _resolve_logical(
        self,
        *,
        profile: GenerationProfile,
        mode: AssetMode,
        width: _Slot[int],
        height: _Slot[int],
        sources: dict[str, SpecSource],
        notes: list[str],
    ) -> LogicalResolution | None:
        """Resolve a resolução lógica — ou recusa o pedido, sem meio-termo."""
        asked_by_user = width.by_user or height.by_user

        if mode is not AssetMode.PIXEL:
            if asked_by_user:
                # Aceitar aqui seria aceitar e ignorar: arte 2D convencional
                # não tem grid lógico, e o número sumiria sem aviso — o
                # sintoma exato que o plano T→J §30 proíbe.
                raise InvalidGenerationRequest(
                    "resolução lógica só existe em Pixel Art; o profile "
                    f"'{profile.id}' produz arte 2D convencional",
                    detail=_field_error(
                        "logical_resolution", "não se aplica a arte 2D convencional"
                    ),
                )
            return None

        if width.value is None or height.value is None:
            if asked_by_user:
                raise InvalidGenerationRequest(
                    "informe largura e altura lógicas juntas — "
                    f"recebi {width.value}×{height.value}",
                    detail=_field_error("logical_resolution", "faltou um dos lados"),
                )
            return None

        if asked_by_user and width.by_user != height.by_user:
            # Metade pedida, metade herdada do profile: daria 32×64 sem que
            # ninguém tivesse pedido 64 de altura. É uma proporção nova
            # aparecendo sozinha, e o plano T→J §30 não admite isso.
            faltante = "altura" if width.by_user else "largura"
            raise InvalidGenerationRequest(
                f"resolução lógica incompleta: informe também a {faltante}. "
                f"Só um dos lados foi pedido, e o outro ({width.value}×"
                f"{height.value}) viria do profile '{profile.id}'",
                detail=_field_error("logical_resolution", f"faltou a {faltante}"),
            )

        try:
            logical = LogicalResolution(width=width.value, height=height.value)
        except ValueError as exc:
            raise InvalidGenerationRequest(
                f"resolução lógica {width.value}×{height.value} fora do suportado "
                "(o limite é de 8 a 1024 pixels por lado)",
                detail=_field_error("logical_resolution", "de 8 a 1024 por lado"),
            ) from exc

        source = _strongest(width.source, height.source)
        sources["logical_resolution"] = source
        sources["logical_resolution.width"] = width.source
        sources["logical_resolution.height"] = height.source

        profile_size = (profile.output.logical_width, profile.output.logical_height)
        if source is not SpecSource.PROFILE_DEFAULT and profile_size != logical.size:
            # Plano T→J §31: o conflito é resolvido a favor do usuário, e o
            # fato de ter havido conflito fica registrado.
            notes.append(
                f"resolução do profile ({profile_size[0]}×{profile_size[1]}) "
                f"substituída por {logical.width}×{logical.height} — "
                f"origem: {source.value}"
            )
        return logical

    def _resolve_palette(
        self,
        *,
        profile: GenerationProfile,
        mode: AssetMode,
        locked_colors: tuple[str, ...],
        max_colors: _Slot[int],
        sources: dict[str, SpecSource],
    ) -> ResolvedPalette | None:
        """Resolve a paleta — ``None`` quando o modo não impõe limite."""
        if locked_colors:
            sources["palette"] = SpecSource.PROFILE_DEFAULT
            return ResolvedPalette(mode="locked", colors=locked_colors)

        if max_colors.value is None:
            if max_colors.by_user:  # pragma: no cover - slot vazio não tem origem
                raise InvalidGenerationRequest("limite de cores inválido")
            return None

        if mode is not AssetMode.PIXEL and max_colors.by_user:
            raise InvalidGenerationRequest(
                "limite de cores só se aplica a Pixel Art; o profile "
                f"'{profile.id}' produz arte 2D convencional",
                detail=_field_error("palette", "não se aplica a arte 2D convencional"),
            )

        try:
            palette = ResolvedPalette(mode="max_colors", max_colors=max_colors.value)
        except ValueError as exc:
            raise InvalidGenerationRequest(
                f"paleta de {max_colors.value} cores fora do suportado "
                "(o limite é de 2 a 256 cores)",
                detail=_field_error("palette", "de 2 a 256 cores"),
            ) from exc

        sources["palette"] = max_colors.source
        return palette


def _body_type(value: str | None) -> BodyType:
    """Texto para :class:`BodyType`; desconhecido vira ``UNKNOWN``.

    Um valor que o vocabulário produziu mas o enum não conhece é sinal de que
    alguém acrescentou uma topologia ao YAML sem acrescentá-la ao contrato.
    Isso vira ``UNKNOWN`` — silêncio — em vez de derrubar a geração: um termo
    novo no vocabulário não pode quebrar um pedido.
    """
    if not value:
        return BodyType.UNKNOWN
    try:
        return BodyType(str(value).strip().lower())
    except ValueError:
        _LOG.warning(
            "topologia corporal '%s' não existe no contrato; tratada como "
            "desconhecida. Acrescente-a a BodyType para que ela chegue ao motor.",
            value,
        )
        return BodyType.UNKNOWN


def _enum_or_auto(enum_cls, value: str | None):
    """Texto para um enum de estilo; ausente ou inválido vira ``AUTO``.

    ``AUTO`` não é "sem estilo": é "ninguém opinou", e o compilador de prompt
    de cada motor decide o que fazer com isso.
    """
    if not value:
        return enum_cls.AUTO
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError:
        return enum_cls.AUTO


def _field_error(campo: str, erro: str) -> dict[str, object]:
    """Detalhe no formato que a interface já sabe listar.

    O handler de 422 da API entrega ``detail.errors`` com ``{campo, erro}``, e
    o painel de leitura renderiza essa lista. Uma recusa do resolver é o mesmo
    tipo de problema — um campo que não serve —, então ela usa o mesmo
    formato em vez de inventar um segundo.
    """
    return {"errors": [{"campo": campo, "erro": erro}]}


def _strongest(*sources: SpecSource) -> SpecSource:
    """A origem de maior precedência entre as informadas."""
    return max(sources, key=SPEC_PRECEDENCE.index)
