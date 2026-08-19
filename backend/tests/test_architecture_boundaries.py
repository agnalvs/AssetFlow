"""Regras de ouro convertidas em teste (planos §18, §73 e §74).

Este arquivo é a defesa automatizada da arquitetura. Ele falha o build se
alguém, no futuro, acoplar o AssetFlow a uma tecnologia de IA específica.

Regras verificadas:

1. Nenhum módulo fora de ``generation/engines/`` importa biblioteca de IA
   (``torch``, ``diffusers``, ``transformers``, ``accelerate``, SDKs...).
2. Nenhum módulo fora de ``generation/engines/`` importa uma gaveta concreta.
3. Uma gaveta não importa outra gaveta.
4. O pacote ``engines/__init__.py`` não importa gaveta alguma (senão a
   estante passaria a depender das gavetas).
5. Kernel e schemas não dependem de camadas superiores (jobs, api, storage).
6. Nenhum nome de pipeline de fornecedor aparece fora das gavetas.
7. ``assetflow/pixel/`` é uma ilha: não conhece camada de cima nem biblioteca
   de IA, e dentro de ``generation/`` só a ponte Pixel o importa
   (plano Pixel §105).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.conftest import BACKEND_ROOT

PACKAGE_ROOT = BACKEND_ROOT / "assetflow"
ENGINES_ROOT = PACKAGE_ROOT / "generation" / "engines"

#: Bibliotecas de IA que só podem existir dentro de uma gaveta.
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

#: Símbolos de fornecedor que não podem vazar para fora das gavetas.
VENDOR_SYMBOLS = (
    "StableDiffusionXLPipeline",
    "StableDiffusionPipeline",
    "FluxPipeline",
    "DiffusionPipeline",
    "AutoPipelineForText2Image",
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _is_engine_module(path: Path) -> bool:
    try:
        relative = path.relative_to(ENGINES_ROOT)
    except ValueError:
        return False
    # `engines/__init__.py` é a estante, não uma gaveta.
    return len(relative.parts) > 1


def _engine_package(path: Path) -> str | None:
    try:
        relative = path.relative_to(ENGINES_ROOT)
    except ValueError:
        return None
    return relative.parts[0] if len(relative.parts) > 1 else None


def _imports(path: Path) -> list[tuple[str, int]]:
    """Todos os módulos importados por um arquivo, com a linha."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # import relativo — resolvido separadamente
                continue
            if node.module:
                found.append((node.module, node.lineno))
    return found


