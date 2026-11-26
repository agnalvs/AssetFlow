"""Lote 11: o aviso de servidor desatualizado."""

from __future__ import annotations

import json
import os
import time

from fastapi.testclient import TestClient

from assetflow.api.app import create_app
from assetflow.servidores import registrar, situacao, vivo
from assetflow.versao import commit_do_git, ultima_alteracao


def _gravar(settings, processo, pid, commit, subiu_ts):
    pasta = settings.data_dir / "servidores"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{processo}-{pid}.json").write_text(json.dumps({
        "processo": processo, "pid": pid, "commit": commit,
        "subiu_em": "2026-11-26T00:00:00+00:00", "subiu_ts": subiu_ts,
    }), encoding="utf-8")


def test_vivo_reconhece_este_processo_e_um_que_nao_existe():
    assert vivo(os.getpid())
    assert not vivo(0) and not vivo(2_000_000_000)


def test_processo_em_dia_nao_avisa(settings):
    registrar(settings, "mcp")
    estado = situacao(settings)
    assert estado["codigo"]["commit"] == commit_do_git(settings.base_dir)
    assert [p["processo"] for p in estado["processos"]] == ["mcp"]
    assert estado["aviso"] is None


def test_commit_novo_sem_arquivo_alterado_nao_avisa(settings):
    """O --reload reinicia a API antes do commit: o commit sozinho não desatualiza."""
    _gravar(settings, "api", os.getpid(), "0000000", time.time())
    _gravar(settings, "mcp", os.getpid(), "0000000", time.time())
    estado = situacao(settings)
    assert estado["aviso"] is None
    assert {p["commit"] for p in estado["processos"]} == {"0000000"}  # fica como informação


def test_pasta_que_ninguem_le_nao_conta(tmp_path):
    lido = tmp_path / "config" / "engines.yaml"
    proposta = tmp_path / "config" / "pixel_knowledge" / "propostas" / "nova.yaml"
    for arquivo in (lido, proposta):
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text("x", encoding="utf-8")
    os.utime(lido, (1_000, 1_000))
    os.utime(proposta, (2_000, 2_000))
    assert ultima_alteracao(tmp_path / "config") == 2_000
    assert ultima_alteracao(tmp_path / "config", ignorar=("propostas",)) == 1_000


def test_codigo_mudado_depois_da_subida_tambem_conta(settings):
    _gravar(settings, "mcp", os.getpid(), commit_do_git(settings.base_dir), 0.0)
    estado = situacao(settings)
    assert "mudou às" in estado["aviso"] and "/mcp" in estado["aviso"]
    _gravar(settings, "api", os.getpid() + 0, commit_do_git(settings.base_dir), 0.0)
    assert "reinicie a API" in situacao(settings)["aviso"]


def test_registro_de_processo_morto_some(settings):
    _gravar(settings, "mcp", 2_000_000_000, "0000000", 0.0)
    assert situacao(settings)["processos"] == []
    assert not (settings.data_dir / "servidores" / "mcp-2000000000.json").exists()


def test_a_api_se_registra_e_a_rota_avisa(container):
    with TestClient(create_app(container=container)) as cliente:
        assert (container.settings.data_dir / "servidores" / f"api-{os.getpid()}.json").exists()
        _gravar(container.settings, "mcp", os.getpid(), "0000000", 0.0)
        assert "reconecte pelo /mcp" in cliente.get("/api/servidores").json()["aviso"]
        container.settings.servidores.aviso = False
        assert cliente.get("/api/servidores").json()["aviso"] is None
    assert not (container.settings.data_dir / "servidores" / f"api-{os.getpid()}.json").exists()
