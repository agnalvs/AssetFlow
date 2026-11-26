"""A fila de pedidos no SQLite: transições, reserva, etapas e falhas do arquivo.

Cada transição é um ``UPDATE`` condicional só; estes testes cobram o efeito
de cada uma num processo. A disputa entre dois processos de verdade está em
``test_pedidos_processos.py``.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from assetflow.pedidos import (
    Etapa,
    FilaCorrompida,
    FilaDePedidos,
    FilaIndisponivel,
    PedidoNaoEncontrado,
    Situacao,
    Tipo,
    TransicaoRecusada,
)

T0 = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def _fila(caminho: Path, **opcoes) -> FilaDePedidos:
    padrao = {"espera_s": 1.0, "max_tentativas": 3, "reserva": timedelta(minutes=30)}
    return FilaDePedidos(caminho, **{**padrao, **opcoes})


@pytest.fixture
def fila(tmp_path: Path) -> FilaDePedidos:
    return _fila(tmp_path / "pedidos" / "pedidos.sqlite3")


def _novo(fila: FilaDePedidos, texto: str = "poção azul", agora: datetime = T0):
    return fila.criar(
        tipo=Tipo.DESENHO,
        projeto="principal",
        texto=texto,
        liberdade="equilibrado",
        direcao_de_arte=None,
        corpo={"prompt": texto},
        leitura={"resolved": {}},
        agora=agora,
    )


def _desenho(fila: FilaDePedidos, pedido_id: str, n: int = 1) -> dict:
    return {
        "asset_id": f"asset_{n}",
        "job_id": f"job_{n}",
        "asset_projeto": "principal",
        "laudo": "laudo",
    }


# ---------------------------------------------------------------------------
# Criar, ler, reservar
# ---------------------------------------------------------------------------
def test_criar_grava_pendente_com_evento(fila: FilaDePedidos):
    pedido = _novo(fila)

    assert pedido.id.startswith("ped_")
    assert pedido.situacao is Situacao.PENDENTE
    assert pedido.etapa(T0) is Etapa.NA_FILA
    assert pedido.max_tentativas == 3
    assert [e.situacao for e in pedido.eventos] == [Situacao.PENDENTE]
    assert fila.obter(pedido.id) == pedido


def test_o_arquivo_usa_wal(fila: FilaDePedidos):
    _novo(fila)
    with sqlite3.connect(fila.caminho) as conexao:
        (modo,) = conexao.execute("PRAGMA journal_mode").fetchone()
    assert modo == "wal"


def test_pedido_que_nao_existe(fila: FilaDePedidos):
    with pytest.raises(PedidoNaoEncontrado, match="ped_nada"):
        fila.obter("ped_nada")


def test_listar_do_mais_novo_e_por_situacao(fila: FilaDePedidos):
    a = _novo(fila, "a", T0)
    b = _novo(fila, "b", T0 + timedelta(seconds=1))
    fila.cancelar(a.id, agora=T0 + timedelta(seconds=2))

    assert [p.id for p in fila.listar(projeto="principal")] == [b.id, a.id]
    assert [p.id for p in fila.listar(situacoes=[Situacao.CANCELADO])] == [a.id]
    assert fila.listar(projeto="outro") == []


def test_reservar_pega_os_mais_antigos_uma_vez_so(fila: FilaDePedidos):
    a = _novo(fila, "a", T0)
    b = _novo(fila, "b", T0 + timedelta(seconds=1))

    assert [p.id for p in fila.candidatos(10, T0)] == [a.id, b.id]
    reservados = fila.reservar([a.id, b.id], "lev_1", T0)
    assert [p.id for p in reservados] == [a.id, b.id]
    assert all(p.leva == "lev_1" and p.situacao is Situacao.EM_DESENHO for p in reservados)
    assert all(p.etapa(T0) is Etapa.NA_VEZ for p in reservados)

    assert fila.reservar([a.id], "lev_2", T0) == [], "já reservado não é reservado de novo"
    assert fila.candidatos(10, T0) == []
    assert fila.contar_na_fila(T0) == 0


def test_reserva_vencida_volta_para_a_fila(fila: FilaDePedidos):
    pedido = _novo(fila)
    fila.reservar([pedido.id], "lev_1", T0)
    depois = T0 + timedelta(minutes=31)

    assert fila.obter(pedido.id).etapa(depois) is Etapa.NA_FILA
    assert [p.id for p in fila.candidatos(10, depois)] == [pedido.id]
    assert [p.leva for p in fila.reservar([pedido.id], "lev_2", depois)] == ["lev_2"]


# ---------------------------------------------------------------------------
# Desenho
# ---------------------------------------------------------------------------
def test_iniciar_marca_o_desenho_e_renova_a_leva(fila: FilaDePedidos):
    a, b = _novo(fila, "a"), _novo(fila, "b", T0 + timedelta(seconds=1))
    fila.reservar([a.id, b.id], "lev_1", T0)

    vinte_min = T0 + timedelta(minutes=20)
    iniciado = fila.iniciar(a.id, agora=vinte_min)

    assert iniciado.etapa(vinte_min) is Etapa.DESENHANDO
    assert iniciado.reservado_ate == vinte_min + timedelta(minutes=30)
    outro = fila.obter(b.id)
    assert outro.reservado_ate == vinte_min + timedelta(minutes=30), "a leva inteira ganha prazo"
    assert outro.etapa(vinte_min) is Etapa.NA_VEZ


def test_iniciar_aceita_pedido_devolvido(fila: FilaDePedidos):
    pedido = _novo(fila)
    iniciado = fila.iniciar(pedido.id, agora=T0)
    assert iniciado.situacao is Situacao.EM_DESENHO and iniciado.leva


@pytest.mark.parametrize(
    ("acao", "trecho"),
    [("cancelar", "cancelado na tela: não desenhe"), ("concluir", "já foi concluído com asset_1")],
)
def test_iniciar_recusa_pedido_encerrado(fila: FilaDePedidos, acao: str, trecho: str):
    pedido = _novo(fila)
    if acao == "cancelar":
        fila.cancelar(pedido.id)
    else:
        fila.iniciar(pedido.id)
        fila.aprovar(pedido.id, **_desenho(fila, pedido.id))
        fila.concluir(pedido.id, olhar="ficou bom")

    with pytest.raises(TransicaoRecusada, match=trecho):
        fila.iniciar(pedido.id)


def test_aprovado_espera_o_olhar_e_so_o_concluir_fecha(fila: FilaDePedidos):
    """Fase B2: aprovado no validador não é pronto."""
    pedido = _novo(fila)
    fila.reservar([pedido.id], "lev_1", T0)
    fila.iniciar(pedido.id, agora=T0)

    aprovado = fila.aprovar(pedido.id, **_desenho(fila, pedido.id), agora=T0)
    assert aprovado.situacao is Situacao.EM_REVISAO
    assert aprovado.etapa(T0) is Etapa.OLHANDO
    assert aprovado.candidatos == ("asset_1",) and aprovado.asset_id == "asset_1"
    assert aprovado.reservado_ate is not None, "a reserva continua com quem vai olhar"
    # Um segundo desenho que chegue sem ter começado não vira candidato.
    assert fila.aprovar(pedido.id, **_desenho(fila, pedido.id, 2)) is None

    concluido = fila.concluir(pedido.id, olhar="a silhueta lê bem", agora=T0)
    assert concluido.situacao is Situacao.CONCLUIDO
    assert concluido.etapa(T0) is Etapa.PRONTO
    assert (concluido.asset_id, concluido.job_id) == ("asset_1", "job_1")
    assert concluido.olhar == "a silhueta lê bem"
    assert concluido.desenhando_desde is None and concluido.reservado_ate is None
    assert concluido.eventos[-1].situacao is Situacao.CONCLUIDO
    with pytest.raises(TransicaoRecusada, match="não há o que concluir"):
        fila.concluir(pedido.id, olhar="de novo")


def test_concluir_sem_desenho_aprovado_diz_por_que(fila: FilaDePedidos):
    pedido = _novo(fila)
    with pytest.raises(TransicaoRecusada, match="na fila, sem reserva"):
        fila.concluir(pedido.id, olhar="bom")
    fila.iniciar(pedido.id)
    with pytest.raises(TransicaoRecusada, match="ainda não tem desenho aprovado"):
        fila.concluir(pedido.id, olhar="bom")


def test_remendo_do_olhar_conta_e_tem_teto(fila: FilaDePedidos):
    pedido = _novo(fila)
    fila.iniciar(pedido.id)
    fila.aprovar(pedido.id, **_desenho(fila, pedido.id, 1))

    remendo = fila.iniciar(pedido.id)
    assert remendo.remendando and remendo.situacao is Situacao.EM_DESENHO
    primeiro = fila.aprovar(pedido.id, **_desenho(fila, pedido.id, 2))
    assert (primeiro.situacao, primeiro.remendos) == (Situacao.EM_REVISAO, 1)
    assert primeiro.candidatos == ("asset_1", "asset_2") and primeiro.asset_id == "asset_2"

    fila.iniciar(pedido.id)
    segundo = fila.aprovar(pedido.id, **_desenho(fila, pedido.id, 3))
    assert segundo.remendos == 2 == segundo.max_remendos
    assert segundo.tentativas == 0, "remendo do olhar não é tentativa do validador"

    with pytest.raises(TransicaoRecusada, match="já usou os 2 remendos"):
        fila.iniciar(pedido.id)
    # Concluir com um desenho anterior do pedido vale; com um alheio, não.
    with pytest.raises(TransicaoRecusada, match="não é um desenho aprovado"):
        fila.concluir(pedido.id, olhar="bom", asset_id="asset_9")
    concluido = fila.concluir(pedido.id, olhar="o primeiro lia melhor", asset_id="asset_1")
    assert (concluido.asset_id, concluido.job_id) == ("asset_1", "job_1")


def test_remendo_nao_aprovado_volta_com_o_candidato_de_antes(fila: FilaDePedidos):
    pedido = _novo(fila)
    fila.iniciar(pedido.id)
    fila.aprovar(pedido.id, **_desenho(fila, pedido.id, 1))
    fila.iniciar(pedido.id)

    depois = fila.reprovar(pedido.id, **_desenho(fila, pedido.id, 2), motivo="repete o exemplo")

    assert depois.situacao is Situacao.EM_REVISAO
    assert depois.asset_id == "asset_1" and depois.candidatos == ("asset_1",)
    assert (depois.remendos, depois.tentativas) == (1, 0)
    assert depois.motivo == "repete o exemplo"


def test_remendo_interrompido_nao_gasta_remendo(fila: FilaDePedidos):
    pedido = _novo(fila)
    fila.iniciar(pedido.id)
    fila.aprovar(pedido.id, **_desenho(fila, pedido.id, 1))
    fila.iniciar(pedido.id)

    depois = fila.desenho_interrompido(pedido.id, nota="receita inválida")

    assert depois.situacao is Situacao.EM_REVISAO and depois.remendos == 0


def test_devolvido_em_revisao_volta_so_para_o_olhar(fila: FilaDePedidos):
    pedido = _novo(fila)
    fila.reservar([pedido.id], "lev_1", T0)
    fila.iniciar(pedido.id, agora=T0)
    fila.aprovar(pedido.id, **_desenho(fila, pedido.id, 1), agora=T0)

    devolvido = fila.devolver(pedido.id, agora=T0)
    assert devolvido.situacao is Situacao.PENDENTE and devolvido.candidatos == ("asset_1",)

    (reservado,) = fila.reservar([pedido.id], "lev_2", T0)
    assert reservado.situacao is Situacao.EM_REVISAO, "falta o olhar, não um desenho novo"
    assert reservado.etapa(T0) is Etapa.OLHANDO


def test_reserva_vencida_em_revisao_volta_para_a_fila(fila: FilaDePedidos):
    pedido = _novo(fila)
    fila.reservar([pedido.id], "lev_1", T0)
    fila.iniciar(pedido.id, agora=T0)
    fila.aprovar(pedido.id, **_desenho(fila, pedido.id, 1), agora=T0)

    depois = T0 + timedelta(hours=2)
    assert [p.id for p in fila.candidatos(5, depois)] == [pedido.id]
    (de_novo,) = fila.reservar([pedido.id], "lev_2", depois)
    assert de_novo.situacao is Situacao.EM_REVISAO and de_novo.leva == "lev_2"


def test_envio_fica_gravado_no_pedido(fila: FilaDePedidos):
    pedido = _novo(fila)
    fila.gravar_envio(pedido.id, {"exemplo_ligado": False, "licoes": [{"id": "L1"}]})
    assert fila.obter(pedido.id).envio == {"exemplo_ligado": False, "licoes": [{"id": "L1"}]}


def test_arquivo_de_antes_da_fase_b2_ganha_as_colunas(tmp_path: Path):
    """``ALTER TABLE`` ao abrir: os pedidos antigos continuam como estavam."""
    from assetflow.pedidos import fila as modulo

    caminho = tmp_path / "antigo.sqlite3"
    conexao = sqlite3.connect(caminho)
    conexao.executescript(modulo._ESQUEMA)
    conexao.execute(
        "INSERT INTO pedidos (id, tipo, situacao, projeto, texto, liberdade, corpo, leitura, "
        "max_tentativas, eventos, criado_em, atualizado_em) VALUES ('ped_velho', 'desenho', "
        "'concluido', 'principal', 'x', 'fiel', '{}', '{}', 3, '[]', "
        "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
    )
    conexao.commit()
    conexao.close()

    velho = _fila(caminho).obter("ped_velho")

    assert velho.situacao is Situacao.CONCLUIDO
    assert (velho.remendos, velho.candidatos, velho.olhar, velho.envio) == (0, (), None, None)


def test_cancelado_durante_o_desenho_nao_conclui(fila: FilaDePedidos):
    pedido = _novo(fila)
    fila.iniciar(pedido.id)
    fila.cancelar(pedido.id)

    assert fila.aprovar(pedido.id, **_desenho(fila, pedido.id)) is None
    assert fila.reprovar(pedido.id, **_desenho(fila, pedido.id)) is None
    assert fila.obter(pedido.id).situacao is Situacao.CANCELADO


def test_reprovar_conta_tentativas_e_falha_no_teto(fila: FilaDePedidos):
    pedido = _novo(fila)
    fila.iniciar(pedido.id, agora=T0)

    primeira = fila.reprovar(pedido.id, **_desenho(fila, pedido.id, 1), agora=T0)
    assert (primeira.situacao, primeira.tentativas) == (Situacao.EM_DESENHO, 1)
    assert primeira.etapa(T0) is Etapa.CORRIGINDO

    fila.iniciar(pedido.id, agora=T0)
    fila.reprovar(pedido.id, **_desenho(fila, pedido.id, 2), agora=T0)
    fila.iniciar(pedido.id, agora=T0)
    terceira = fila.reprovar(pedido.id, **_desenho(fila, pedido.id, 3), agora=T0)

    assert terceira.situacao is Situacao.FALHOU
    assert terceira.etapa(T0) is Etapa.NAO_APROVADO
    assert terceira.motivo == "não aprovado em 3 tentativas"
    assert terceira.asset_id == "asset_3", "o último desenho fica ligado ao pedido"
    assert [e.situacao for e in terceira.eventos][-1] is Situacao.FALHOU


def test_desenho_sem_asset_so_tira_a_marca(fila: FilaDePedidos):
    pedido = _novo(fila)
    fila.iniciar(pedido.id, agora=T0)

    depois = fila.desenho_interrompido(pedido.id, nota="receita recusada", agora=T0)

    assert depois.situacao is Situacao.EM_DESENHO and depois.tentativas == 0
    assert depois.etapa(T0) is Etapa.NA_VEZ
    assert depois.eventos[-1].nota == "receita recusada"


# ---------------------------------------------------------------------------
# Cancelar e devolver
# ---------------------------------------------------------------------------
def test_cancelar_e_cancelar_de_novo(fila: FilaDePedidos):
    pedido = _novo(fila)

    assert fila.cancelar(pedido.id).etapa(T0) is Etapa.CANCELADO
    with pytest.raises(TransicaoRecusada, match="já está cancelado") as erro:
        fila.cancelar(pedido.id)
    assert erro.value.pedido.situacao is Situacao.CANCELADO


def test_devolver_volta_para_a_fila_sem_perder_tentativas(fila: FilaDePedidos):
    pedido = _novo(fila)
    fila.reservar([pedido.id], "lev_1", T0)
    fila.iniciar(pedido.id, agora=T0)
    fila.reprovar(pedido.id, **_desenho(fila, pedido.id), agora=T0)

    devolvido = fila.devolver(pedido.id, agora=T0)

    assert devolvido.situacao is Situacao.PENDENTE
    assert devolvido.etapa(T0) is Etapa.NA_FILA
    assert devolvido.tentativas == 1
    assert devolvido.leva is None and devolvido.reservado_ate is None
    with pytest.raises(TransicaoRecusada, match="só um pedido em desenho"):
        fila.devolver(pedido.id)


# ---------------------------------------------------------------------------
# O arquivo: travado e danificado
# ---------------------------------------------------------------------------
def test_banco_travado_vira_erro_claro(tmp_path: Path):
    caminho = tmp_path / "pedidos.sqlite3"
    fila = _fila(caminho, espera_s=0.2)
    _novo(fila)

    outro = sqlite3.connect(caminho, isolation_level=None)
    try:
        outro.execute("BEGIN EXCLUSIVE")
        with pytest.raises(FilaIndisponivel, match="ocupada por outro processo"):
            _novo(fila, "bloqueado")
    finally:
        outro.execute("ROLLBACK")
        outro.close()
    assert len(fila.listar()) == 1, "nada se perdeu"


def test_banco_danificado_vira_erro_claro_e_o_arquivo_fica(tmp_path: Path):
    caminho = tmp_path / "pedidos.sqlite3"
    lixo = b"isto nao e um banco SQLite " * 200
    caminho.write_bytes(lixo)
    fila = _fila(caminho)

    with pytest.raises(FilaCorrompida, match="danificado e não foi alterado") as erro:
        fila.listar()
    assert str(caminho) in str(erro.value)
    with pytest.raises(FilaCorrompida):
        _novo(fila)
    assert caminho.read_bytes() == lixo
