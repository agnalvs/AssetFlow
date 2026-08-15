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