def _relative_imports(path: Path) -> list[tuple[int, str, tuple[str, ...]]]:
    """Imports relativos como ``(linha, módulo, nomes)``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            found.append(
                (node.lineno, node.module or "", tuple(alias.name for alias in node.names))
            )
    return found


ALL_FILES = _python_files(PACKAGE_ROOT)
NON_ENGINE_FILES = [path for path in ALL_FILES if not _is_engine_module(path)]


def test_there_are_files_to_inspect():
    assert len(NON_ENGINE_FILES) > 20


@pytest.mark.parametrize(
    "path", NON_ENGINE_FILES, ids=lambda p: str(p.relative_to(PACKAGE_ROOT))
)
def test_no_ai_library_outside_engines(path: Path):
    """Regra de ouro §74."""
    violations = [
        f"{path.name}:{line} importa '{module}'"
        for module, line in _imports(path)
        if module.split(".")[0] in AI_LIBRARIES
    ]
    assert not violations, (
        "biblioteca de IA usada fora de uma gaveta:\n" + "\n".join(violations)
    )


@pytest.mark.parametrize(
    "path", NON_ENGINE_FILES, ids=lambda p: str(p.relative_to(PACKAGE_ROOT))
)
def test_no_concrete_engine_import_outside_engines(path: Path):
    """Regra §18: pipelines e kernel nunca importam uma gaveta."""
    absolute = [
        f"{path.name}:{line} importa '{module}'"
        for module, line in _imports(path)
        if module.startswith("assetflow.generation.engines.")
    ]
    relative = [
        f"{path.name}:{line} importa '.{module}' {names}"
        for line, module, names in _relative_imports(path)
        if module.startswith("engines.") or module.endswith(".engines")
    ]
    assert not (absolute + relative), (
        "gaveta concreta importada fora de engines/ — use o EngineResolver:\n"
        + "\n".join(absolute + relative)
    )


@pytest.mark.parametrize(
    "path", NON_ENGINE_FILES, ids=lambda p: str(p.relative_to(PACKAGE_ROOT))
)
def test_no_vendor_symbol_outside_engines(path: Path):
    source = path.read_text(encoding="utf-8")
    # Comentários e docstrings citam os símbolos ao explicar a proibição;
    # o que não pode é o símbolo aparecer como código executável.
    tree = ast.parse(source, filename=str(path))
    names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    leaked = [symbol for symbol in VENDOR_SYMBOLS if symbol in names]
    assert not leaked, f"{path.name} usa símbolo de fornecedor: {leaked}"


def test_engines_package_init_imports_no_engine():
    """A estante não pode depender das gavetas."""
    init = ENGINES_ROOT / "__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8"), filename=str(init))
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert not imports, "engines/__init__.py deve permanecer sem imports"


def test_engines_do_not_import_each_other():
    """Cada gaveta é independente das outras."""
    violations: list[str] = []
    for path in ALL_FILES:
        package = _engine_package(path)
        if package is None:
            continue
        for module, line in _imports(path):
            if module.startswith("assetflow.generation.engines."):
                other = module.split(".")[3]
                if other != package:
                    violations.append(f"{path.name}:{line} importa a gaveta '{other}'")
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    "path",
    _python_files(PACKAGE_ROOT / "generation" / "kernel")
    + _python_files(PACKAGE_ROOT / "generation" / "schemas"),
    ids=lambda p: str(p.relative_to(PACKAGE_ROOT)),
)
def test_kernel_and_schemas_do_not_depend_on_upper_layers(path: Path):
    """O núcleo não pode conhecer API, jobs, storage nem pipelines."""
    forbidden = ("assetflow.api", "assetflow.jobs", "assetflow.storage", "assetflow.bootstrap")
    violations = [
        f"{path.name}:{line} importa '{module}'"
        for module, line in _imports(path)
        if module.startswith(forbidden)
    ]
    relative_violations = [
        f"{path.name}:{line} importa '.{module}'"
        for line, module, _names in _relative_imports(path)
        if module.split(".")[0] in {"api", "jobs", "storage", "bootstrap", "pipelines"}
    ]
    assert not (violations + relative_violations), "\n".join(violations + relative_violations)


def test_every_engine_has_a_manifest():
    for directory in sorted(ENGINES_ROOT.iterdir()):
        if not directory.is_dir() or directory.name == "__pycache__":
            continue
        assert (directory / "manifest.json").exists(), (
            f"a gaveta '{directory.name}' não tem manifest.json e nunca será descoberta"
        )


# ---------------------------------------------------------------------------
# 7. O módulo Pixel é uma ilha (plano Pixel §105)
# ---------------------------------------------------------------------------
# ``assetflow/pixel/`` é a tecnologia Pixel Exact: entra ``(imagem,
# PixelOutputSpec)``, sai ``(imagem, relatórios)``. Ele não sabe qual motor
# produziu a imagem, nem que existem job, projeto ou storage — é por isso que
# ele pertence à **estante** do AssetFlow e nunca a uma gaveta.
#
# Essa promessa some com um único ``import`` mal colocado, e some em silêncio:
# o sistema continua funcionando, só que o módulo Pixel deixa de ser reusável
# fora do pipeline de geração. Os testes desta seção medem as duas direções da
# fronteira — o que o Pixel enxerga, e quem enxerga o Pixel.

PIXEL_ROOT = PACKAGE_ROOT / "pixel"
GENERATION_ROOT = PACKAGE_ROOT / "generation"

PIXEL_FILES = _python_files(PIXEL_ROOT)
GENERATION_FILES = _python_files(GENERATION_ROOT)

#: Camadas que o módulo Pixel não pode enxergar. ``generation.schemas`` fica
#: de fora de propósito: é a camada neutra de contratos (``AssetFlowModel``,
#: ``Stopwatch``), sem motor e sem produto dentro.
LAYERS_FORBIDDEN_TO_PIXEL = (
    "assetflow.generation.engines",
    "assetflow.generation.pipelines",
    "assetflow.jobs",
    "assetflow.api",
    "assetflow.storage",
)

#: A ponte: os únicos pacotes de ``generation/`` que podem importar
#: ``assetflow.pixel``. Um traduz ``GenerationProfile`` -> ``PixelOutputSpec``
#: e roda o processador; o outro é o pipeline que os usa.
PIXEL_BRIDGE_PACKAGES = (
    GENERATION_ROOT / "postprocessing" / "pixel",
    GENERATION_ROOT / "pipelines" / "pixel",
)

#: Onde o nome ``assetflow.pixel`` não pode aparecer de jeito nenhum: o núcleo
#: (kernel, schemas, prompting) e as gavetas.
PIXEL_FREE_PACKAGES = (
    GENERATION_ROOT / "kernel",
    GENERATION_ROOT / "schemas",
    GENERATION_ROOT / "prompting",
    ENGINES_ROOT,
)

PIXEL_FREE_FILES = [
    path for package in PIXEL_FREE_PACKAGES for path in _python_files(package)
]


def _module_name(path: Path) -> str:
    """``assetflow/pixel/service.py`` -> ``assetflow.pixel.service``."""
    parts = path.relative_to(PACKAGE_ROOT.parent).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_name(path: Path) -> str:
    """O pacote a partir do qual os imports relativos do arquivo resolvem."""
    module = _module_name(path)
    return module if path.name == "__init__.py" else module.rpartition(".")[0]


def _resolved_imports(path: Path) -> list[tuple[str, int]]:
    """Todos os imports do arquivo **em forma absoluta**, com a linha.

    Resolver o relativo é o que dá valor a esta seção: ``from .pixel import``
    dentro de ``generation/pipelines/`` é o subpacote de pipelines, enquanto
    ``from ....pixel import`` é o módulo Pixel. Comparar texto não distingue
    os dois — só a contagem de níveis distingue.

    Os nomes importados entram como módulos candidatos (``from ... import
    pixel`` vira ``assetflow.pixel``); um nome que na verdade é uma classe
    apenas gera um candidato que ninguém casa.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_name(path).split(".")
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # `level=1` é o próprio pacote; cada nível a mais sobe um.
                kept = max(0, len(package) - (node.level - 1))
                prefix = [*package[:kept], *(node.module.split(".") if node.module else [])]
            else:
                prefix = node.module.split(".") if node.module else []
            if not prefix:
                continue
            base = ".".join(prefix)
            found.append((base, node.lineno))
            found.extend((f"{base}.{alias.name}", node.lineno) for alias in node.names)
    return found


