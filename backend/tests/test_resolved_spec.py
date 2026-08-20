"""Do texto ao contrato — os testes obrigatórios do plano Text→JSON.

Dois defeitos motivaram o plano, e os dois eram invisíveis pelo mesmo motivo:
não existia um lugar onde a decisão ficasse registrada.

    "tree"          ->  {"asset_type": "character"}    §40
    32×32 pedido    ->  64×64 entregue e validado      §41, §42

O arquivo é dividido pelas seções do plano. Os testes de §40, §41 e §42 são
declarados permanentes por ele — são a prova de que os dois sintomas não
voltaram, e não devem ser afrouxados para acomodar mudança de comportamento.
"""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image
from pydantic import ValidationError

from assetflow.bootstrap import AppContainer
from assetflow.generation.kernel.exceptions import InvalidGenerationRequest
from assetflow.generation.schemas import (
    AssetGenerationRequest,
    AssetOutputOverrides,
    AssetType,
    JobStatus,
    SpecOverrides,
    SpecSource,
)

from tests.conftest import process_next_job, run


def _request(container: AppContainer, prompt: str, **overrides) -> AssetGenerationRequest:
    payload: dict = {
        "project_id": "project_spec",
        "profile": "pixel_character_64",
        "prompt": prompt,
    }
    payload.update(overrides)
    return AssetGenerationRequest(**payload)


def _resolve(container: AppContainer, prompt: str, **overrides):
    return container.service.resolve_spec(_request(container, prompt, **overrides))


def _completed_job(container: AppContainer, request: AssetGenerationRequest):
    async def scenario():
        job = await container.service.submit(request)
        assert await process_next_job(container)
        return await container.service.get_job(job.id)

    job = run(scenario())
    assert job.status is JobStatus.COMPLETED, job.error
    return job


# ---------------------------------------------------------------------------
# §39 — a tabela de classificação
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("prompt", "esperado"),
    [
        ("tree", AssetType.PROP),
        ("árvore", AssetType.PROP),
        ("knight", AssetType.CHARACTER),
        ("guerreiro", AssetType.CHARACTER),
        ("stone", AssetType.PROP),
        ("potion", AssetType.PROP),
        ("forest background", AssetType.BACKGROUND),
        ("floresta de fundo", AssetType.BACKGROUND),
        ("grass tileset", AssetType.TILESET),
    ],
)
def test_classification_table(container: AppContainer, prompt: str, esperado: AssetType):
    """A tabela literal do plano T→J §39, nas duas línguas.

    Note o par ``grass tileset``/``tree``: as duas frases contêm um termo de
    prop, e só uma delas é um prop. O que decide é o *marker* — o termo que
    nomeia o tipo de asset ganha do termo que nomeia o sujeito.
    """
    assert _resolve(container, prompt).asset.type is esperado


def test_classification_is_case_and_accent_insensitive(container: AppContainer):
    """Quem digita "ARVORE" sem acento pediu a mesma coisa que "árvore"."""
    for escrita in ("ARVORE", "Árvore", "arvore"):
        assert _resolve(container, escrita).asset.type is AssetType.PROP


def test_unknown_subject_keeps_the_profile_type(container: AppContainer):
    """Plano T→J §23: o que o sistema não sabe, ele não inventa.

    "algo azul e brilhante" não diz o tipo. O classificador cala, o profile
    responde — e a origem registrada diz exatamente isso, para que ninguém
    depois confunda o padrão com um pedido.
    """
    spec = _resolve(container, "algo azul e brilhante")

    assert spec.asset.type is AssetType.CHARACTER  # veio do pixel_character_64
    assert spec.source_of("asset.type") is SpecSource.PROFILE_DEFAULT


# ---------------------------------------------------------------------------
# §40 — a regressão da árvore (permanente)
# ---------------------------------------------------------------------------
def test_tree_is_a_prop_not_a_character(container: AppContainer):
    """O bug original, em uma linha: uma árvore não é um personagem.

    O pedido usa `pixel_character_64` de propósito — é o profile que a
    interface manda para o modo Pixel Art, e era ele que impunha
    ``asset_type: character`` a qualquer coisa que fosse pedida.
    """
    resolved = _resolve(container, "tree")

    assert resolved.asset.type is AssetType.PROP
    assert resolved.asset.subject == "tree"
    assert resolved.asset.category == "vegetation"
    assert resolved.source_of("asset.type") is SpecSource.INFERENCE


def test_the_prop_reading_reaches_the_prompt(container: AppContainer):
    """Classificar sem mudar o prompt não teria resolvido nada.

    A consequência prática de "tree" ser prop é usar o vocabulário de prop: a
    lista de `avoid` passa a barrar personagem e mão, e a pose de personagem
    desaparece. Enquanto a árvore era classificada como personagem, ela era
    descrita ao motor como personagem.
    """
    preview = container.service.preview_prompt(_request(container, "tree"))

    assert preview.resolved.asset.type is AssetType.PROP
    assert preview.semantic.pose is None
    assert "characters" in preview.semantic.avoid
    assert "multiple characters" not in preview.semantic.avoid


