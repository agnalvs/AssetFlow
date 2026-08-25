"""O Pixel Optimizer obrigatório (plano Optimizer §57 a §69).

O plano fecha uma bifurcação: o AssetFlow não pergunta mais "modelo ou
agente?". Existe um caminho, e o agente virou o estágio que corrige o que o
motor produziu::

    Motor -> PixelPostProcessor -> Validação V1 -> Optimizer -> Validação V2
                                                                  -> Aceitação

O que este arquivo protege, e por quê:

* **o estágio é obrigatório** — não há campo no pedido para desligá-lo, e não
  há motor que escape dele. Se um dia houvesse, voltaríamos a ter dois
  caminhos com nomes diferentes;
* **o Optimizer não é um motor** — ele não está no registry, não tem manifesto
  e não aparece em lista nenhuma da interface (§76). Foi exatamente isso que
  deu errado antes: o agente entrou no seletor de motores e a tela passou a
  oferecer, lado a lado, coisas que não são comparáveis;
* **corrigir não pode estragar** — a otimização que baixa a nota é descartada
  (§20), e as invariantes do Pixel Exact (resolução, paleta, alpha) sobrevivem
  a ela (§63 a §66);
* **preservar é uma decisão registrada** — um pixel isolado pode ser um olho, e
  o §17 manda preservá-lo *com o motivo escrito*, não em silêncio.
"""

from __future__ import annotations

from PIL import Image

from assetflow.bootstrap import AppContainer
from assetflow.generation.schemas import AssetGenerationRequest
from assetflow.pixel import PixelAssetProcessor, PixelValidator
from assetflow.pixel.contracts.output_spec import PixelOutputSpec
from assetflow.pixel.optimizer import (
    MAX_ITERATIONS,
    AssetFlowPixelOptimizer,
    OptimizationStatus,
    PaletteGuard,
    PaletteViolation,
    PixelCanvas,
    PixelReviewer,
    PixelToolExecutor,
    RepairAction,
    RepairPlanner,
    ReviewLoop,
)
from tests.conftest import run

OUTLINE = (20, 20, 20, 255)
BODY = (200, 60, 60, 255)


def _spec(size: int = 32, colors: int = 8, **overrides) -> PixelOutputSpec:
    return PixelOutputSpec(
        logical_size={"width": size, "height": size},
        palette={"mode": "max_colors", "max_colors": colors},
        **overrides,
    )


