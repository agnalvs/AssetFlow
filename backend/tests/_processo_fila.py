"""Um processo que escreve na fila de pedidos, para o teste de dois processos.

Não é um teste (o nome não começa com ``test_``): ``test_pedidos_processos``
sobe dois destes com ``python -m tests._processo_fila`` e solta os dois ao
mesmo tempo. Cada um avisa que está pronto criando ``<largada>.<rótulo>`` e
espera o arquivo ``<largada>`` existir antes de começar a escrever.

    criar      <banco> <largada> <rótulo> <quantos>
    disputar   <banco> <largada> <rótulo> <disputado>

``criar`` cria ``quantos`` pedidos. ``disputar`` reserva pedidos de 3 em 3 até
a fila esvaziar, desenha (inicia e conclui) cada um que reservou e tenta
concluir também o pedido ``disputado``, que os dois processos querem. A saída
é um JSON numa linha, em stdout.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import timedelta
from pathlib import Path

from assetflow.pedidos import FilaDePedidos, Tipo, TransicaoRecusada, nova_leva


def _largar(largada: Path, rotulo: str) -> None:
    Path(f"{largada}.{rotulo}").touch()
    limite = time.monotonic() + 60
    while not largada.exists():
        if time.monotonic() > limite:
            raise SystemExit("a largada não veio")
        time.sleep(0.005)


def _criar(fila: FilaDePedidos, rotulo: str, quantos: int) -> dict:
    ids = [
        fila.criar(
            tipo=Tipo.DESENHO,
            projeto="principal",
            texto=f"{rotulo} {n}",
            liberdade="equilibrado",
            direcao_de_arte=None,
            corpo={"prompt": f"{rotulo} {n}"},
            leitura={"resolved": {}},
        ).id
        for n in range(quantos)
    ]
    return {"criados": ids}


def _disputar(fila: FilaDePedidos, rotulo: str, disputado: str) -> dict:
    meus: list[str] = []
    while True:
        candidatos = fila.candidatos(3)
        if not candidatos:
            break
        reservados = fila.reservar([p.id for p in candidatos], nova_leva())
        for pedido in reservados:
            fila.iniciar(pedido.id)
            if fila.concluir(
                pedido.id,
                asset_id=f"asset_{rotulo}_{pedido.id}",
                job_id=f"job_{rotulo}",
                asset_projeto="principal",
                laudo=rotulo,
            ) is None:
                raise SystemExit(f"{pedido.id} reservado por {rotulo} e concluído por outro")
            meus.append(pedido.id)

    ganhou = False
    try:
        fila.iniciar(disputado)
        ganhou = (
            fila.concluir(
                disputado,
                asset_id=f"asset_{rotulo}_disputado",
                job_id=f"job_{rotulo}",
                asset_projeto="principal",
                laudo=rotulo,
            )
            is not None
        )
    except TransicaoRecusada:
        ganhou = False
    return {"reservados": meus, "ganhou_o_disputado": ganhou}


def main(argv: list[str]) -> None:
    papel, banco, largada, rotulo, extra = argv
    fila = FilaDePedidos(Path(banco), espera_s=15.0, reserva=timedelta(minutes=30))
    _largar(Path(largada), rotulo)
    if papel == "criar":
        resultado = _criar(fila, rotulo, int(extra))
    else:
        resultado = _disputar(fila, rotulo, extra)
    print(json.dumps(resultado))


if __name__ == "__main__":
    main(sys.argv[1:])
