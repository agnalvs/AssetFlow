"""O revisor do Pixel Optimizer feito por modelo (plano Optimizer §42).

O que precisa estar certo aqui, e por quê:

* **o modelo descreve, nunca corrige.** O laudo dele passa pelo mesmo
  planejador determinístico, pela mesma guarda de paleta e pela mesma regra de
  que otimizar não pode piorar. O pior caso de uma alucinação é um reparo
  inútil no log — nunca um sprite destruído;
* **queda é rebaixamento, nunca falha.** Provedor fora do ar, JSON quebrado,
  resposta vazia: vale o laudo determinístico, e o job segue;
* **o laudo diz quem o escreveu.** Dois assets com diagnósticos diferentes
  precisam poder dizer se foram revisados pela mesma coisa.

Nenhum teste aqui toca a rede: o cliente é substituído por um dublê. O que se
está exercitando é a leitura do laudo e a fronteira, não o provedor.
"""

from __future__ import annotations

from PIL import Image

from assetflow.llm import LLMPixelReviewer
from assetflow.llm.chat import ChatError
from assetflow.pixel import PixelValidator
from assetflow.pixel.contracts.output_spec import PixelOutputSpec
from assetflow.pixel.optimizer import (
    AssetFlowPixelOptimizer,
    PixelCanvas,
    ReviewLoop,
)

OUTLINE = (20, 20, 20, 255)
BODY = (200, 60, 60, 255)


class FakeChat:
    """Um cliente que devolve o que o teste mandar — ou estoura."""

    def __init__(self, *replies: str, fail: str | None = None) -> None:
        self._replies = list(replies)
        self._fail = fail
        self.prompts: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        if self._fail:
            raise ChatError(self._fail)
        return self._replies.pop(0) if self._replies else "{}"

    def describe(self) -> str:  # pragma: no cover - só para log
        return "fake"


def _spec() -> PixelOutputSpec:
    return PixelOutputSpec(
        logical_size={"width": 16, "height": 16},
        palette={"mode": "max_colors", "max_colors": 8},
    )


def _sprite() -> Image.Image:
    image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(5, 11):
        for x in range(5, 11):
            pixels[x, y] = BODY
    for y in range(4, 12):
        for x in range(4, 12):
            if x in (4, 11) or y in (4, 11):
                pixels[x, y] = OUTLINE
    return image


def _review(reply: str | None = None, *, fail: str | None = None):
    spec = _spec()
    image = _sprite()
    canvas = PixelCanvas.from_image(image)
    validation = PixelValidator().validate(image, spec)
    chat = FakeChat(*( (reply,) if reply else () ), fail=fail)
    reviewer = LLMPixelReviewer(chat, max_attempts=1)
    return reviewer, chat, reviewer.review(canvas, spec, validation)


# ---------------------------------------------------------------------------
def test_the_model_can_name_a_problem_the_validator_cannot_measure():
    """O motivo de o revisor por LLM existir (§42).

    "A chaminé ficou solta do telhado" não é uma medida, e por isso o revisor
    determinístico nunca vai vê-la. Um tipo que o planejador não conhece
    **entra** no laudo mesmo assim: ele será declinado com motivo, e é essa
    recusa que revela o que falta implementar.
    """
    _reviewer, _chat, review = _review(
        '{"issues": [{"type": "detached_chimney", "severity": "high",'
        ' "region": "telhado", "pixels": [[6, 6]],'
        ' "detail": "a chaminé não encosta no telhado"}]}'
    )

    tipos = {issue.type for issue in review.issues}
    assert "detached_chimney" in tipos
    achado = review.of_type("detached_chimney")[0]
    assert achado.position == (6, 6)
    assert achado.severity.value == "high"
    assert not review.approved


def test_the_prompt_carries_the_sprite_as_a_map():
    """O modelo precisa ver a **forma**, não uma lista de coordenadas.

    Uma lista de cor por pixel em 64×64 teria milhares de linhas, e o que se
    está pedindo — "o que está estruturalmente errado neste desenho?" — é
    justamente o que se perde nessa forma.
    """
    _reviewer, chat, _review_result = _review('{"issues": []}')
    prompt = chat.prompts[0]

    assert "Mapa" in prompt
    assert "Grade: 16x16" in prompt
    assert "Ocupação:" in prompt
    # O mapa tem uma linha por linha da grade, e '.' onde é transparente.
    mapa = prompt.split("transparente):\n")[1].splitlines()
    assert len(mapa) == 16
    assert all(len(linha) == 16 for linha in mapa)
    assert mapa[0] == "." * 16


