"""O módulo Pixel não muda quando o motor muda (plano Pixel §92 e §105).

O plano Pixel §105 é a regra de ouro deste arquivo: ``assetflow/pixel/``
recebe ``(imagem, PixelOutputSpec)`` e não faz ideia de quem produziu a
imagem. Ele não conhece SDXL, ``engine_id``, checkpoint, job, projeto nem
storage. É por isso que o Pixel Exact pertence à estante do AssetFlow e não a
uma gaveta.

A regra é verificada de duas direções, porque uma sozinha não basta:

``de fora para dentro (§92)``
    O mesmo pedido é gerado por duas gavetas independentes. O asset entregue
    precisa cumprir o mesmo contrato técnico nos dois caminhos, e os
    relatórios precisam citar as **mesmas versões** de processador e
    validador — se o veredito dependesse do motor, dois benchmarks feitos com
    gavetas diferentes não seriam comparáveis (plano Pixel §76).

``de dentro para fora (§105)``
    Um teste de AST prova que nenhum arquivo do pacote consegue conhecer um
    motor: a dependência simplesmente não existe no código-fonte. É o mesmo
    padrão de ``tests/test_architecture_boundaries.py``, aplicado às
    fronteiras específicas do módulo Pixel.

As duas gavetas usadas são mocks de CPU (plano §69): a suíte roda sem GPU e
sem rede.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest
from PIL import Image

from assetflow.bootstrap import AppContainer
from assetflow.generation.schemas import JobStatus
from tests.conftest import BACKEND_ROOT, process_next_job, run

#: Gaveta padrão da suíte para ``text_to_image.pixel``.
ENGINE_A = "mock-image-v1"
#: Segunda gaveta, implementação totalmente independente da primeira. Ela vem
#: desligada em ``engines.yaml`` e é ligada em runtime — a troca de motor é
#: mudança de **estado de configuração**, nunca de código (plano §67).
ENGINE_B = "mock-pixel-alt-v1"

PIXEL_ROOT = BACKEND_ROOT / "assetflow" / "pixel"


def _generate(container: AppContainer, make_request):
    """Roda um pedido de Pixel Art inteiro e devolve o job concluído."""

    async def scenario():
        job = await container.service.submit(make_request(output={"variations": 1}))
        assert await process_next_job(container)
        return await container.service.get_job(job.id)

    job = run(scenario())
    assert job.status is JobStatus.COMPLETED, job.error
    return job


def _read_image(container: AppContainer, uri: str) -> Image.Image:
    async def read() -> bytes:
        return await container.storage.read(uri)

    return Image.open(io.BytesIO(run(read()))).convert("RGBA")


# ---------------------------------------------------------------------------
# (1) De fora para dentro: trocar a gaveta não muda o contrato do asset
# ---------------------------------------------------------------------------
def test_both_engines_produce_the_same_pixel_contract(
    container: AppContainer, make_request
):
    """Plano Pixel §92: duas gavetas, o mesmo contrato Pixel Exact.

    O que este teste fixa não é "as duas imagens são iguais" — elas não são,
    e não deveriam ser: são motores diferentes. É que as **exigências
    técnicas** do arquivo entregue não dependem de quem desenhou: 64×64
    reais, orçamento de paleta do profile, alpha sem meio-termo e o selo
    ``pixel_exact``.

    Se um dia o pós-processamento passasse a se comportar de um jeito para uma
    gaveta e de outro para a outra — por um caminho especial, um
    ``if engine_id == ...``, um formato de saída assumido —, é aqui que isso
    apareceria.
    """
    container.registry.enable(ENGINE_A)
    container.registry.disable(ENGINE_B)
    job_a = _generate(container, make_request)
    assert job_a.engine.id == ENGINE_A

    # Único ato entre as duas gerações: ligar a outra gaveta.
    container.registry.enable(ENGINE_B)
    job_b = _generate(container, make_request)
    assert job_b.engine.id == ENGINE_B, (
        "a segunda gaveta precisa vencer o roteamento, senão o teste compara "
        "o mesmo motor com ele mesmo"
    )

    profile = container.pixel_profiles.get("pixel_character_64_strict")

    for job in (job_a, job_b):
        variant = job.asset.variants[0]
        assert (variant.width, variant.height) == profile.target_size == (64, 64)
        assert (variant.logical_width, variant.logical_height) == (64, 64)
        assert variant.color_count is not None
        assert variant.color_count <= profile.max_colors
        assert variant.pixel_exact is True, variant.validation.issues

        image = _read_image(container, variant.uri)
        assert image.size == (64, 64)
        alpha = {
            value
            for value, count in enumerate(image.getchannel("A").histogram())
            if count
        }
        assert alpha <= {0, 255}, f"{job.engine.id} deixou alpha parcial no asset"

    # As gavetas são de fato distintas — sem isto o teste passaria mesmo se a
    # troca não tivesse surtido efeito nenhum.
    assert job_a.engine.model_id != job_b.engine.model_id
    assert _read_image(container, job_a.asset.variants[0].uri).tobytes() != _read_image(
        container, job_b.asset.variants[0].uri
    ).tobytes()


def test_pixel_reports_cite_the_same_module_versions(
    container: AppContainer, make_request
):
    """Plano Pixel §76 e §92: o veredito é do módulo, não do motor.

    As versões de processador e validador — e o profile Pixel aplicado, e a
    lista de estágios executados — precisam ser idênticas nos dois caminhos.
    É a condição para o benchmark do §76 significar alguma coisa: comparar a
    qualidade de duas gavetas só faz sentido se a régua for a mesma.
    """
    container.registry.enable(ENGINE_A)
    container.registry.disable(ENGINE_B)
    metadata_a = _generate(container, make_request).asset.variants[0].metadata

    container.registry.enable(ENGINE_B)
    metadata_b = _generate(container, make_request).asset.variants[0].metadata

    metrics_a = metadata_a["pixel_metrics"]
    metrics_b = metadata_b["pixel_metrics"]

    for field in (
        "pixel_pipeline_version",
        "postprocessor_version",
        "validator_version",
        "profile_version",
    ):
        assert metrics_a[field] == metrics_b[field], (
            f"'{field}' mudou ao trocar de gaveta: o módulo Pixel estaria "
            "reagindo ao motor"
        )

    assert metadata_a["pixel_spec_id"] == metadata_b["pixel_spec_id"]
    assert metadata_a["pixel_steps"] == metadata_b["pixel_steps"]
    # Mesma lista de requisitos exigida, com o mesmo resultado por código: um
    # check que se pula para uma gaveta e roda para a outra seria um veredito
    # com régua variável.
    assert metadata_a["hard_checks"] == metadata_b["hard_checks"]


# ---------------------------------------------------------------------------
# (2) De dentro para fora: a dependência não existe no código-fonte
# ---------------------------------------------------------------------------
def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _imports(path: Path) -> list[tuple[str, int]]:
    """Módulos importados por um arquivo (absolutos), com a linha."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            found.append((node.module, node.lineno))
    return found


