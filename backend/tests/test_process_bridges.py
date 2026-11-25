"""As pontes para processos externos (Pixel Forge e SD-πXL).

Estas duas gavetas não importam biblioteca nenhuma: elas executam um binário e
leem os PNGs que saírem. É o que mantém o backend livre do runtime Rust do
Pixel Forge e do ambiente Python do SD-πXL (plano de motores §8.3).

O defeito que este arquivo existe para trancar
-----------------------------------------------
As duas ficaram **permanentemente inutilizáveis**, mesmo depois de
configuradas, por causa de um ciclo entre três peças:

1. com ``lazy_load``, ``initialize()`` só roda no primeiro job — até lá a
   gaveta não tinha recebido a configuração dela;
2. o ``health_check()`` respondia a partir dessa configuração ausente, e
   dizia "não configurado" sobre uma gaveta que **estava** configurada;
3. o ``EngineHandle`` transformava esse "indisponível" em estado ``FAILED``.

E ``FAILED`` é recusado pelo resolver — então ``initialize()`` nunca rodava,
a configuração nunca chegava, e o health check nunca podia melhorar. Um motor
que só sabia responder que não estava pronto, para sempre.

A correção tem três partes, e cada uma é testada abaixo: a instância recebe a
configuração ao ser criada, o health check lê de lá, e um "indisponível"
anterior à inicialização deixou de reprovar o motor.
"""

from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

import pytest

from assetflow.bootstrap import AppContainer, build_container
from assetflow.generation.schemas import AssetGenerationRequest, EngineState
from assetflow.settings import Settings, engine_runtime_configs
from tests.conftest import run

BRIDGES = ("pixel-forge-v1", "sdpixl-v1")


# ---------------------------------------------------------------------------
# Um executável de mentira com a forma de CLI que as duas pontes esperam.
# ---------------------------------------------------------------------------
_FAKE = r"""
import argparse, os, struct, sys, zlib

# Registra o argv quando pedido: é o único jeito de um teste provar o que foi
# de fato invocado, em vez de provar a intenção de quem montou a configuração.
destino = os.environ.get("FAKE_ARGV_LOG")
if destino:
    with open(destino, "w", encoding="utf-8") as handle:
        handle.write(" ".join(sys.argv[1:]))

p = argparse.ArgumentParser()
p.add_argument("positional", nargs="*")     # `generate <classe>`, quando houver
p.add_argument("--prompt", default="")
p.add_argument("--seed", type=int, default=0)
p.add_argument("--size", type=int, default=32)
p.add_argument("--out", "--output", dest="out", required=True)
a, _desconhecidos = p.parse_known_args()

n = a.size
linhas = []
for y in range(n):
    linha = bytearray([0])
    for x in range(n):
        borda = x in (0, n - 1) or y in (0, n - 1)
        dentro = 6 <= x < n - 6 and 6 <= y < n - 6
        if borda:
            cor = (20, 20, 20, 255)
        elif dentro:
            cor = (200, 60, 60, 255)
        else:
            cor = (0, 0, 0, 0)
        linha += bytes(cor)
    linhas.append(bytes(linha))

bruto = b"".join(linhas)
png = bytes([137, 80, 78, 71, 13, 10, 26, 10])
for tag, corpo in ((b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)),
                   (b"IDAT", zlib.compress(bruto)),
                   (b"IEND", b"")):
    png += struct.pack(">I", len(corpo)) + tag + corpo
    png += struct.pack(">I", zlib.crc32(tag + corpo) & 0xFFFFFFFF)

with open(a.out, "wb") as handle:
    handle.write(png)
"""


@pytest.fixture
def fake_binary(tmp_path: Path) -> Path:
    """Um "motor" que responde à mesma CLI e grava um PNG 32×32.

    Ele existe para separar duas perguntas que ficavam misturadas: *a ponte do
    AssetFlow funciona?* e *o binário externo está instalado nesta máquina?*.
    Só a primeira é responsabilidade deste repositório, e é a que se testa
    aqui — sem Rust, sem clone e sem rede.
    """
    script = tmp_path / "fake_engine.py"
    script.write_text(_FAKE, encoding="utf-8")
    return script