def test_a_provider_that_is_down_degrades_instead_of_failing():
    """Uma geração não morre porque um modelo de texto não respondeu."""
    reviewer, _chat, review = _review(fail="conexão recusada")

    assert reviewer.name == "heuristic", "o laudo precisa dizer quem o escreveu"
    # O determinístico continuou trabalhando: este sprite tem contorno e forma,
    # então o laudo é o dele — vazio ou não, mas existente.
    assert isinstance(review.issues, list)


def test_a_malformed_report_is_refused_not_guessed():
    """JSON quebrado vira rebaixamento, não um laudo inventado pela metade."""
    reviewer, _chat, _review_result = _review("desculpe, não consegui")

    assert reviewer.name == "heuristic"


def test_coordinates_outside_the_grid_are_dropped_not_the_whole_report():
    """Um modelo que erra uma posição entre vinte produziu dezenove úteis.

    Perder as dezenove por causa da vigésima seria o pior dos dois mundos. Um
    problema que fica **sem nenhuma** posição válida, esse é descartado: ele
    não teria como virar reparo.
    """
    _reviewer, _chat, review = _review(
        '{"issues": ['
        ' {"type": "orphan_pixel", "pixels": [[3, 3], [999, 999]], "detail": "a"},'
        ' {"type": "orphan_pixel", "pixels": [[500, 500]], "detail": "b"}'
        "]}"
    )

    achados = review.of_type("orphan_pixel")
    assert len(achados) == 1
    assert achados[0].pixels == ((3, 3),)


def test_the_model_does_not_repeat_what_the_validator_already_found():
    """Sem isto, o mesmo pixel viraria dois reparos — e o segundo, ruído no log."""
    spec = _spec()
    image = _sprite()
    image.load()[1, 1] = (7, 200, 30, 255)  # órfão que o determinístico acha
    canvas = PixelCanvas.from_image(image)
    validation = PixelValidator().validate(image, spec)

    reviewer = LLMPixelReviewer(
        FakeChat('{"issues": [{"type": "orphan_pixel", "pixels": [[1, 1]]}]}'),
        max_attempts=1,
    )
    review = reviewer.review(canvas, spec, validation)

    assert len([i for i in review.of_type("orphan_pixel") if i.position == (1, 1)]) == 1


def test_a_hallucinated_report_cannot_destroy_the_sprite():
    """A fronteira do §42, e a razão de o revisor só descrever.

    O modelo aqui aponta o corpo inteiro como problema. O planejador
    determinístico continua sendo quem decide — e ele não tem correção para um
    tipo que não conhece, nem apaga pixel de cor usada (§17).
    """
    spec = _spec()
    image = _sprite()
    antes = list(image.getdata())

    laudo = (
        '{"issues": [{"type": "everything_is_wrong", "severity": "high",'
        ' "pixels": [' + ", ".join(f"[{x}, {y}]" for y in range(5, 11) for x in range(5, 11))
        + '], "detail": "apague tudo"}]}'
    )
    optimizer = AssetFlowPixelOptimizer(
        loop=ReviewLoop(reviewer=LLMPixelReviewer(FakeChat(laudo, laudo, laudo), max_attempts=1))
    )
    validator = PixelValidator()
    outcome = optimizer.optimize(
        image,
        spec,
        validator.validate(image, spec),
        revalidate=lambda img: validator.validate(img, spec),
    )

    assert list(outcome.image.getdata()) == antes, "o laudo alucinado mexeu no sprite"
    recusas = [
        kind for plan in outcome.report.plans for kind, _reason in plan.declined
    ]
    assert "everything_is_wrong" in recusas


def test_the_reviewer_name_reaches_the_report():
    """`optimizer.json` precisa dizer quem revisou (§48)."""
    spec = _spec()
    image = _sprite()
    image.load()[1, 1] = (7, 200, 30, 255)
    validator = PixelValidator()

    optimizer = AssetFlowPixelOptimizer(
        loop=ReviewLoop(
            reviewer=LLMPixelReviewer(FakeChat('{"issues": []}'), max_attempts=1)
        )
    )
    outcome = optimizer.optimize(
        image,
        spec,
        validator.validate(image, spec),
        revalidate=lambda img: validator.validate(img, spec),
    )

    assert outcome.report.reviewer == "llm"
    assert outcome.report.document()["reviewer"] == "llm"
