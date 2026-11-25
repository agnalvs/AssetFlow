"""Topologia corporal, estilo e a classe de cada campo (pesquisa PixelLab).

Três eixos que estavam colapsados em um, e o custo de cada colapso:

``asset.type`` × ``character.body_type``
    Um lobo e um cavaleiro eram ambos `character`, e nada distinguia quatro
    patas de duas pernas. O motor desenhava o lobo em pé. É o mesmo erro que
    fazia uma árvore virar `character`, um nível abaixo.

``style.detail`` × ``style.shading``
    Não existiam. Um sprite pode ser muito detalhado com sombreamento chapado,
    ou simples com sombreamento dramático — tratá-los como um controle só
    perderia metade das combinações.

*origem* × *classe*
    A precedência diz **de onde veio** um valor. A classe diz **o que o
    AssetFlow promete** sobre ele. Sem a segunda, a tela mostra "32×32" e
    "contorno seletivo" com o mesmo peso, e só o primeiro é garantido.
"""

from __future__ import annotations

import pytest

from assetflow.bootstrap import AppContainer
from assetflow.generation.schemas import (
    SPEC_CONSTRAINTS,
    AssetGenerationRequest,
    BodyType,
    ConstraintClass,
    SpecSource,
)


def _spec(container: AppContainer, prompt: str, **kwargs):
    return container.service.resolve_spec(
        AssetGenerationRequest(
            project_id="p", profile="pixel_character_64", prompt=prompt, **kwargs
        )
    )


# ---------------------------------------------------------------------------
# A topologia vem da descrição
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("prompt", "esperado"),
    [
        ("um cavaleiro de armadura", BodyType.HUMANOID),
        ("um lobo cinzento", BodyType.QUADRUPED),
        ("uma águia", BodyType.AVIAN),
        ("a shark", BodyType.AQUATIC),
        ("um dragão vermelho", BodyType.SERPENTINE),
        ("um slime verde", BodyType.AMORPHOUS),
    ],
)
def test_the_subject_says_the_body_shape(
    container: AppContainer, prompt: str, esperado: BodyType
):
    """Quem escreve "um lobo" já disse quadrúpede; ninguém deveria repetir.

    E o caso que mais importa é o goblin: ele é `creature` na categoria e
    `humanoid` na topologia. Categoria diz que **tipo** de coisa é; topologia
    diz que **forma** o corpo tem — e é a forma que o gerador precisa.
    """
    spec = _spec(container, prompt)

    assert spec.character.body_type is esperado
    assert spec.source_of("character.body_type") is SpecSource.INFERENCE


def test_category_and_body_shape_are_different_axes(container: AppContainer):
    """Um goblin é `creature` de corpo humanoide; um lobo, `creature` de
    quatro patas. Colapsar os dois perderia justamente essa distinção."""
    goblin = _spec(container, "um goblin")
    lobo = _spec(container, "um lobo")

    assert goblin.asset.category == lobo.asset.category == "creature"
    assert goblin.character.body_type is BodyType.HUMANOID
    assert lobo.character.body_type is BodyType.QUADRUPED


def test_a_subject_without_a_body_stays_silent(container: AppContainer):
    """`unknown` é silêncio honesto, não palpite.

    Chutar `humanoid` para uma árvore mandaria "humanoid character" ao motor
    junto da palavra "árvore" — e o modelo tentaria conciliar as duas coisas.
    """
    spec = _spec(container, "uma árvore")

    assert spec.character.body_type is BodyType.UNKNOWN
    assert spec.character.body_type.known is False
    assert "character.body_type" not in spec.sources


def test_the_screen_wins_over_the_inference(container: AppContainer):
    """Inferência é o nível 3; a interface é o 4.

    É o que permite pedir um lobo antropomórfico sem reescrever a frase.
    """
    spec = _spec(container, "um lobo", output={"body_type": "humanoid"})

    assert spec.character.body_type is BodyType.HUMANOID
    assert spec.source_of("character.body_type") is SpecSource.UI_SELECTION


