"""Lote 10: o iniciar.bat e o lançador (scripts/iniciar.py)."""

from __future__ import annotations

import importlib.util
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.conftest import BACKEND_ROOT

_spec = importlib.util.spec_from_file_location("iniciar", BACKEND_ROOT / "scripts" / "iniciar.py")
iniciar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(iniciar)


def _servidor(rotas: dict[str, tuple[str, str]]):
    """Um HTTP local que responde ``rotas[caminho] = (tipo, corpo)``."""

    class Atende(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in rotas:
                self.send_response(404)
                self.end_headers()
                return
            tipo, corpo = rotas[self.path]
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.end_headers()
            self.wfile.write(corpo.encode("utf-8"))

        def log_message(self, *args):
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Atende)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


@pytest.fixture
def outro_app():
    servidor = _servidor({"/": ("text/html", "<title>Outro app</title>")})
    yield servidor
    servidor.shutdown()


@pytest.fixture
def assetflow():
    saude = json.dumps({"status": "ok", "version": "x", "engines": {"desenhista-v1": "ready"}})
    servidor = _servidor({
        "/": ("text/html", "<html><head><title>AssetFlow — Crie assets</title></head></html>"),
        "/api/health": ("application/json", saude),
    })
    yield servidor
    servidor.shutdown()


def test_porta_ocupada_e_pulada(outro_app):
    ocupada = outro_app.server_address[1]
    assert iniciar.em_uso(ocupada)
    assert iniciar.porta_livre(ocupada) != ocupada


def test_porta_livre_aceita_escutar():
    porta = iniciar.porta_livre(20_000)
    with socket.socket() as s:
        s.bind(("127.0.0.1", porta))  # não levanta


def test_outro_app_nao_passa_por_assetflow(outro_app):
    base = f"http://127.0.0.1:{outro_app.server_address[1]}"
    assert not iniciar.e_a_api(base)
    assert not iniciar.e_a_tela(base)


def test_a_tela_do_assetflow_e_reconhecida_pelo_titulo_e_pelo_proxy(assetflow):
    base = f"http://127.0.0.1:{assetflow.server_address[1]}"
    assert iniciar.e_a_api(base)
    assert iniciar.e_a_tela(base)


def test_o_bat_chama_o_lancador_e_tem_crlf():
    bat = (BACKEND_ROOT.parent / "iniciar.bat").read_bytes()
    assert b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b"")
    assert b"backend\\scripts\\iniciar.py" in bat


def test_sem_instalacao_diz_o_que_falta(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(iniciar, "BACKEND", tmp_path / "backend")
    monkeypatch.setattr(iniciar, "FRONTEND", tmp_path / "frontend")
    assert iniciar.main(["--sem-navegador"]) == 1
    assert "SETUP.md" in capsys.readouterr().out
