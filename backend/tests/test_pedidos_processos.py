"""Dois processos de verdade escrevendo na mesma fila, ao mesmo tempo.

É o caso real: o uvicorn da API e o ``python -m assetflow.mcp`` do Claude
Code são processos diferentes sobre o mesmo SQLite. Duas conexões no mesmo
processo não provariam nada sobre travas de arquivo; aqui são dois
interpretadores Python, soltos no mesmo instante (``tests/_processo_fila.py``).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

from assetflow.pedidos import FilaDePedidos, Situacao, Tipo
from tests.conftest import BACKEND_ROOT


def _soltar(papel: str, banco: Path, largada: Path, extras: dict[str, str]) -> dict[str, dict]:
    """Sobe um processo por rótulo, espera os dois ficarem prontos e solta juntos."""
    processos = {
        rotulo: subprocess.Popen(
            [sys.executable, "-m", "tests._processo_fila", papel, str(banco), str(largada), rotulo, extra],
            cwd=BACKEND_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for rotulo, extra in extras.items()
    }
    limite = time.monotonic() + 60
    while not all(Path(f"{largada}.{rotulo}").exists() for rotulo in processos):
        assert time.monotonic() < limite, "os processos não ficaram prontos"
        for rotulo, processo in processos.items():
            assert processo.poll() is None, processo.communicate()[1]
        time.sleep(0.02)
    largada.touch()

    saidas = {}
    for rotulo, processo in processos.items():
        stdout, stderr = processo.communicate(timeout=120)
        assert processo.returncode == 0, f"processo {rotulo} falhou:\n{stderr}"
        saidas[rotulo] = json.loads(stdout.strip().splitlines()[-1])
    return saidas


def test_dois_processos_criam_ao_mesmo_tempo_sem_perder_nada(tmp_path: Path):
    banco = tmp_path / "pedidos.sqlite3"
    FilaDePedidos(banco).listar()  # o arquivo já existe, em WAL, antes da largada

    saidas = _soltar("criar", banco, tmp_path / "largada", {"A": "80", "B": "80"})

    criados = saidas["A"]["criados"] + saidas["B"]["criados"]
    gravados = FilaDePedidos(banco).listar(limite=1000)
    assert len(criados) == len(set(criados)) == 160
    assert {pedido.id for pedido in gravados} == set(criados)


def test_dois_processos_disputando_a_fila_nunca_pegam_o_mesmo_pedido(tmp_path: Path):
    banco = tmp_path / "pedidos.sqlite3"
    fila = FilaDePedidos(banco, reserva=timedelta(minutes=30))
    todos = [
        fila.criar(
            tipo=Tipo.DESENHO,
            projeto="principal",
            texto=f"pedido {n}",
            liberdade="equilibrado",
            direcao_de_arte=None,
            corpo={},
            leitura={"resolved": {}},
        ).id
        for n in range(60)
    ]
    # O disputado fica fora da fila (reservado aqui) e os dois o querem concluir.
    disputado = todos.pop()
    fila.reservar([disputado], "lev_teste")

    saidas = _soltar(
        "disputar", banco, tmp_path / "largada", {"A": disputado, "B": disputado}
    )

    de_a, de_b = set(saidas["A"]["reservados"]), set(saidas["B"]["reservados"])
    assert not de_a & de_b, "um pedido foi reservado pelos dois processos"
    assert de_a | de_b == set(todos), "pedido perdido ou desenhado duas vezes"
    vencedores = [rotulo for rotulo, saida in saidas.items() if saida["ganhou_o_disputado"]]
    assert len(vencedores) == 1, "o disputado tem de ser concluído por um processo só"

    final = {pedido.id: pedido for pedido in fila.listar(limite=1000)}
    assert all(final[pid].situacao is Situacao.CONCLUIDO for pid in todos + [disputado])
    assert final[disputado].asset_id == f"asset_{vencedores[0]}_disputado"