def test_the_type_dropdown_beats_the_classifier(container: AppContainer):
    """Plano T→J §9: seleção da interface ganha da inferência.

    É o controle "Tipo: [Automático ▾]" do §18. Quem escolher "Personagem"
    para uma árvore recebe um personagem — a leitura automática é um palpite
    útil, não uma tutela.
    """
    resolved = _resolve(container, "tree", asset_type="character")

    assert resolved.asset.type is AssetType.CHARACTER
    assert resolved.source_of("asset.type") is SpecSource.UI_SELECTION
    # A categoria era do prop; com outro tipo ela descreveria outra coisa.
    assert resolved.asset.category is None


# ---------------------------------------------------------------------------
# §41 — a regressão da resolução (permanente)
# ---------------------------------------------------------------------------
def test_manual_override_beats_the_profile_resolution(container: AppContainer):
    """Profile diz 64×64, a pessoa digitou 32×32 — vale 32×32."""
    resolved = _resolve(
        container,
        "knight",
        spec_overrides=SpecOverrides(logical_width=32, logical_height=32),
    )

    assert resolved.logical_resolution is not None
    assert resolved.logical_resolution.size == (32, 32)
    assert resolved.source_of("logical_resolution") is SpecSource.MANUAL_OVERRIDE


def test_the_overridden_profile_value_is_recorded(container: AppContainer):
    """Plano T→J §31: o conflito é resolvido, e o fato dele fica registrado."""
    resolved = _resolve(
        container,
        "knight",
        spec_overrides=SpecOverrides(logical_width=32, logical_height=32),
    )

    assert any(
        "64×64" in nota and "32×32" in nota for nota in resolved.notes
    ), resolved.notes


def test_explicit_prompt_constraints_win_over_the_interface(container: AppContainer):
    """Plano T→J §25: "tree 32x32, 8 colors, transparent background".

    Os três valores estão escritos na frase. Nenhum deles pode ser substituído
    pelo profile — e o sujeito que segue para o motor é "tree", sem os números
    junto (senão o modelo desenha o texto).
    """
    resolved = _resolve(
        container,
        "tree 32x32, 8 colors, transparent background",
        output=AssetOutputOverrides(
            logical_width=64, logical_height=64, palette_size=16
        ),
    )

    assert resolved.asset.subject == "tree"
    assert resolved.asset.type is AssetType.PROP
    assert resolved.logical_resolution.size == (32, 32)
    assert resolved.palette.max_colors == 8
    assert resolved.background.mode == "transparent"
    assert resolved.source_of("logical_resolution") is SpecSource.EXPLICIT_PROMPT
    assert resolved.source_of("palette") is SpecSource.EXPLICIT_PROMPT


def test_transparent_background_is_not_read_as_a_scenery_request(container: AppContainer):
    """A armadilha da palavra "background".

    Em "transparent background" ela é uma restrição de fundo; em "forest
    background" ela nomeia o tipo do asset. Extrair a restrição **antes** de
    classificar é o que separa os dois casos — e sem isso toda árvore com
    fundo transparente viraria cenário.
    """
    transparente = _resolve(container, "tree, transparent background")

    assert transparente.asset.type is AssetType.PROP
    assert _resolve(container, "forest background").asset.type is AssetType.BACKGROUND


def test_the_full_precedence_order(container: AppContainer):
    """As seis camadas do §9 empilhadas no mesmo pedido.

    Profile diz 64, a interface diz 48, a frase diz 32 e a mão diz 24. O
    resultado é 24, e cada degrau abaixo dele foi de fato oferecido — é o
    teste que quebra se alguém inverter duas linhas de ``SPEC_PRECEDENCE``.
    """
    base = _resolve(container, "knight")
    assert base.logical_resolution.size == (64, 64)  # profile

    interface = _resolve(
        container,
        "knight",
        output=AssetOutputOverrides(logical_width=48, logical_height=48),
    )
    assert interface.logical_resolution.size == (48, 48)

    frase = _resolve(
        container,
        "knight 32x32",
        output=AssetOutputOverrides(logical_width=48, logical_height=48),
    )
    assert frase.logical_resolution.size == (32, 32)

    mao = _resolve(
        container,
        "knight 32x32",
        output=AssetOutputOverrides(logical_width=48, logical_height=48),
        spec_overrides=SpecOverrides(logical_width=24, logical_height=24),
    )
    assert mao.logical_resolution.size == (24, 24)
    assert mao.source_of("logical_resolution") is SpecSource.MANUAL_OVERRIDE


# ---------------------------------------------------------------------------
# §30 — nunca corrigir em silêncio
# ---------------------------------------------------------------------------
def test_an_unsupported_resolution_is_refused_not_rounded(container: AppContainer):
    """Plano T→J §30: fora do suportado vira erro, nunca 64×64 calado."""
    with pytest.raises(InvalidGenerationRequest) as excinfo:
        _resolve(container, "knight 4x4")

    assert "4×4" in str(excinfo.value)