def _options(binary: Path, engine_id: str) -> str:
    key = "args" if engine_id == "pixel-forge-v1" else "command"
    invocation = [
        str(binary),
        "--prompt", "{prompt}",
        "--seed", "{seed}",
        "--size", "32",
        "--out", "{output}",
    ]
    if engine_id == "pixel-forge-v1":
        return json.dumps({"binary": sys.executable, key: invocation})
    # O SD-πXL recebe o comando inteiro, com o interpretador na frente.
    return json.dumps({key: [sys.executable, *invocation]})


def _env_name(engine_id: str) -> str:
    return f"ASSETFLOW_ENGINE_{engine_id.upper().replace('-', '_')}_OPTIONS"


# ---------------------------------------------------------------------------
# A configuração chega sem editar o YAML versionado
# ---------------------------------------------------------------------------
def test_engine_options_come_from_the_environment(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    """Ligar uma ponte não pode exigir editar `engines.yaml`.

    O caminho do executável é diferente em cada máquina, e `engines.yaml` é
    versionado: escrever um caminho absoluto ali garante conflito a cada
    `git pull` — ou, pior, o caminho de outra pessoa entrando no seu ambiente.
    """
    monkeypatch.setenv(
        _env_name("pixel-forge-v1"), json.dumps({"binary": "X:/pf.exe"})
    )
    config = engine_runtime_configs(settings)["pixel-forge-v1"]

    assert config.options["binary"] == "X:/pf.exe"
    # O merge é por chave: o que o YAML dizia e o ambiente não mencionou fica.
    assert config.options["output_glob"] == "*.png"


def test_broken_json_in_the_environment_warns_instead_of_breaking_boot(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Uma aspa a menos não pode impedir o sistema de subir — nem passar calada."""
    monkeypatch.setenv(_env_name("pixel-forge-v1"), '{"binary": ')
    with caplog.at_level("WARNING"):
        config = engine_runtime_configs(settings)["pixel-forge-v1"]

    assert config.options.get("binary", "") == ""
    assert any("não é JSON válido" in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# O ciclo que trancava as duas gavetas
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("engine_id", BRIDGES)
def test_an_unconfigured_bridge_stays_registered_instead_of_failing(
    container: AppContainer, engine_id: str
):
    """Um health check anterior à inicialização não reprova o motor.

    Sem isto, consultar o catálogo — o que a tela faz ao abrir — trancava as
    duas pontes em ``FAILED``, e o estado nunca mais melhorava porque o
    resolver recusa ``FAILED`` e a inicialização nunca chegava a acontecer.
    """
    container.registry.enable(engine_id)
    entries = run(container.service.engine_catalog(include_hidden=True, check_health=True))
    entry = next(item for item in entries if item.engine_id == engine_id)

    # Sem binário, ela continua indisponível — e isso é correto e honesto.
    assert entry.available is False
    assert entry.unavailable_reason

    # Mas o **estado** não pode ser FAILED: ela não falhou, só não está pronta.
    record = container.registry.get(engine_id)
    assert record.state is not EngineState.FAILED, (
        "a gaveta foi reprovada por um health check anterior à configuração — "
        "é o ciclo que a tornava permanentemente inutilizável"
    )


@pytest.mark.parametrize("engine_id", BRIDGES)
def test_a_configured_bridge_reports_healthy_before_the_first_job(
    settings: Settings, fake_binary: Path, engine_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """O catálogo precisa dizer a verdade **antes** de qualquer geração.

    É a tela abrindo: se uma gaveta configurada aparecer como "indisponível"
    ali, ninguém vai escolhê-la — e a configuração correta não terá servido
    para nada.
    """
    monkeypatch.setenv("ASSETFLOW_ENGINES_ENABLED", engine_id)
    monkeypatch.setenv(_env_name(engine_id), _options(fake_binary, engine_id))
    settings.worker.embedded = False
    container = build_container(settings)

    entries = run(container.service.engine_catalog(include_hidden=True, check_health=True))
    entry = next(item for item in entries if item.engine_id == engine_id)

    assert entry.available is True, entry.unavailable_reason
    assert entry.unavailable_reason is None


# ---------------------------------------------------------------------------
# A ponte inteira, de ponta a ponta
# ---------------------------------------------------------------------------
def test_pixel_forge_generates_a_real_asset_through_the_whole_pipeline(
    settings: Settings, fake_binary: Path, monkeypatch: pytest.MonkeyPatch
):
    """Pedido -> Kernel -> Pixel Forge -> Pixel Exact -> Optimizer -> storage.

    O que este teste prova é o encaixe, não o binário: com o executável real
    no lugar do dublê, o que muda é a arte — não o caminho.
    """
    monkeypatch.setenv("ASSETFLOW_ENGINES_ENABLED", "pixel-forge-v1")
    monkeypatch.setenv(
        _env_name("pixel-forge-v1"), _options(fake_binary, "pixel-forge-v1")
    )
    settings.worker.embedded = False
    container = build_container(settings)

    job = run(container.service.submit(AssetGenerationRequest(
        project_id="p",
        profile="pixel_character_64",
        prompt="uma casa de pedra 32x32 com 8 cores",
        engine={"mode": "manual", "engine_id": "pixel-forge-v1", "allow_fallback": False},
    )))
    run(container.worker.run_once())
    job = run(container.jobs.get(job.id))

    assert job.status.value == "completed", job.error
    assert job.engine.id == "pixel-forge-v1"

    variant = job.asset.variants[0]
    assert (variant.logical_width, variant.logical_height) == (32, 32)
    assert variant.pixel_exact is True
    # E o Optimizer rodou nele, como roda em qualquer motor (§57).
    assert (variant.metadata.get("pixel_metrics") or {}).get("optimizer_status")


def test_a_bridge_that_produces_nothing_fails_loudly(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Um binário que roda e não grava imagem é erro, nunca asset vazio.

    Este é o modo de falha realista de uma ponte mal configurada: o comando
    existe, sai com código 0, e escreve em outro lugar. Devolver um asset em
    branco seria o pior resultado possível.
    """
    quiet = tmp_path / "quiet.py"
    quiet.write_text("print('nada a fazer')\n", encoding="utf-8")
    monkeypatch.setenv("ASSETFLOW_ENGINES_ENABLED", "pixel-forge-v1")
    monkeypatch.setenv(_env_name("pixel-forge-v1"), json.dumps(
        {"binary": sys.executable, "args": [str(quiet)]}
    ))
    settings.worker.embedded = False
    container = build_container(settings)

    job = run(container.service.submit(AssetGenerationRequest(
        project_id="p",
        profile="pixel_character_64",
        prompt="uma casa",
        engine={"mode": "manual", "engine_id": "pixel-forge-v1", "allow_fallback": False},
    )))
    # O worker reenfileira antes de desistir: rodar uma vez só deixaria o job
    # em `queued`, e o teste passaria a afirmar algo sobre o retry, não sobre
    # a ponte.
    for _ in range(settings.worker.max_attempts + 1):
        run(container.worker.run_once())
        job = run(container.jobs.get(job.id))
        if job.status.value in ("failed", "completed"):
            break

    assert job.status.value == "failed"
    assert job.asset is None


# ---------------------------------------------------------------------------
# O que o dublê garante sobre o formato
# ---------------------------------------------------------------------------
def test_the_stand_in_binary_really_produces_a_readable_png(
    fake_binary: Path, tmp_path: Path
):
    """Um dublê que produzisse lixo faria os testes acima passarem por engano."""
    import subprocess

    destino = tmp_path / "out.png"
    subprocess.run(
        [sys.executable, str(fake_binary), "--prompt", "x", "--seed", "1",
         "--size", "32", "--out", str(destino)],
        check=True, capture_output=True,
    )

    data = destino.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (32, 32)
    assert zlib.crc32(b"IEND") & 0xFFFFFFFF == struct.unpack(">I", data[-4:])[0]


# ---------------------------------------------------------------------------
# O Pixel Forge é condicionado por CLASSE, não por prompt
# ---------------------------------------------------------------------------
def test_the_subject_decides_the_class_not_the_asset_type():
    """A CLI real é ``generate <classe>``, de um vocabulário fechado.

    E a ordem da resolução é a decisão inteira: para o AssetFlow "uma casa de
    pedra" é um `prop`; para o Pixel Forge é um `building`. Perguntar primeiro
    ao tipo entregaria `misc` — a classe que não diz nada — para um pedido que
    dizia tudo.
    """
    from assetflow.generation.engines.pixel_forge.config import PixelForgeConfig

    config = PixelForgeConfig()

    assert config.resolve_class("prop", "uma casa de pedra") == "building"
    assert config.resolve_class("prop", "espada longa") == "weapon"
    assert config.resolve_class("prop", "poção vermelha") == "potion"
    # Sem sujeito reconhecido, o tipo responde.
    assert config.resolve_class("tileset", "grass") == "terrain"
    assert config.resolve_class("character", "cavaleiro") == "character"
    # E sem nenhum dos dois, a classe neutra — nunca vazio, que seria erro de
    # invocação em vez de geração genérica.
    assert config.resolve_class("prop", "candelabro") == "misc"


def test_the_subject_is_matched_by_word_not_by_substring():
    """`pá` dentro de `pássaro` faria uma ave virar ferramenta."""
    from assetflow.generation.engines.pixel_forge.config import PixelForgeConfig

    assert PixelForgeConfig().resolve_class("prop", "pássaro") != "tool"


def test_the_class_vocabulary_is_configuration():
    """O vocabulário válido depende do modelo **treinado**, que não é nosso.

    Um mapa fixo em código seria uma promessa sobre o modelo de outra pessoa.
    """
    from assetflow.generation.engines.pixel_forge.config import PixelForgeConfig

    config = PixelForgeConfig(
        subject_map={"candelabro": "prop_luminoso"},
        class_map={"tileset": "chao"},
        fallback_class="nada",
    )

    assert config.resolve_class("prop", "candelabro") == "prop_luminoso"
    assert config.resolve_class("tileset", "grass") == "chao"
    # `icon` está no mapa padrão; o fallback é para o que não está.
    assert config.resolve_class("tipo-que-nao-existe", "xyz") == "nada"


def test_the_bridge_sends_the_class_on_the_command_line(
    settings: Settings, fake_binary: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """De ponta a ponta: o que chega ao processo é a classe, não a frase.

    O dublê registra o `argv` que recebeu. É o único jeito de provar o que foi
    de fato invocado — inspecionar a configuração provaria a intenção de quem
    a montou, que é outra coisa.
    """
    registro = tmp_path / "argv.txt"
    monkeypatch.setenv("FAKE_ARGV_LOG", str(registro))
    monkeypatch.setenv("ASSETFLOW_ENGINES_ENABLED", "pixel-forge-v1")
    monkeypatch.setenv(_env_name("pixel-forge-v1"), json.dumps({
        "binary": sys.executable,
        "args": [
            str(fake_binary), "generate", "{class}",
            "--size", "{size}", "--seed", "{seed}", "--output", "{output}",
        ],
    }))
    settings.worker.embedded = False
    container = build_container(settings)

    job = run(container.service.submit(AssetGenerationRequest(
        project_id="p",
        profile="pixel_character_64",
        prompt="uma casa de pedra 32x32 com 8 cores",
        engine={"mode": "manual", "engine_id": "pixel-forge-v1", "allow_fallback": False},
    )))
    run(container.worker.run_once())
    job = run(container.jobs.get(job.id))

    assert job.status.value == "completed", job.error
    argv = registro.read_text(encoding="utf-8")

    assert " generate building " in f" {argv} ", argv
    assert "--size 32" in argv
    # E a frase inteira **não** foi para a linha de comando: o Pixel Forge
    # recusaria, e "uma casa de pedra 32x32" não é uma classe.
    assert "uma casa de pedra" not in argv
