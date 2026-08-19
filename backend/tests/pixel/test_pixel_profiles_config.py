"""Coerência entre ``profiles.yaml`` e ``pixel_profiles.yaml`` (plano Pixel §64).

Os dois arquivos descrevem o mesmo asset por ângulos diferentes:

    config/profiles.yaml         o produto   — "Personagem Pixel Art 64×64, 16 cores"
    config/pixel_profiles.yaml   o arquivo   — resolução lógica, paleta, alpha, canvas

Quando um Generation Profile aponta um ``pixel_profile``, é o profile Pixel
que manda: ele é a fonte única da verdade técnica, e os campos equivalentes do
Generation Profile só alimentam a API e a interface
(``postprocessing/pixel/spec.py``).

E aí mora a falha silenciosa que este arquivo existe para impedir. Se alguém
mudar ``palette.size`` de 16 para 8 em ``profiles.yaml`` e esquecer o
``pixel_profiles.yaml``, **nada quebra**: o asset continua saindo com 16
cores, a tela continua anunciando 8, e a divergência só aparece quando um
artista reclamar. Nenhum teste de comportamento pega isso — os dois arquivos
estão internamente corretos; o que está errado é a relação entre eles.

Por isso as verificações daqui são sobre *configuração*, não sobre execução:
elas leem os dois YAML e comparam o que cada um declara.
"""

from __future__ import annotations

from typing import Any

import pytest

from assetflow.generation.postprocessing import spec_from_profile
from assetflow.generation.profiles import ProfileRegistry
from assetflow.pixel.profiles import PixelProfileRegistry
from assetflow.settings import load_settings
from tests.conftest import BACKEND_ROOT

#: A configuração é lida no import porque ela decide quais casos existem: os
#: testes são parametrizados pelos profiles declarados, e não por uma lista
#: escrita à mão que envelheceria em silêncio no primeiro profile novo (§66).
SETTINGS = load_settings(base_dir=BACKEND_ROOT)

PROFILES_RAW: dict[str, Any] = SETTINGS.profiles_config.get("profiles") or {}
PIXEL_RAW: dict[str, Any] = SETTINGS.pixel_profiles_config.get("pixel_profiles") or {}
PALETTES_RAW: dict[str, Any] = SETTINGS.pixel_profiles_config.get("palettes") or {}

PROFILES = ProfileRegistry.from_config(SETTINGS.profiles_config)
PIXEL_PROFILES = PixelProfileRegistry.from_config(SETTINGS.pixel_profiles_config)

#: Só os Generation Profiles que declaram um contrato Pixel Exact.
LINKED_PROFILE_IDS = sorted(
    profile_id
    for profile_id, raw in PROFILES_RAW.items()
    if isinstance(raw, dict) and raw.get("pixel_profile")
)


def test_the_configuration_actually_declares_something():
    """Piso do arquivo: sem profiles ligados, todo teste abaixo seria vácuo."""
    assert PIXEL_RAW, "config/pixel_profiles.yaml não declarou nenhum profile"
    assert LINKED_PROFILE_IDS, (
        "nenhum profile de profiles.yaml aponta um 'pixel_profile' — ou a "
        "configuração regrediu, ou este arquivo de teste ficou obsoleto"
    )


# ---------------------------------------------------------------------------
# Carga: um erro de digitação não pode sumir do mapa
# ---------------------------------------------------------------------------
def test_every_pixel_profile_declared_is_actually_loaded():
    """Profile Pixel inválido é ignorado com log — e some sem quebrar nada.

    ``PixelProfileRegistry.from_config`` engole a exceção de propósito: um
    profile experimental com erro de digitação não pode derrubar o backend
    inteiro. O preço é que ele desaparece silenciosamente, e quem pedir por
    ele só descobre no meio de um job. Comparar o que o YAML declara com o
    que o registro carregou é o que transforma esse sumiço em falha de build.
    """
    declarados = set(PIXEL_RAW)
    carregados = set(PIXEL_PROFILES.ids())
    assert declarados == carregados, (
        "profile(s) Pixel declarado(s) mas não carregado(s) "
        f"(inválidos, veja o log do registry): {sorted(declarados - carregados)}"
    )


@pytest.mark.parametrize("profile_id", list(PIXEL_PROFILES.ids()))
def test_pixel_profile_project_palette_is_resolved(profile_id: str):
    """Uma paleta PROJECT não resolvida vira reprovação em todo job (§11).

    O registro troca ``project_palette`` pela paleta LOCKED correspondente
    ainda no boot. Se o ``palette_id`` não existe em ``palettes:``, ele apenas
    avisa no log e devolve o spec intacto — e o profile sai do boot com um
    modo de paleta que o quantizador não sabe atender, reprovando no check
    ``PX-PALETTE-001`` a cada geração.

    Um profile já resolvido chega aqui como ``locked``; encontrar
    ``project_palette`` significa que a resolução falhou.
    """
    spec = PIXEL_PROFILES.get(profile_id)
    assert spec.palette.mode != "project_palette", (
        f"o profile Pixel '{profile_id}' pede a paleta de projeto "
        f"'{spec.palette.palette_id}', que não existe em palettes: "
        f"{sorted(PALETTES_RAW)}"
    )