def test_logical_resolution_is_refused_in_studio_mode(container: AppContainer):
    """Aceitar e ignorar é a mesma doença: o número precisa ter efeito.

    Arte 2D convencional não tem grid lógico. Guardar 32×32 em um pedido
    Studio produziria um spec que ninguém honra — exatamente o sintoma que
    este plano existe para eliminar.
    """
    request = AssetGenerationRequest(
        project_id="project_spec",
        profile="studio_character",
        prompt="cartoon knight",
        spec_overrides=SpecOverrides(logical_width=32, logical_height=32),
    )
    with pytest.raises(InvalidGenerationRequest) as excinfo:
        container.service.resolve_spec(request)

    assert "Pixel Art" in str(excinfo.value)


def test_a_lone_dimension_is_refused(container: AppContainer):
    """Metade de uma resolução não é uma resolução."""
    with pytest.raises(InvalidGenerationRequest):
        _resolve(container, "knight", spec_overrides=SpecOverrides(logical_width=32))


# ---------------------------------------------------------------------------
# §34 — identidade do spec
# ---------------------------------------------------------------------------
def test_the_spec_hash_follows_the_content(container: AppContainer):
    """Mesma configuração, mesmo hash; qualquer valor diferente, outro hash."""
    a = _resolve(container, "knight")
    b = _resolve(container, "knight")
    c = _resolve(
        container,
        "knight",
        spec_overrides=SpecOverrides(logical_width=32, logical_height=32),
    )

    assert a.spec_hash == b.spec_hash
    assert a.spec_id == b.spec_id
    assert a.spec_hash != c.spec_hash


def test_the_spec_is_immutable(container: AppContainer):
    """Plano T→J §15: depois de resolvido, 32 não vira 64 nem por engano."""
    resolved = _resolve(container, "knight")

    with pytest.raises(ValidationError):
        resolved.asset.type = AssetType.PROP  # type: ignore[misc]


# ---------------------------------------------------------------------------
# §42 e §43 — o caminho inteiro, até o arquivo e até o selo
# ---------------------------------------------------------------------------
def test_the_requested_resolution_reaches_the_png(container: AppContainer):
    """O teste que detecta exatamente o problema observado (plano T→J §42).

    Pedido de 32×32 com o profile de 64×64. O que se mede é o arquivo, não o
    relatório: ``logical.png`` precisa ter 32×32 pixels de verdade.
    """
    job = _completed_job(
        container,
        _request(
            container,
            "knight",
            output=AssetOutputOverrides(variations=1),
            spec_overrides=SpecOverrides(logical_width=32, logical_height=32),
        ),
    )

    variant = job.asset.variants[0]
    assert (variant.logical_width, variant.logical_height) == (32, 32)

    async def read(uri: str) -> bytes:
        return await container.storage.backend.get(
            container.storage.backend.key_from_uri(uri)
        )

    imagem = Image.open(io.BytesIO(run(read(variant.uri))))
    assert imagem.size == (32, 32)


def test_the_pixel_exact_seal_is_measured_against_the_request(container: AppContainer):
    """Plano T→J §43 e §44: o selo vale contra o pedido, não contra o profile.

    Aqui está a diferença entre um selo e um enfeite. Antes, o validador
    recebia o contrato do profile: um asset de 64×64 passava em PX-DIM-001
    mesmo quando 32×32 tinha sido pedido, e o "PIXEL EXACT ✓" aparecia sobre
    o arquivo errado.
    """
    job = _completed_job(
        container,
        _request(
            container,
            "knight",
            output=AssetOutputOverrides(variations=1),
            spec_overrides=SpecOverrides(
                logical_width=32, logical_height=32, palette_max_colors=8
            ),
        ),
    )

    variant = job.asset.variants[0]
    assert variant.pixel_exact is True
    assert variant.metadata["hard_checks"]["PX-DIM-001"] == "pass"
    assert variant.metadata["logical_size"] == [32, 32]
    assert variant.color_count is not None and variant.color_count <= 8


def test_the_job_carries_the_spec_that_generated_it(container: AppContainer):
    """Plano T→J §33 e §35: o que a tela mostrou é o que o job executou."""
    request = _request(
        container,
        "tree",
        output=AssetOutputOverrides(variations=1),
        spec_overrides=SpecOverrides(logical_width=32, logical_height=32),
    )
    esperado = container.service.resolve_spec(request)
    job = _completed_job(container, request)

    assert job.resolved_spec is not None
    assert job.resolved_spec.spec_hash == esperado.spec_hash
    assert job.asset.metadata["spec_id"] == esperado.spec_id

    # E o contrato fica gravado ao lado do asset, para quem for depurar depois.
    variant = job.asset.variants[0]
    uri = variant.artifacts["resolved_spec.json"]

    async def read(alvo: str) -> bytes:
        return await container.storage.backend.get(
            container.storage.backend.key_from_uri(alvo)
        )

    documento = json.loads(run(read(uri)))
    assert documento["spec_hash"] == esperado.spec_hash
    assert documento["asset"]["type"] == "prop"
    assert documento["raw_prompt"] == "tree"