def _relative_roots(path: Path) -> list[tuple[str, int]]:
    """Primeiro segmento de cada import relativo, com a linha.

    Um import relativo não diz para onde sobe só pelo texto: ``from ...jobs``
    e ``from ..jobs`` escrevem o mesmo segmento. Para a proibição deste
    módulo isso basta — nenhum pacote **dentro** de ``assetflow/pixel/`` se
    chama ``jobs``, ``api``, ``storage`` ou ``engines``, então qualquer
    ocorrência do segmento é necessariamente uma camada de fora.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level and node.module:
            found.append((node.module.split(".")[0], node.lineno))
    return found


PIXEL_FILES = _python_files(PIXEL_ROOT)

#: O que ``assetflow/pixel/`` não pode alcançar (plano Pixel §5, §68 e §105).
#:
#: ``engines``  o módulo não pode conhecer motor nenhum, nem a estante deles;
#: ``jobs``/``api``/``storage``/``bootstrap`` são camadas de cima: o Pixel
#: Exact precisa continuar utilizável por um script de benchmark ou por um
#: editor futuro, sem arrastar fila, HTTP e disco junto.
FORBIDDEN_PACKAGES = ("engines", "jobs", "api", "storage", "bootstrap")

#: Os mesmos alvos escritos como módulo absoluto. ``engines`` mora dentro de
#: ``generation``, então o caminho completo entra à parte.
FORBIDDEN_MODULES = (
    *(f"assetflow.{package}" for package in FORBIDDEN_PACKAGES),
    "assetflow.generation.engines",
)

#: Prefixos para alcançar também os submódulos, sem que ``assetflow.api``
#: passe a casar com um futuro ``assetflow.apiario``.
FORBIDDEN_PREFIXES = tuple(f"{module}." for module in FORBIDDEN_MODULES)

#: Bibliotecas de IA. A lista é a mesma de ``test_architecture_boundaries.py``,
#: mas a fronteira aqui é outra: lá a regra permite o import **dentro** de uma
#: gaveta, e ``assetflow/pixel/`` nunca é uma gaveta.
AI_LIBRARIES = {
    "torch",
    "diffusers",
    "transformers",
    "accelerate",
    "safetensors",
    "comfy",
    "replicate",
    "openai",
    "anthropic",
    "onnxruntime",
    "tensorflow",
}


def test_there_are_pixel_files_to_inspect():
    """Sem este piso, apagar o pacote deixaria as regras abaixo verdes."""
    assert len(PIXEL_FILES) > 20


@pytest.mark.parametrize(
    "path", PIXEL_FILES, ids=lambda p: str(p.relative_to(PIXEL_ROOT))
)
def test_pixel_module_never_reaches_engine_job_api_or_storage(path: Path):
    """Plano Pixel §105: o módulo não conhece motor nem as camadas de cima."""
    absolute = [
        f"{path.name}:{line} importa '{module}'"
        for module, line in _imports(path)
        if module in FORBIDDEN_MODULES or module.startswith(FORBIDDEN_PREFIXES)
    ]
    relative = [
        f"{path.name}:{line} importa '.{root}'"
        for root, line in _relative_roots(path)
        if root in FORBIDDEN_PACKAGES
    ]
    assert not (absolute + relative), (
        "assetflow/pixel/ precisa continuar recebendo apenas (imagem, spec):\n"
        + "\n".join(absolute + relative)
    )


@pytest.mark.parametrize(
    "path", PIXEL_FILES, ids=lambda p: str(p.relative_to(PIXEL_ROOT))
)
def test_pixel_module_imports_no_ai_library(path: Path):
    """Plano Pixel §5: o Pixel Exact é álgebra sobre pixels, não IA.

    ``numpy`` e ``Pillow`` são permitidos e usados à vontade (plano Pixel
    §108) — o que não pode entrar é a biblioteca do gerador, porque seria a
    porta pela qual o módulo passaria a depender de como a imagem nasceu.
    """
    violations = [
        f"{path.name}:{line} importa '{module}'"
        for module, line in _imports(path)
        if module.split(".")[0] in AI_LIBRARIES
    ]
    assert not violations, "\n".join(violations)


def test_no_engine_vocabulary_leaks_into_the_pixel_contracts():
    """O contrato de entrada não tem onde guardar a identidade do motor.

    ``PixelOutputSpec`` é o **único** objeto que o módulo recebe além da
    imagem (plano Pixel §10). Enquanto ele não tiver um campo capaz de
    carregar motor, modelo ou checkpoint, nenhum estágio pode se especializar
    por gaveta nem que queira — a informação não chega até lá.

    A verificação é sobre os campos do contrato, não sobre o texto do arquivo:
    as docstrings citam SDXL e ``engine_id`` justamente ao explicar a
    proibição, e proibir a palavra proibiria também explicá-la.
    """
    from assetflow.pixel.contracts import PixelOutputSpec

    proibidos = {"engine", "engine_id", "model", "model_id", "checkpoint", "lora"}
    campos = set(PixelOutputSpec.model_fields)
    assert not (campos & proibidos), (
        f"o PixelOutputSpec ganhou um campo de motor: {sorted(campos & proibidos)}"
    )