# ---------------------------------------------------------------------------
# Coerência entre os dois arquivos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("profile_id", LINKED_PROFILE_IDS)
def test_linked_pixel_profile_exists(profile_id: str):
    """O ``pixel_profile`` apontado precisa existir — e a falta é silenciosa.

    Com um nome inexistente, ``spec_from_profile`` registra um aviso e
    **deriva** um spec dos campos antigos do Generation Profile. O job passa,
    o asset sai, e o contrato técnico em vigor deixa de ser o que o
    ``pixel_profiles.yaml`` descreve. É a divergência mais fácil de introduzir
    (basta renomear um bloco) e a mais difícil de perceber.
    """
    profile = PROFILES.get(profile_id)
    assert PIXEL_PROFILES.find(profile.pixel_profile) is not None, (
        f"o profile '{profile_id}' aponta o pixel_profile "
        f"'{profile.pixel_profile}', que não existe em pixel_profiles.yaml; "
        f"disponíveis: {list(PIXEL_PROFILES.ids())}"
    )


@pytest.mark.parametrize("profile_id", LINKED_PROFILE_IDS)
def test_both_files_declare_the_same_technical_values(profile_id: str):
    """Resolução lógica, orçamento de paleta e limiar de alpha têm de bater.

    O que o código aplica vem do profile Pixel; o que a API publica e a
    interface mostra vem do Generation Profile. Enquanto os dois disserem a
    mesma coisa, tanto faz — no instante em que divergirem, a tela passa a
    mentir sobre o arquivo entregue, e é impossível notar olhando para um
    arquivo só.
    """
    profile = PROFILES.get(profile_id)
    spec = PIXEL_PROFILES.get(profile.pixel_profile)

    assert (profile.output.logical_width, profile.output.logical_height) == (
        spec.logical_size.width,
        spec.logical_size.height,
    ), (
        f"'{profile_id}' declara "
        f"{profile.output.logical_width}x{profile.output.logical_height} e "
        f"'{spec.id}' declara {spec.logical_size.width}x{spec.logical_size.height}"
    )

    assert profile.palette.size == spec.max_colors, (
        f"'{profile_id}' anuncia {profile.palette.size} cores e '{spec.id}' "
        f"aplica {spec.max_colors}"
    )

    assert profile.postprocessing.alpha_threshold == spec.alpha.threshold, (
        f"'{profile_id}' anuncia limiar de alpha "
        f"{profile.postprocessing.alpha_threshold} e '{spec.id}' aplica "
        f"{spec.alpha.threshold}"
    )


@pytest.mark.parametrize("profile_id", LINKED_PROFILE_IDS)
def test_resolved_spec_comes_from_the_pixel_profile(profile_id: str):
    """A resolução precisa entregar o profile Pixel, não um spec derivado.

    Este é o teste que fecha a porta dos dois anteriores: eles comparam o que
    os arquivos *declaram*, este confere o que o sistema *resolve*. Um spec
    derivado tem ``id`` no formato ``derived:<profile>`` — se ele aparecer
    aqui, o Generation Profile voltou a ser a fonte da verdade técnica sem
    que ninguém tenha pedido.
    """
    profile = PROFILES.get(profile_id)
    spec = spec_from_profile(profile, PIXEL_PROFILES)

    assert spec is not None
    assert spec.id == profile.pixel_profile
    assert spec.mode == "pixel_exact"
    assert spec.target_size == (
        profile.output.logical_width,
        profile.output.logical_height,
    )


# ---------------------------------------------------------------------------
# O outro lado: arte 2D não tem contrato Pixel
# ---------------------------------------------------------------------------
def test_studio_profile_has_no_pixel_contract():
    """``studio_character`` não é Pixel Art — perguntar não faz sentido (§10).

    ``spec_from_profile`` devolvendo ``None`` é o que faz o
    ``PixelExactProcessor`` se declarar inaplicável e sair da cadeia. Se ele
    devolvesse um spec qualquer, o modo Studio ganharia resolução lógica,
    paleta reduzida e alpha binário — arte 2D convencional processada como
    sprite.
    """
    profile = PROFILES.get("studio_character")

    assert profile.pixel_profile is None
    assert profile.output.is_logical is False
    assert spec_from_profile(profile, PIXEL_PROFILES) is None
