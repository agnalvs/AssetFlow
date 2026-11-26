"""Lote 9: a cópia de segurança de backend/data/."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from assetflow.api.app import create_app
from assetflow.backup import ErroDaCopia, criar_copia, listar_copias, restaurar_copia
from assetflow.backup.__main__ import main
from assetflow.pedidos import CorpoDoPedido
from tests.conftest import run


@pytest.fixture
def fora():
    """Uma pasta fora do repositório (o tmp do pytest fica dentro dele)."""
    with tempfile.TemporaryDirectory(prefix="assetflow-copias-") as pasta:
        yield Path(pasta)


def _pedidos(caminho: Path) -> int:
    conexao = sqlite3.connect(caminho)
    try:
        return conexao.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0]
    finally:
        conexao.close()


def _criar(container, texto="poção 16x16"):
    return run(container.pedidos.criar(CorpoDoPedido(prompt=texto, profile="pixel_prop_64",
                                                     modo_conceito="sem_conceito")))


def test_a_copia_leva_as_partes_e_o_wal_vai_junto(container, fora):
    _criar(container)
    _criar(container, "espada 32x32")
    asset = container.settings.storage_root / "projects" / "principal" / "jobs" / "job_x" / "000.png"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"png")
    wal = container.settings.pedidos_path.with_name("pedidos.sqlite3-wal")
    assert wal.exists() and wal.stat().st_size > 0  # o que foi gravado ainda está no -wal

    copia = criar_copia(container.settings, pasta=fora)

    assert copia.arquivo.parent == fora.resolve() and copia.arquivo.name.startswith("assetflow-dados-")
    with zipfile.ZipFile(copia.arquivo) as zip_:
        nomes = set(zip_.namelist())
        manifesto = json.loads(zip_.read("copia.json"))
        assert "pedidos/pedidos.sqlite3" in nomes and "pedidos/pedidos.sqlite3-wal" not in nomes
        assert "assets/projects/principal/jobs/job_x/000.png" in nomes
        extraido = fora / "conferir.sqlite3"
        extraido.write_bytes(zip_.read("pedidos/pedidos.sqlite3"))
    assert _pedidos(extraido) == 2  # um arquivo só, com o que estava no -wal
    assert {"pedidos", "assets"} <= set(manifesto["partes"])
    assert all(len(item["sha256"]) == 64 for item in manifesto["arquivos"])
    assert [c.arquivo for c in listar_copias(container.settings, pasta=fora)] == [copia.arquivo]


def test_a_copia_recusa_pasta_dentro_do_repositorio(container, tmp_path):
    with pytest.raises(ErroDaCopia, match="dentro do repositório"):
        criar_copia(container.settings, pasta=tmp_path)


def test_restaurar_ensaia_confere_e_guarda_o_que_havia(container, fora):
    _criar(container)
    copia = criar_copia(container.settings, pasta=fora)
    _criar(container, "baú 32x32")
    assert _pedidos(container.settings.pedidos_path) == 2

    ensaio = restaurar_copia(container.settings, copia.arquivo)
    assert ensaio.ensaio and "pedidos" in ensaio.partes
    assert _pedidos(container.settings.pedidos_path) == 2  # o ensaio não muda nada

    feito = restaurar_copia(container.settings, copia.arquivo, confirmar=True)
    assert _pedidos(container.settings.pedidos_path) == 1
    assert feito.guardado_em is not None and (feito.guardado_em / "pedidos" / "pedidos.sqlite3").exists()
    assert _pedidos(feito.guardado_em / "pedidos" / "pedidos.sqlite3") == 2  # nada foi apagado


def test_restaurar_recusa_banco_em_uso_e_copia_danificada(container, fora):
    _criar(container)
    copia = criar_copia(container.settings, pasta=fora)

    ocupado = sqlite3.connect(container.settings.pedidos_path)
    ocupado.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(ErroDaCopia, match="feche a API e o servidor MCP"):
            restaurar_copia(container.settings, copia.arquivo, confirmar=True)
    finally:
        ocupado.rollback()
        ocupado.close()

    danificada = fora / "danificada.zip"
    with zipfile.ZipFile(copia.arquivo) as origem, zipfile.ZipFile(danificada, "w") as destino:
        for nome in origem.namelist():
            dados = origem.read(nome)
            destino.writestr(nome, dados + b"x" if nome.startswith("pedidos/") else dados)
    with pytest.raises(ErroDaCopia, match="danificada"):
        restaurar_copia(container.settings, danificada)


def test_pela_tela_e_o_interruptor(container, fora):
    container.settings.backup.pasta = str(fora)
    with TestClient(create_app(container=container)) as cliente:
        criada = cliente.post("/api/backup")
        assert criada.status_code == 201, criada.text
        lista = cliente.get("/api/backup").json()
        assert lista["items"][0]["nome"] == criada.json()["nome"]
        container.settings.backup.ligado = False
        desligada = cliente.post("/api/backup")
    assert desligada.status_code == 400 and "ASSETFLOW_BACKUP" in desligada.json()["message"]


def test_o_comando(container, fora, monkeypatch, capsys):
    container.settings.backup.pasta = str(fora)
    monkeypatch.setattr("assetflow.backup.__main__.load_settings", lambda: container.settings)
    assert main(["criar"]) == 0
    assert "cópia gravada:" in capsys.readouterr().out
    assert main(["listar"]) == 0
    assert "assetflow-dados-" in capsys.readouterr().out
