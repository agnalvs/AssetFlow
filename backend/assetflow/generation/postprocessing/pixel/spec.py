"""Do Generation Profile para o PixelOutputSpec (plano Pixel §10 e §64).

Aqui moram os dois vocabulários lado a lado, e é o único lugar do sistema em
que isso acontece:

    GenerationProfile   fala de produto     — "personagem pixel, 64×64, 16 cores"
    PixelOutputSpec     fala de arquivo     — "alpha binário, canvas contain, preview 8×"

O módulo ``assetflow.pixel`` não conhece ``GenerationProfile`` (e não pode:
ele precisa servir a qualquer coisa que produza uma imagem). Esta tradução
pertence à camada de pós-processamento, que já conhece as duas pontas.

Precedência, na ordem em que as fontes ganham::

    profile Pixel (config/pixel_profiles.yaml)
        <  Final Resolved Spec (o contrato do job)

O Final Resolved Spec vem por último porque ele **já** é o resultado da
precedência inteira do plano T→J §9 — manual, prompt, interface, inferência,
profile. Quando ninguém pediu nada, ele carrega os próprios valores do profile
e a sobreposição não muda um pixel; quando alguém pediu 32×32, é aqui que
32×32 chega ao arquivo. Antes desta ligação o pedido morria no caminho e o
profile Pixel respondia sozinho — o bug do 32×32 que sai 64×64.

Quando o Generation Profile aponta um ``pixel_profile``, ele é a fonte única
da verdade técnica *de partida* — o Generation Profile não contribui com nada,
justamente para não existirem dois lugares dizendo qual é o limiar de alpha. A
coerência entre os dois arquivos é garantida por teste
(``tests/pixel/test_pixel_profiles_config.py``), não por convenção.

Profiles antigos, que nunca ouviram falar de Pixel Exact, continuam
funcionando: sem ``pixel_profile``, o spec é derivado dos campos que eles já
tinham.
"""

from __future__ import annotations

import logging

from ....pixel.contracts import PixelOutputSpec
from ....pixel.profiles import PixelProfileRegistry
from ...profiles import GenerationProfile
from ...schemas import FinalResolvedSpec

__all__ = ["spec_from_profile"]

_LOG = logging.getLogger("assetflow.generation.postprocessing.pixel")

#: Ampliação usada quando o profile antigo não declara nenhuma (plano Pixel §34).
_DEFAULT_PREVIEW_SCALE = 8


def spec_from_profile(
    profile: GenerationProfile,
    registry: PixelProfileRegistry | None = None,
    *,
    resolved: FinalResolvedSpec | None = None,
) -> PixelOutputSpec | None:
    """Resolve o contrato Pixel Exact deste job.

    Devolve ``None`` quando o pedido não descreve um asset de Pixel Art — é
    o caso do modo Studio, que não tem resolução lógica e para o qual a
    pergunta "isto é Pixel Exact?" não faz sentido.
    """
    spec = _base_spec(profile, registry, resolved)
    if spec is None:
        return None
    return _apply_resolved(spec, resolved)


def _base_spec(
    profile: GenerationProfile,
    registry: PixelProfileRegistry | None,
    resolved: FinalResolvedSpec | None,
) -> PixelOutputSpec | None:
    # Quem decide se este job é Pixel Art é o spec resolvido, não o profile:
    # o modo pode ter sido corrigido à mão, e o profile não fica sabendo.
    if resolved is not None and not resolved.is_pixel:
        return None
    if profile.pixel_profile:
        found = registry.find(profile.pixel_profile) if registry else None
        if found is not None:
            return found
        _LOG.warning(
            "profile '%s' aponta o pixel_profile '%s', que não existe em "
            "pixel_profiles.yaml; derivando o spec do próprio profile",
            profile.id,
            profile.pixel_profile,
        )
    if not profile.output.is_logical:
        return None
    return _derive(profile)