def _imports_any(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def _inside(path: Path, package: Path) -> bool:
    return package in path.parents


def test_there_are_pixel_files_to_inspect():
    """Guarda da própria seção: parametrização vazia passa sem provar nada."""
    assert len(PIXEL_FILES) > 20
    assert len(PIXEL_FREE_FILES) > 10


@pytest.mark.parametrize(
    "path", PIXEL_FILES, ids=lambda p: str(p.relative_to(PACKAGE_ROOT))
)
def test_pixel_module_does_not_import_upper_layers(path: Path):
    """Plano Pixel §105: o Pixel é estante, e estante não olha para cima.

    Ele recebe imagem e contrato, devolve imagem e relatório. Job, API,
    storage, gaveta e pipeline são a camada que **chama** o Pixel; se ele
    passasse a chamá-los de volta, deixaria de ser utilizável fora do pipeline
    de geração — e o pacote inteiro, que hoje é uma tecnologia isolada,
    viraria mais um pedaço acoplado ao produto.
    """
    violations = [
        f"{path.name}:{line} importa '{module}'"
        for module, line in _resolved_imports(path)
        if _imports_any(module, LAYERS_FORBIDDEN_TO_PIXEL)
    ]
    assert not violations, (
        "assetflow/pixel/ não pode depender da camada de cima:\n" + "\n".join(violations)
    )


@pytest.mark.parametrize(
    "path", PIXEL_FILES, ids=lambda p: str(p.relative_to(PACKAGE_ROOT))
)
def test_pixel_module_has_no_ai_library(path: Path):
    """Plano Pixel §5 e §105: o Pixel não faz ideia de quem gerou a imagem.

    A regra §74 já proíbe biblioteca de IA fora das gavetas, mas aqui ela vale
    por um motivo próprio: o Pixel Exact precisa continuar medindo do mesmo
    jeito a saída do SDXL de hoje e a de um motor que ainda não existe. Basta
    um ``import torch`` para que trocar de motor passe a exigir mexer na
    tecnologia Pixel.
    """
    violations = [
        f"{path.name}:{line} importa '{module}'"
        for module, line in _resolved_imports(path)
        if module.split(".")[0] in AI_LIBRARIES
    ]
    assert not violations, (
        "biblioteca de IA dentro do módulo Pixel:\n" + "\n".join(violations)
    )


def test_only_the_pixel_bridge_imports_the_pixel_module():
    """A outra direção: dentro de ``generation/``, só a ponte conhece o Pixel.

    O acesso ao módulo Pixel é concentrado em dois pacotes — o
    pós-processamento (``generation/postprocessing/pixel/``) e o pipeline
    (``generation/pipelines/pixel/``). Espalhar esse import pelo resto de
    ``generation/`` tornaria a tecnologia Pixel uma dependência difusa do
    motor de geração, e não uma peça plugada em um ponto conhecido
    (plano Pixel §105).
    """
    importers = {
        path
        for path in GENERATION_FILES
        for module, _line in _resolved_imports(path)
        if _imports_any(module, ("assetflow.pixel",))
    }
    assert importers, (
        "ninguém em generation/ importa assetflow.pixel — a detecção quebrou "
        "(ou a ponte sumiu), e o teste passaria vazio"
    )

    outsiders = sorted(
        str(path.relative_to(PACKAGE_ROOT))
        for path in importers
        if not any(_inside(path, package) for package in PIXEL_BRIDGE_PACKAGES)
    )
    assert not outsiders, (
        "assetflow.pixel importado fora da ponte Pixel:\n" + "\n".join(outsiders)
    )


@pytest.mark.parametrize(
    "path", PIXEL_FREE_FILES, ids=lambda p: str(p.relative_to(PACKAGE_ROOT))
)
def test_kernel_schemas_prompting_and_engines_ignore_the_pixel_module(path: Path):
    """O núcleo e as gavetas não sabem que Pixel Exact existe (plano Pixel §105).

    O Kernel resolve capacidade e chama motor; a gaveta gera imagem. Nenhum
    dos dois decide o que é Pixel Art — quem sabe disso é o produto, acima
    deles. Um ``import assetflow.pixel`` no Kernel significaria um kernel com
    opinião sobre modo de arte; na gaveta, significaria uma gaveta obrigada a
    entregar Pixel Exact por conta própria, exatamente a divisão de trabalho
    que o plano §18 desfaz.
    """
    violations = [
        f"{path.name}:{line} importa '{module}'"
        for module, line in _resolved_imports(path)
        if _imports_any(module, ("assetflow.pixel",))
    ]
    assert not violations, "\n".join(violations)