def _sprite(size: int = 32) -> Image.Image:
    """Um sprite legível: corpo sólido, contorno escuro, margem transparente."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = image.load()
    inner = range(size // 4, size - size // 4)
    for y in inner:
        for x in inner:
            pixels[x, y] = BODY
    borda = range(size // 4 - 1, size - size // 4 + 1)
    for y in borda:
        for x in borda:
            if x in (borda.start, borda.stop - 1) or y in (borda.start, borda.stop - 1):
                pixels[x, y] = OUTLINE
    return image


def _optimize(image: Image.Image, spec: PixelOutputSpec):
    validator = PixelValidator()
    before = validator.validate(image, spec)
    optimizer = AssetFlowPixelOptimizer()
    return optimizer.optimize(
        image, spec, before, revalidate=lambda img: validator.validate(img, spec)
    )


# ---------------------------------------------------------------------------
# O estágio é obrigatório (§33, §34, §46, §62)
# ---------------------------------------------------------------------------
def test_the_request_has_no_way_to_turn_optimization_off():
    """§33 e §34: a otimização não é opção de quem pede.

    O teste é sobre a **ausência** de um campo, e é por isso que ele existe:
    um campo aceito e ignorado seria pior que nenhum — a interface passaria a
    oferecer um controle sem efeito, e ninguém descobriria.
    """
    campos = set(AssetGenerationRequest.model_fields)

    assert "optimize" not in campos
    assert "pixel_pipeline" not in campos
    # E os campos da bifurcação antiga também sumiram (§31 e §52).
    assert "generation_strategy" not in campos
    assert "pixel_agent" not in campos


def test_the_spec_always_carries_the_forced_pipeline(container: AppContainer):
    """§32: o contrato do job registra o pipeline, e ele vem imposto.

    O pedido não fala de otimização — e mesmo assim o spec diz que ela vai
    acontecer. É o que permite, meses depois, saber por qual pipeline um asset
    antigo passou.
    """
    spec = container.service.resolve_spec(
        AssetGenerationRequest(
            project_id="p", profile="pixel_character_64", prompt="uma árvore"
        )
    )

    assert spec.pixel_pipeline.optimize is True
    assert spec.pixel_pipeline.forced is True
    assert spec.pixel_pipeline.max_iterations == MAX_ITERATIONS
    assert spec.pixel_pipeline.optimizer_id == "assetflow_pixel_optimizer"


def test_every_engine_goes_through_the_same_downstream_pipeline(
    container: AppContainer,
):
    """§57: trocar o motor não muda o que vem depois dele.

    Este é o teste que impede a bifurcação de voltar por outra porta. Se um
    motor pudesse pular o Optimizer, existiriam de novo dois caminhos — só que
    desta vez sem nome, escondidos atrás da escolha de motor.
    """
    engines = [record.id for record in container.registry.list() if record.enabled]
    assert engines, "a suíte precisa de ao menos um motor habilitado"

    for engine_id in engines:
        request = AssetGenerationRequest(
            project_id="p",
            profile="pixel_character_64",
            prompt="uma árvore",
            engine={"mode": "manual", "engine_id": engine_id, "allow_fallback": False},
        )
        job = run(container.service.submit(request))
        run(container.worker.run_once())
        job = run(container.jobs.get(job.id))

        assert job.status.value == "completed", job.error
        metrics = job.asset.variants[0].metadata.get("pixel_metrics") or {}
        assert metrics.get("optimizer_status"), (
            f"o motor '{engine_id}' produziu um asset sem laudo de otimização"
        )
        assert metrics.get("optimizer_version")


# ---------------------------------------------------------------------------
# O Optimizer não é um motor (§58, §76, §79)
# ---------------------------------------------------------------------------
def test_the_optimizer_is_not_an_engine(container: AppContainer):
    """§79: ele corrige a imagem gerada; não gera imagem.

    Estar no registry o tornaria escolhível — e escolher entre "FLUX" e "o
    corretor de pixels" é a pergunta sem sentido que o plano veio desfazer.
    """
    ids = set(container.registry.ids())

    assert "assetflow_pixel_optimizer" not in ids
    assert not any("optimizer" in engine_id for engine_id in ids)
    # E ele existe, montado ao lado do kernel — não dentro dele.
    assert container.optimizer.enabled


def test_the_optimizer_never_shows_up_in_the_engine_catalog(container: AppContainer):
    """§76: a interface desenha o seletor a partir deste catálogo."""
    entries = run(container.service.engine_catalog(include_hidden=True))
    nomes = {entry.engine_id for entry in entries}

    assert "assetflow_pixel_optimizer" not in nomes
    assert not any("optimizer" in nome for nome in nomes)


# ---------------------------------------------------------------------------
# Preservar é uma decisão, não um esquecimento (§17)
# ---------------------------------------------------------------------------
def test_a_lone_pixel_of_a_used_colour_is_preserved_with_a_reason():
    """§17: um pixel isolado pode ser um olho.

    A distinção é a **cor**. Ninguém desenha um detalhe com uma cor que não
    usa em nenhum outro lugar; um resíduo de quantização, sim.
    """
    spec = _spec()
    image = _sprite()
    pixels = image.load()
    # Os dois estão **isolados** — sem vizinho opaco —, e é essa a única
    # coisa que têm em comum. O que os separa é a cor.
    pixels[2, 29] = OUTLINE            # o "olho": cor que o contorno usa muito
    pixels[2, 2] = (11, 200, 33, 255)  # ruído: cor única no sprite inteiro

    outcome = _optimize(image, spec)

    assert outcome.image.getpixel((2, 29)) == OUTLINE, "o olho foi apagado"
    assert outcome.image.getpixel((2, 2))[3] == 0, "o ruído sobreviveu"

    recusas = [
        reason
        for plan in outcome.report.plans
        for kind, reason in plan.declined
        if kind == "orphan_pixel"
    ]
    assert recusas, "preservar um pixel precisa ficar registrado, não implícito"
    assert any("(2, 29)" in reason for reason in recusas)


def test_the_planner_refuses_to_draw_an_outline_that_does_not_exist():
    """§79: o Optimizer remenda contorno; não cria contorno.

    Um sprite sem linha escura em volta tem *toda* a fronteira exposta.
    Pintá-la com a cor da própria borda não criaria um contorno — engordaria o
    sprite em um anel, e mais um a cada volta do laço.
    """
    spec = _spec()
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(8, 24):
        for x in range(8, 24):
            pixels[x, y] = BODY  # bloco liso: nenhum contorno

    canvas = PixelCanvas.from_image(image)
    validator = PixelValidator()
    review = PixelReviewer().review(canvas, spec, validator.validate(image, spec))
    plan = RepairPlanner().plan(review, canvas, spec)

    assert not any(
        action.tool == "repair_outline" for action in plan.actions
    ), "o Optimizer tentou desenhar um contorno que o motor não fez"


# ---------------------------------------------------------------------------
# A paleta manda (§16, §67)
# ---------------------------------------------------------------------------
def test_a_locked_palette_rejects_a_colour_from_outside():
    """§67: em paleta travada, a cor de fora é recusada — não aproximada.

    Aproximar seria o Optimizer decidindo por conta própria qual cor do
    projeto o artista quis. A recusa fica no log, e o reparo simplesmente não
    acontece.
    """
    guard = PaletteGuard(("#141414", "#c83c3c"), locked=True)
    executor = PixelToolExecutor(palette=guard)
    canvas = PixelCanvas(8, 8)

    record = executor.execute(
        canvas,
        RepairAction(tool="set_pixel", params={"x": 1, "y": 1, "color": "#00ff00"}),
    )

    assert record.pixels_changed == 0
    assert record.error and "paleta travada" in record.error
    assert canvas.get(1, 1)[3] == 0, "a cor proibida chegou ao canvas"

    # A cor do projeto passa normalmente.
    assert executor.execute(
        canvas,
        RepairAction(tool="set_pixel", params={"x": 1, "y": 1, "color": "#c83c3c"}),
    ).pixels_changed == 1


def test_a_full_colour_budget_resolves_to_the_nearest_colour_in_use():
    """§16: com orçamento cheio, a pincelada acontece em um tom vizinho.

    Aqui aproximar é o certo, e a diferença para o caso travado é o que está em
    jogo: lá, a lista é o contrato do projeto; aqui, o que importa é o número.
    Recusar deixaria um buraco no sprite para respeitar uma contagem.
    """
    guard = PaletteGuard(("#101010", "#f0f0f0"), max_colors=2)

    assert guard.resolve("#121212") == (16, 16, 16, 255)
    assert guard.is_full


def test_the_palette_guard_is_built_per_asset():
    """As cores de um sprite não podem vazar para o orçamento do seguinte.

    Uma guarda compartilhada no construtor do laço faria o segundo asset
    começar com a paleta do primeiro já gasta — e o efeito só apareceria em
    produção, no segundo job.
    """
    loop = ReviewLoop()
    spec = _spec(colors=4)
    validator = PixelValidator()

    primeiro = _sprite()
    canvas = PixelCanvas.from_image(primeiro)
    loop.run(canvas, spec, validator.validate(primeiro, spec))

    segundo = PixelCanvas(8, 8)
    segundo.set(0, 0, (5, 5, 5, 255))
    from assetflow.pixel.optimizer.loop import guard_for

    assert guard_for(spec, segundo).colors == ((5, 5, 5, 255),)


# ---------------------------------------------------------------------------
# Otimizar não pode piorar (§20)
# ---------------------------------------------------------------------------
def test_an_optimization_that_lowers_the_score_is_thrown_away():
    """§20: um corretor que às vezes estraga é pior que nenhum corretor.

    O planejador é substituído por um que pinta lixo de propósito: o que se
    testa aqui é a **rede de segurança**, e ela precisa valer para qualquer
    plano, inclusive um que ninguém escreveria.
    """

    class VandalPlanner(RepairPlanner):
        def plan(self, review, canvas, spec):
            from assetflow.pixel.optimizer.contracts import RepairPlan

            plano = RepairPlan()
            for x in range(0, canvas.width, 3):
                plano.add(
                    RepairAction(
                        tool="set_pixel",
                        params={"x": x, "y": x % canvas.height, "color": "#ff00ff"},
                        reason="ruído de propósito",
                    )
                )
            return plano

    spec = _spec()
    image = _sprite()
    pixels = image.load()
    pixels[2, 2] = (11, 200, 33, 255)  # dá ao revisor algo a encontrar

    validator = PixelValidator()
    before = validator.validate(image, spec)
    optimizer = AssetFlowPixelOptimizer(loop=ReviewLoop(planner=VandalPlanner()))
    outcome = optimizer.optimize(
        image, spec, before, revalidate=lambda img: validator.validate(img, spec)
    )

    assert outcome.reverted is True
    assert outcome.image is image, "a imagem estragada foi entregue"
    assert outcome.report.score_after is not None
    assert outcome.report.score_after < outcome.report.score_before


# ---------------------------------------------------------------------------
# As invariantes do Pixel Exact sobrevivem (§63 a §66)
# ---------------------------------------------------------------------------
def test_the_optimizer_preserves_resolution_alpha_and_palette():
    """§63 a §66: o Optimizer corrige dentro do contrato, nunca contra ele."""
    spec = _spec(size=32, colors=8)
    image = _sprite()
    pixels = image.load()
    for x, y in ((2, 2), (29, 4), (3, 28)):
        pixels[x, y] = (x * 7 % 256, y * 11 % 256, 90, 255)

    outcome = _optimize(image, spec)
    resultado = outcome.image

    assert resultado.size == (32, 32)
    assert resultado.mode == "RGBA"
    valores = {pixel[3] for pixel in resultado.getdata()}
    assert valores <= {0, 255}, f"alpha deixou de ser binário: {sorted(valores)}"
    cores = {pixel[:3] for pixel in resultado.getdata() if pixel[3] > 0}
    assert len(cores) <= 8


# ---------------------------------------------------------------------------
# O laço termina (§19) e o relatório é sempre escrito (§46, §48)
# ---------------------------------------------------------------------------
def test_the_review_loop_never_runs_past_its_ceiling():
    """§19: três voltas é teto, não meta.

    Um planejador que sempre encontra o que fazer é o pior caso — e é
    exatamente ele que o teto existe para conter.
    """

    class NeverSatisfied(RepairPlanner):
        def plan(self, review, canvas, spec):
            from assetflow.pixel.optimizer.contracts import RepairPlan

            plano = RepairPlan()
            plano.add(
                RepairAction(
                    tool="set_pixel",
                    params={"x": 0, "y": len(review.issues) % canvas.height, "color": OUTLINE},
                    reason="sempre há o que fazer",
                )
            )
            return plano

    spec = _spec()
    image = _sprite()
    image.load()[2, 2] = (11, 200, 33, 255)
    canvas = PixelCanvas.from_image(image)

    loop = ReviewLoop(planner=NeverSatisfied())
    report = loop.run(canvas, spec, PixelValidator().validate(image, spec))

    assert report.iterations <= MAX_ITERATIONS
    assert len(report.reviews) <= MAX_ITERATIONS


def test_skipped_does_not_mean_the_stage_was_skipped():
    """§46: `skipped` é uma decisão do Optimizer, não a ausência dele.

    A confusão é fácil e cara: se `skipped` fosse lido como "não rodou",
    voltaríamos a ter uma otimização opcional — só que sem ninguém ter
    decidido isso.
    """
    spec = _spec()
    outcome = _optimize(_sprite(), spec)

    assert outcome.report.status in tuple(OptimizationStatus)
    assert outcome.report.reviews, "o Optimizer rodou sem revisar nada"
    assert outcome.report.score_before is not None
    assert outcome.report.score_after is not None
    documento = outcome.report.document()
    assert documento["status"] and documento["reviewer"] == "heuristic"


def test_a_disabled_optimizer_says_so_instead_of_disappearing():
    """§46: desligar é uma decisão de instalação — e fica registrada.

    Sem o status `disabled`, um servidor com a otimização desligada produziria
    relatórios indistinguíveis dos de um servidor que otimizou e não achou
    nada. São coisas muito diferentes.
    """
    spec = _spec()
    image = _sprite()
    validator = PixelValidator()

    outcome = AssetFlowPixelOptimizer(enabled=False).optimize(
        image, spec, validator.validate(image, spec)
    )

    assert outcome.report.status is OptimizationStatus.DISABLED
    assert outcome.image is image
    assert outcome.report.pixels_changed == 0


# ---------------------------------------------------------------------------
# Os artefatos do §47
# ---------------------------------------------------------------------------
def test_a_corrected_asset_keeps_the_before_and_after_on_disk():
    """§47: um asset corrigido precisa poder ser auditado.

    Sem `postprocessed.png` e `initial_validation.json`, a pergunta "a
    otimização ajudou?" só teria a resposta que o próprio Optimizer deu — e
    conferi-la exigiria reprocessar o job.
    """
    spec = _spec()
    image = _sprite()
    pixels = image.load()
    for x, y in ((2, 2), (29, 4), (3, 28)):
        pixels[x, y] = (x * 7 % 256, y * 11 % 256, 90, 255)

    outcome = PixelAssetProcessor().run(image, spec)

    assert outcome.optimization is not None
    assert outcome.optimization.report.pixels_changed > 0, (
        "o caso de teste deixou de exercitar uma correção real"
    )
    assert "postprocessed.png" in outcome.artifacts
    assert "initial_validation.json" in outcome.artifacts
    assert "optimizer.json" in outcome.artifacts
    assert "optimizer_actions.json" in outcome.artifacts
    # A validação final é a que a aceitação usou — e é `validation.json`.
    assert outcome.validation is not outcome.initial_validation


def test_an_untouched_asset_does_not_duplicate_its_own_files():
    """O outro lado do §47: sem correção, não há "antes" a guardar.

    Gravar `postprocessed.png` idêntico a `logical.png` em todo asset encheria
    o storage de cópia e faria parecer que houve correção onde não houve.
    """
    outcome = PixelAssetProcessor().run(_sprite(), _spec())

    assert outcome.optimization is not None
    assert outcome.optimization.report.pixels_changed == 0
    assert "postprocessed.png" not in outcome.artifacts
    assert "initial_validation.json" not in outcome.artifacts
    # O laudo, esse existe sempre: o estágio rodou (§46).
    assert "optimizer.json" in outcome.artifacts


# ---------------------------------------------------------------------------
# As ferramentas (§15, §40)
# ---------------------------------------------------------------------------
def test_a_fractional_coordinate_is_refused_not_truncated():
    """§15: meio pixel não existe na grade.

    Truncar em silêncio esconderia um erro de planejamento até ele aparecer na
    imagem — quando já não há como saber qual ação o causou.
    """
    executor = PixelToolExecutor()
    canvas = PixelCanvas(8, 8)

    record = executor.execute(
        canvas,
        RepairAction(tool="set_pixel", params={"x": 1.5, "y": 2, "color": "#ffffff"}),
    )

    assert record.pixels_changed == 0
    assert record.error and "fracion" in record.error
    # `13.0` é um inteiro escrito como float — e isso o JSON produz o tempo todo.
    assert executor.execute(
        canvas,
        RepairAction(tool="set_pixel", params={"x": 1.0, "y": 2, "color": "#ffffff"}),
    ).pixels_changed == 1


def test_an_unknown_tool_costs_one_repair_not_the_whole_asset():
    """Um plano torto produz um reparo a menos e um log que aponta o problema."""
    executor = PixelToolExecutor()
    canvas = PixelCanvas(8, 8)

    record = executor.execute(canvas, RepairAction(tool="draw_dragon", params={}))

    assert record.pixels_changed == 0
    assert record.error and "desconhecida" in record.error


def test_the_shipped_tools_are_the_ones_the_plan_asks_for():
    """§40: o conjunto inicial, e nada além dele.

    Uma ferramenta sem problema medido correspondente é uma ferramenta que
    ninguém saberia quando usar — e o vocabulário aqui é de **reparo**, não de
    desenho: não há `draw_circle` nem `draw_triangle`.
    """
    nomes = set(PixelToolExecutor().tool_names)

    assert nomes == {
        "set_pixel",
        "erase_pixel",
        "draw_pixels",
        "replace_color",
        "inspect_canvas",
        "inspect_region",
        "repair_outline",
        "connect_cluster",
    }


def test_erasing_does_not_spend_a_palette_slot():
    """Apagar não é usar uma cor.

    Se o alpha 0 gastasse uma entrada do orçamento, a borracha competiria com
    o desenho pelas cores disponíveis — e um sprite de 8 cores passaria a ter
    7 utilizáveis.
    """
    guard = PaletteGuard(("#101010",), max_colors=1)

    assert guard.resolve((0, 0, 0, 0)) == (0, 0, 0, 0)
    assert guard.colors == ((16, 16, 16, 255),)
    try:
        PaletteGuard(("#101010",), locked=True).resolve((0, 0, 0, 0))
    except PaletteViolation:  # pragma: no cover - o que este teste proíbe
        raise AssertionError("apagar foi tratado como cor proibida")