def _derive(profile: GenerationProfile) -> PixelOutputSpec:
    """Constrói um spec a partir dos campos que o profile já tinha.

    Compatibilidade: antes do Pixel Exact, tudo que existia era resolução
    lógica, tamanho de paleta, limiar de alpha e dois interruptores de
    validação. É exatamente esse conjunto que vira spec aqui.
    """
    palette = profile.palette
    if palette.strategy == "fixed" and palette.fixed_colors:
        palette_spec = {"mode": "locked", "colors": palette.fixed_colors}
    else:
        palette_spec = {"mode": "max_colors", "max_colors": palette.size or 16}

    post = profile.postprocessing
    return PixelOutputSpec.model_validate(
        {
            "id": f"derived:{profile.id}",
            "version": "1.0.0",
            "logical_size": {
                "width": int(profile.output.logical_width or 0),
                "height": int(profile.output.logical_height or 0),
            },
            "background": {
                "mode": "transparent" if profile.output.transparent else "solid"
            },
            "alpha": {"mode": "binary", "threshold": post.alpha_threshold},
            "palette": palette_spec,
            "dithering": {"enabled": False},
            "cleanup": {"mode": "conservative" if post.pixel_cleanup else "off"},
            "preview": {
                "enabled": True,
                # Sem profile Pixel não há escala de preview declarada. O
                # thumbnail do profile antigo é a intenção mais próxima que
                # existe — mas só quando ele amplia: escala 1 produziria um
                # `preview.png` idêntico ao asset, que é arquivo à toa.
                "scale": (
                    int(post.thumbnail_scale)
                    if post.thumbnail_scale and post.thumbnail_scale > 1
                    else _DEFAULT_PREVIEW_SCALE
                ),
            },
            "validation": {
                "require_exact_dimensions": bool(post.validate_grid),
                "require_binary_alpha": bool(post.pixel_cleanup),
                "require_palette_limit": bool(post.validate_color_count),
            },
            "metadata": {"derived_from": profile.id},
        }
    )


def _apply_resolved(
    spec: PixelOutputSpec, resolved: FinalResolvedSpec | None
) -> PixelOutputSpec:
    """Grava no contrato de saída o que o job resolveu (plano T→J §14 e §44).

    São os três campos do spec resolvido que descrevem o *arquivo*: resolução
    lógica, paleta e fundo. Eles chegam aqui já decididos — o pós-processador
    não infere nada e não escolhe entre 32 e 64; ele executa.

    E, porque este mesmo ``PixelOutputSpec`` alimenta o validador logo depois,
    o selo PIXEL EXACT passa a ser conferido contra o que a pessoa pediu, e
    não contra o padrão do profile (plano T→J §43 e §44).
    """
    if resolved is None or resolved.logical_resolution is None:
        return spec

    updates: dict[str, object] = {}
    logical = resolved.logical_resolution
    if logical.size != spec.target_size:
        updates["logical_size"] = spec.logical_size.model_copy(
            update={"width": logical.width, "height": logical.height}
        )

    palette = resolved.palette
    if palette is not None and palette.mode == "max_colors" and palette.max_colors:
        if spec.palette.mode == "max_colors":
            updates["palette"] = spec.palette.model_copy(
                update={"max_colors": palette.max_colors}
            )
        else:
            # Paleta travada e limite numérico são contratos incompatíveis. O
            # resolver já recusa o pedido explícito; chegar aqui significa
            # profile Pixel travado contra profile de produto com `size` — uma
            # incoerência de configuração, que some no log e não no arquivo.
            _LOG.warning(
                "spec Pixel '%s' usa paleta travada; o limite de %s cores do "
                "contrato resolvido foi ignorado",
                spec.id,
                palette.max_colors,
            )

    transparent = resolved.background.transparent
    if transparent != (spec.background.mode == "transparent"):
        updates["background"] = spec.background.model_copy(
            update={"mode": "transparent" if transparent else "solid"}
        )

    return spec.model_copy(update=updates) if updates else spec