def test_the_body_shape_survives_a_type_change_but_not_a_subject_change(
    container: AppContainer,
):
    """A topologia deriva do **sujeito**, e a regra dela segue o sujeito.

    "Sprite sheet de um lobo" continua quadrúpede — o tipo virou `spritesheet`
    e o bicho é o mesmo. Mas trocar o sujeito à mão faz `quadruped` passar a
    descrever um animal que saiu do pedido.
    """
    trocou_tipo = _spec(container, "sprite sheet de um lobo")
    assert trocou_tipo.character.body_type is BodyType.QUADRUPED

    trocou_sujeito = _spec(
        container, "um lobo", spec_overrides={"subject": "uma espada"}
    )
    assert trocou_sujeito.character.body_type is BodyType.UNKNOWN


def test_the_vocabulary_is_configuration(container: AppContainer):
    """Acrescentar um bicho é editar YAML, nunca um `.py`.

    O teste não inspeciona o arquivo: ele confirma que um termo que existe
    **só** em `body_types` é reconhecido. Sem isso, cada animal precisaria ser
    listado duas vezes — e a segunda lista ia ficar desatualizada.
    """
    spec = _spec(container, "um morcego")

    assert spec.character.body_type is BodyType.AVIAN


# ---------------------------------------------------------------------------
# Estilo
# ---------------------------------------------------------------------------
def test_detail_and_shading_are_independent(container: AppContainer):
    """Muito detalhe com sombreamento chapado é uma combinação legítima."""
    spec = _spec(
        container, "um cavaleiro", output={"detail": "high", "shading": "flat"}
    )

    assert spec.style.detail.value == "high"
    assert spec.style.shading.mode.value == "flat"


def test_nobody_opining_leaves_style_neutral(container: AppContainer):
    """`auto` não é "sem estilo": é "ninguém opinou".

    A diferença importa no compilador de prompt — em `auto` ele **não diz
    nada** sobre contorno, em vez de mandar um padrão que ninguém pediu.
    """
    spec = _spec(container, "um cavaleiro")

    assert spec.style.is_default
    assert "style.outline" not in spec.sources


def test_manual_correction_wins_over_the_screen(container: AppContainer):
    spec = _spec(
        container,
        "um cavaleiro",
        output={"outline": "black"},
        spec_overrides={"outline": "selective"},
    )

    assert spec.style.outline.mode.value == "selective"
    assert spec.source_of("style.outline") is SpecSource.MANUAL_OVERRIDE


# ---------------------------------------------------------------------------
# A classe de cada campo
# ---------------------------------------------------------------------------
def test_hard_and_style_are_different_promises(container: AppContainer):
    """A distinção que o selo da interface existe para mostrar."""
    spec = _spec(container, "um cavaleiro 32x32")

    assert spec.constraint_of("logical_resolution") is ConstraintClass.HARD
    assert spec.constraint_of("palette") is ConstraintClass.HARD
    assert spec.constraint_of("asset.type") is ConstraintClass.SEMANTIC
    assert spec.constraint_of("style.outline") is ConstraintClass.STYLE
    assert spec.constraint_of("engine") is ConstraintClass.ENGINE_HINT


def test_an_unclassified_field_promises_the_least(container: AppContainer):
    """Prometer `HARD` por omissão daria a um campo novo uma garantia que
    ninguém escreveu."""
    spec = _spec(container, "x")

    assert spec.constraint_of("campo.que.nao.existe") is ConstraintClass.SEMANTIC


def test_every_hard_field_is_something_the_pipeline_actually_enforces():
    """Um campo marcado `hard` que o Pixel Exact não cobra é uma mentira.

    Os três aqui têm hard check correspondente no `PixelValidator`:
    ``PX-DIM-001``, ``PX-COLOR-001``/``PX-PALETTE-001`` e ``PX-ALPHA-001``.
    """
    duros = {
        campo
        for campo, classe in SPEC_CONSTRAINTS.items()
        if classe is ConstraintClass.HARD
    }

    assert duros == {"logical_resolution", "palette", "background"}


def test_the_classification_reaches_the_interface(container: AppContainer):
    """A tela lê isto do backend em vez de manter a própria tabela."""
    preview = container.service.preview_prompt(
        AssetGenerationRequest(
            project_id="p", profile="pixel_character_64", prompt="um lobo"
        )
    )

    assert preview.constraints["logical_resolution"] == "hard"
    assert preview.constraints["style.outline"] == "style"
    assert preview.constraints["character.body_type"] == "semantic"

