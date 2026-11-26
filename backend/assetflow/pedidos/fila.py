"""A fila de pedidos, num SQLite que a API e o servidor MCP dividem.

São dois processos — o uvicorn e o ``python -m assetflow.mcp`` que o Claude
Code sobe —, cada um com a sua fila de jobs em memória. A fila de pedidos é o
que os dois precisam ver, e por isso mora em disco (``data/pedidos/``).

As regras de acesso — conexão curta, WAL com o ``-wal`` mantido entre
conexões, ``busy_timeout``, ``synchronous=NORMAL`` — estão em
:mod:`assetflow.sqlite_curto`, que a fila divide com as lições. Duas são da
fila:

* **uma transição, uma instrução**: toda mudança de situação é um ``UPDATE``
  condicional só (``WHERE situacao = ...``), com o evento anexado na mesma
  instrução e o resultado lido pelo ``RETURNING``. Não há "ler, decidir,
  escrever" em que outro processo possa entrar no meio;
* **o arquivo nunca é apagado nem recriado**: banco travado vira
  :class:`FilaIndisponivel`; banco danificado vira :class:`FilaCorrompida`,
  com o caminho, e fica como está. Colunas novas (as da Fase B2) entram por
  ``ALTER TABLE`` ao abrir, e os pedidos antigos ficam como estavam.

Desde a Fase B2, **aprovado no validador não é pronto**: o desenho aprovado
vira candidato e o pedido vai para ``em_revisao``, à espera do olhar do Claude.
Só :meth:`FilaDePedidos.concluir` (a ferramenta ``concluir_pedido``) o leva a
``concluido``. O desenho das transições está em :mod:`.modelo`.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..sqlite_curto import BancoCurto
from .modelo import Evento, ModoConceito, Pedido, Situacao, Tipo

__all__ = [
    "ErroDaFila",
    "FilaCorrompida",
    "FilaDePedidos",
    "FilaIndisponivel",
    "PedidoNaoEncontrado",
    "TransicaoRecusada",
    "agora_utc",
    "nova_leva",
]


class ErroDaFila(Exception):
    """Algo na fila de pedidos; a mensagem é para ser lida, em português."""

    codigo = "fila_indisponivel"


class FilaIndisponivel(ErroDaFila):
    """O banco está ocupado por outro processo além do tempo de espera."""

    codigo = "fila_indisponivel"


class FilaCorrompida(ErroDaFila):
    """O arquivo não é um banco legível. Ele não é tocado."""

    codigo = "fila_corrompida"


class PedidoNaoEncontrado(ErroDaFila):
    codigo = "pedido_nao_encontrado"


class TransicaoRecusada(ErroDaFila):
    """O pedido está numa situação que não permite o que foi pedido."""

    codigo = "pedido_em_outra_situacao"

    def __init__(self, mensagem: str, pedido: Pedido) -> None:
        super().__init__(mensagem)
        self.pedido = pedido


def agora_utc() -> datetime:
    return datetime.now(UTC)


def nova_leva() -> str:
    return f"lev_{secrets.token_hex(6)}"


def _carimbo(momento: datetime) -> str:
    """Sempre o mesmo formato e fuso: comparar como texto é comparar no tempo."""
    return momento.astimezone(UTC).isoformat(timespec="microseconds")


_ATIVAS = ("pendente", "em_desenho", "em_revisao")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS pedidos (
    id               TEXT PRIMARY KEY,
    tipo             TEXT NOT NULL,
    situacao         TEXT NOT NULL,
    projeto          TEXT NOT NULL,
    texto            TEXT NOT NULL,
    liberdade        TEXT NOT NULL,
    direcao_de_arte  TEXT,
    corpo            TEXT NOT NULL,
    leitura          TEXT NOT NULL,
    origem_asset_id  TEXT,
    asset_id         TEXT,
    job_id           TEXT,
    asset_projeto    TEXT,
    tentativas       INTEGER NOT NULL DEFAULT 0,
    max_tentativas   INTEGER NOT NULL,
    ultimo_laudo     TEXT,
    leva             TEXT,
    reservado_ate    TEXT,
    desenhando_desde TEXT,
    motivo           TEXT,
    eventos          TEXT NOT NULL DEFAULT '[]',
    criado_em        TEXT NOT NULL,
    atualizado_em    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS pedidos_por_situacao ON pedidos (situacao, criado_em);
CREATE INDEX IF NOT EXISTS pedidos_por_projeto ON pedidos (projeto, criado_em);
CREATE INDEX IF NOT EXISTS pedidos_por_leva ON pedidos (leva);
"""


#: Colunas da Fase B2, acrescentadas a um arquivo de antes dela ao abrir.
_COLUNAS_NOVAS = {
    "pedidos": (
        # Remendos pedidos pelo olhar depois de um desenho aprovado, e o teto.
        ("remendos", "INTEGER NOT NULL DEFAULT 0"),
        ("max_remendos", "INTEGER NOT NULL DEFAULT 2"),
        # 1 enquanto um desenho começado com candidato (um remendo) roda.
        ("remendando", "INTEGER NOT NULL DEFAULT 0"),
        # Os desenhos aprovados do pedido: [{asset_id, job_id, asset_projeto}].
        ("candidatos", "TEXT NOT NULL DEFAULT '[]'"),
        # A linha do olhar que concluiu o pedido.
        ("olhar", "TEXT"),
        # O que foi entregue ao Claude com o pedido: exemplo, lições, interruptores.
        ("envio", "TEXT"),
        # Lote 1: a etapa de conceito, a banca e o custo.
        ("modo_conceito", "TEXT NOT NULL DEFAULT 'sem_conceito'"),
        ("conceitos", "TEXT NOT NULL DEFAULT '[]'"),
        ("conceitos_recusados", "TEXT NOT NULL DEFAULT '[]'"),
        ("conceito", "TEXT"),
        ("motivo_conceito", "TEXT"),
        ("banca", "TEXT"),
        ("custo", "TEXT NOT NULL DEFAULT '{}'"),
    ),
}

#: Pedido que precisa de conceito e ainda não tem: ``desenhar`` é recusado.
_SEM_CONCEITO_PRONTO = "(modo_conceito != 'sem_conceito' AND conceito IS NULL)"

#: Pedidos que um pedidos_pendentes pode pegar: pendentes e reservas vencidas.
_LIVRE = (
    "situacao = 'pendente' OR (situacao IN ('em_desenho', 'em_revisao') "
    "AND reservado_ate < :agora)"
)


def _evento(situacao_sql: str) -> str:
    """O trecho que anexa um evento, na mesma instrução da transição.

    ``situacao_sql`` é uma expressão SQL — às vezes um ``CASE``: numa
    instrução ``UPDATE`` o SQLite avalia tudo com os valores antigos, então o
    evento registra exatamente a situação que a mesma instrução grava.
    """
    return (
        "eventos = json_insert(eventos, '$[#]', json_object("
        f"'em', :agora, 'situacao', {situacao_sql}, 'nota', :nota))"
    )


class FilaDePedidos:
    """Operações sobre o arquivo da fila. Cada uma abre e fecha a conexão."""

    def __init__(
        self,
        caminho: Path,
        *,
        espera_s: float = 5.0,
        max_tentativas: int = 3,
        max_remendos: int = 2,
        reserva: timedelta = timedelta(minutes=30),
    ) -> None:
        self._caminho = Path(caminho)
        self._espera_s = float(espera_s)
        self._max_tentativas = int(max_tentativas)
        self._max_remendos = int(max_remendos)
        self._reserva = reserva
        self._banco = BancoCurto(
            self._caminho,
            esquema=_ESQUEMA,
            traduzir=self._traduzir,
            espera_s=self._espera_s,
            colunas_novas=_COLUNAS_NOVAS,
        )

    @property
    def caminho(self) -> Path:
        return self._caminho

    @property
    def reserva(self) -> timedelta:
        return self._reserva

    @property
    def max_tentativas(self) -> int:
        return self._max_tentativas

    @property
    def max_remendos(self) -> int:
        return self._max_remendos

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------
    @contextmanager
    def _conexao(self) -> Iterator[sqlite3.Connection]:
        with self._banco.conexao() as conexao:
            yield conexao

    def _traduzir(self, exc: Exception) -> ErroDaFila:
        texto = str(exc).lower()
        if isinstance(exc, sqlite3.OperationalError) and ("locked" in texto or "busy" in texto):
            return FilaIndisponivel(
                f"a fila de pedidos está ocupada por outro processo há mais de "
                f"{self._espera_s:g} s; tente de novo em instantes ({self._caminho})"
            )
        if isinstance(exc, sqlite3.DatabaseError) and (
            "not a database" in texto or "malformed" in texto or "corrupt" in texto
        ):
            return FilaCorrompida(
                f"o arquivo da fila de pedidos está danificado e não foi alterado: "
                f"{self._caminho}. Feche a API e o servidor MCP, guarde uma cópia "
                "dele (com os arquivos -wal e -shm ao lado, se houver) e tire os três "
                "do lugar para o AssetFlow começar uma fila nova; os assets já "
                "desenhados continuam no histórico."
            )
        return ErroDaFila(f"a fila de pedidos não respondeu ({self._caminho}): {exc}")

    # ------------------------------------------------------------------
    # Criar e ler
    # ------------------------------------------------------------------
    def criar(
        self,
        *,
        tipo: Tipo,
        projeto: str,
        texto: str,
        liberdade: str,
        direcao_de_arte: str | None,
        corpo: dict[str, Any],
        leitura: dict[str, Any],
        origem_asset_id: str | None = None,
        modo_conceito: ModoConceito | str = ModoConceito.SEM_CONCEITO,
        banca: dict[str, Any] | None = None,
        agora: datetime | None = None,
    ) -> Pedido:
        momento = _carimbo(agora or agora_utc())
        evento = json.dumps(
            [{"em": momento, "situacao": Situacao.PENDENTE.value, "nota": "pedido feito na tela"}],
            ensure_ascii=False,
        )
        with self._conexao() as conexao:
            linha = conexao.execute(
                """
                INSERT INTO pedidos (
                    id, tipo, situacao, projeto, texto, liberdade, direcao_de_arte,
                    corpo, leitura, origem_asset_id, max_tentativas, max_remendos,
                    modo_conceito, banca, eventos, criado_em, atualizado_em
                ) VALUES (?, ?, 'pendente', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING *
                """,
                (
                    f"ped_{secrets.token_hex(6)}",
                    Tipo(tipo).value,
                    projeto,
                    texto,
                    liberdade,
                    direcao_de_arte or None,
                    json.dumps(corpo, ensure_ascii=False),
                    json.dumps(leitura, ensure_ascii=False),
                    origem_asset_id,
                    self._max_tentativas,
                    self._max_remendos,
                    ModoConceito(modo_conceito).value,
                    json.dumps(banca, ensure_ascii=False) if banca else None,
                    evento,
                    momento,
                    momento,
                ),
            ).fetchall()[0]
        return _pedido(linha)

    def registrar_edicao(
        self,
        *,
        projeto: str,
        texto: str,
        corpo: dict[str, Any],
        leitura: dict[str, Any],
        origem_asset_id: str,
        asset_id: str,
        job_id: str,
        asset_projeto: str,
        olhar: str,
        agora: datetime | None = None,
    ) -> Pedido:
        """A edição da autora no editor de pixels (lote 5), já concluída.

        É uma criação, não uma transição: um ``INSERT`` só, com o desenho como
        candidato e o pedido pronto. Nenhum estado intermediário fica visível
        a quem pega pedidos pendentes.
        """
        momento = _carimbo(agora or agora_utc())
        evento = json.dumps(
            [{"em": momento, "situacao": Situacao.CONCLUIDO.value, "nota": f"editado na tela: {asset_id}"}],
            ensure_ascii=False,
        )
        candidato = json.dumps(
            [{"asset_id": asset_id, "job_id": job_id, "asset_projeto": asset_projeto}]
        )
        with self._conexao() as conexao:
            linha = conexao.execute(
                """
                INSERT INTO pedidos (
                    id, tipo, situacao, projeto, texto, liberdade, direcao_de_arte,
                    corpo, leitura, origem_asset_id, max_tentativas, max_remendos,
                    modo_conceito, asset_id, job_id, asset_projeto, olhar, candidatos,
                    eventos, criado_em, atualizado_em
                ) VALUES (?, 'ajuste', 'concluido', ?, ?, 'fiel', NULL, ?, ?, ?, ?, ?,
                          'sem_conceito', ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING *
                """,
                (
                    f"ped_{secrets.token_hex(6)}",
                    projeto,
                    texto,
                    json.dumps(corpo, ensure_ascii=False),
                    json.dumps(leitura, ensure_ascii=False),
                    origem_asset_id,
                    self._max_tentativas,
                    self._max_remendos,
                    asset_id,
                    job_id,
                    asset_projeto,
                    olhar,
                    candidato,
                    evento,
                    momento,
                    momento,
                ),
            ).fetchall()[0]
        return _pedido(linha)

    def obter(self, pedido_id: str) -> Pedido:
        with self._conexao() as conexao:
            linha = conexao.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
        if linha is None:
            raise PedidoNaoEncontrado(f"não há pedido '{pedido_id}' na fila")
        return _pedido(linha)

    def listar(
        self,
        *,
        projeto: str | Sequence[str] | None = None,
        situacoes: Sequence[Situacao] = (),
        limite: int = 30,
    ) -> list[Pedido]:
        """Do mais novo para o mais antigo. ``projeto`` aceita um ou vários."""
        condicoes, valores = [], []
        if projeto is not None:
            projetos = [projeto] if isinstance(projeto, str) else list(projeto)
            condicoes.append(f"projeto IN ({', '.join('?' * len(projetos))})")
            valores.extend(projetos)
        if situacoes:
            condicoes.append(f"situacao IN ({', '.join('?' * len(situacoes))})")
            valores.extend(Situacao(s).value for s in situacoes)
        onde = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
        with self._conexao() as conexao:
            linhas = conexao.execute(
                f"SELECT * FROM pedidos {onde} ORDER BY criado_em DESC LIMIT ?",
                (*valores, max(1, int(limite))),
            ).fetchall()
        return [_pedido(linha) for linha in linhas]

    def candidatos(self, limite: int, agora: datetime | None = None) -> list[Pedido]:
        """Os que esperam desenho ou olhar, dos mais antigos: pendentes e reservas vencidas."""
        with self._conexao() as conexao:
            linhas = conexao.execute(
                f"""
                SELECT * FROM pedidos
                WHERE {_LIVRE}
                ORDER BY criado_em ASC LIMIT :limite
                """,
                {"agora": _carimbo(agora or agora_utc()), "limite": max(1, int(limite))},
            ).fetchall()
        return [_pedido(linha) for linha in linhas]

    def contar_na_fila(self, agora: datetime | None = None) -> int:
        with self._conexao() as conexao:
            (quantos,) = conexao.execute(
                f"SELECT count(*) FROM pedidos WHERE {_LIVRE}",
                {"agora": _carimbo(agora or agora_utc())},
            ).fetchone()
        return int(quantos)

    # ------------------------------------------------------------------
    # Transições — cada uma, um UPDATE condicional
    # ------------------------------------------------------------------
    def reservar(
        self, ids: Sequence[str], leva: str, agora: datetime | None = None
    ) -> list[Pedido]:
        """Reserva os que ainda estiverem livres; devolve só os reservados agora.

        Um pedido que já tem desenho aprovado (candidato) volta reservado em
        ``em_revisao``: falta o olhar, não um desenho novo.
        """
        if not ids:
            return []
        momento = agora or agora_utc()
        marcadores = ", ".join(f":id{i}" for i in range(len(ids)))
        valores: dict[str, Any] = {f"id{i}": pedido_id for i, pedido_id in enumerate(ids)}
        valores.update(
            agora=_carimbo(momento),
            ate=_carimbo(momento + self._reserva),
            leva=leva,
            nota="reservado por pedidos_pendentes",
        )
        nova = "CASE WHEN candidatos != '[]' THEN 'em_revisao' ELSE 'em_desenho' END"
        with self._conexao() as conexao:
            linhas = conexao.execute(
                f"""
                UPDATE pedidos SET
                    situacao = {nova}, leva = :leva, reservado_ate = :ate,
                    desenhando_desde = NULL, remendando = 0, atualizado_em = :agora,
                    {_evento(nova)}
                WHERE id IN ({marcadores}) AND ({_LIVRE})
                RETURNING *
                """,
                valores,
            ).fetchall()
        reservados = [_pedido(linha) for linha in linhas]
        return sorted(reservados, key=lambda pedido: pedido.criado_em)

    def gravar_envio(self, pedido_id: str, envio: dict[str, Any]) -> None:
        """Guarda o que foi entregue ao Claude com o pedido (exemplo, lições)."""
        with self._conexao() as conexao:
            conexao.execute(
                "UPDATE pedidos SET envio = :envio WHERE id = :id",
                {"id": pedido_id, "envio": json.dumps(envio, ensure_ascii=False)},
            ).fetchall()

    def iniciar(self, pedido_id: str, agora: datetime | None = None) -> Pedido:
        """Um ``desenhar(pedido_id)`` começou: marca e renova a leva inteira.

        Aceita pedido pendente (por exemplo, devolvido à fila), em desenho ou
        em revisão; recusa concluído, falho e cancelado. Com candidato, o
        desenho é um **remendo do olhar** — e é recusado quando os remendos do
        pedido acabaram.
        """
        momento = agora or agora_utc()
        valores = {
            "id": pedido_id,
            "agora": _carimbo(momento),
            "ate": _carimbo(momento + self._reserva),
            "leva": nova_leva(),
            "nota": "desenho começou",
        }
        with self._conexao() as conexao:
            linha = conexao.execute(
                f"""
                UPDATE pedidos SET
                    situacao = 'em_desenho', desenhando_desde = :agora,
                    remendando = CASE WHEN candidatos != '[]' THEN 1 ELSE 0 END,
                    reservado_ate = :ate, leva = COALESCE(leva, :leva),
                    atualizado_em = :agora, {_evento("'em_desenho'")}
                WHERE id = :id AND situacao IN ('pendente', 'em_desenho', 'em_revisao')
                  AND (candidatos = '[]' OR remendos < max_remendos)
                  AND NOT {_SEM_CONCEITO_PRONTO}
                RETURNING *
                """,
                valores,
            ).fetchall()
            linha = linha[0] if linha else None
            if linha is not None:
                # A leva inteira ganha prazo novo: quem está desenhando um
                # pedido ainda vai desenhar os outros que pegou junto.
                conexao.execute(
                    """
                    UPDATE pedidos SET reservado_ate = :ate
                    WHERE leva = :leva AND situacao IN ('em_desenho', 'em_revisao')
                      AND id != :id
                    """,
                    {"ate": valores["ate"], "leva": linha["leva"], "id": pedido_id},
                )
        if linha is None:
            atual = self.obter(pedido_id)
            raise TransicaoRecusada(_por_que_nao_desenha(atual), atual)
        return _pedido(linha)

    def aprovar(
        self,
        pedido_id: str,
        *,
        asset_id: str,
        job_id: str,
        asset_projeto: str,
        laudo: str,
        agora: datetime | None = None,
    ) -> Pedido | None:
        """Aprovado no validador: vira candidato, e o pedido espera o olhar.

        Não conclui (Fase B2). Um remendo aprovado conta um remendo. ``None``
        se o pedido não estiver mais em desenho (cancelado ou devolvido).
        """
        return self._uma(
            f"""
            UPDATE pedidos SET
                situacao = 'em_revisao', asset_id = :asset, job_id = :job,
                asset_projeto = :projeto, ultimo_laudo = :laudo, motivo = NULL,
                candidatos = json_insert(candidatos, '$[#]', json_object(
                    'asset_id', :asset, 'job_id', :job, 'asset_projeto', :projeto)),
                remendos = remendos + remendando, remendando = 0,
                desenhando_desde = NULL,
                atualizado_em = :agora, {_evento("'em_revisao'")}
            WHERE id = :id AND situacao = 'em_desenho'
            RETURNING *
            """,
            {
                "id": pedido_id,
                "asset": asset_id,
                "job": job_id,
                "projeto": asset_projeto,
                "laudo": laudo,
                "agora": _carimbo(agora or agora_utc()),
                "nota": f"aprovado no validador, esperando o olhar: {asset_id}",
            },
        )

    def concluir(
        self,
        pedido_id: str,
        *,
        olhar: str,
        asset_id: str | None = None,
        agora: datetime | None = None,
    ) -> Pedido:
        """O olhar terminou: conclui com um dos desenhos aprovados do pedido.

        Sem ``asset_id``, vale o último aprovado. Com ele, só um candidato do
        próprio pedido — um remendo que piorou o desenho não obriga a ficar
        com ele.
        """
        escolhido = (
            "(SELECT value FROM json_each(pedidos.candidatos) "
            "WHERE json_extract(value, '$.asset_id') = COALESCE(:asset, pedidos.asset_id))"
        )
        linha = self._uma(
            f"""
            UPDATE pedidos SET
                situacao = 'concluido', olhar = :olhar, motivo = NULL,
                asset_id = json_extract({escolhido}, '$.asset_id'),
                job_id = json_extract({escolhido}, '$.job_id'),
                asset_projeto = json_extract({escolhido}, '$.asset_projeto'),
                leva = NULL, desenhando_desde = NULL, reservado_ate = NULL,
                atualizado_em = :agora, {_evento("'concluido'")}
            WHERE id = :id AND situacao = 'em_revisao' AND {escolhido} IS NOT NULL
            RETURNING *
            """,
            {
                "id": pedido_id,
                "asset": asset_id,
                "olhar": olhar,
                "agora": _carimbo(agora or agora_utc()),
                "nota": f"concluído depois do olhar: {olhar}",
            },
        )
        if linha is None:
            atual = self.obter(pedido_id)
            raise TransicaoRecusada(_por_que_nao_conclui(atual, asset_id), atual)
        return linha

    def reprovar(
        self,
        pedido_id: str,
        *,
        asset_id: str,
        job_id: str,
        asset_projeto: str,
        laudo: str,
        agora: datetime | None = None,
        motivo: str | None = None,
    ) -> Pedido | None:
        """Não aprovado: conta a tentativa; no teto, o pedido vai para ``falhou``.

        Um **remendo** não aprovado é diferente: conta um remendo e o pedido
        volta para ``em_revisao`` com o candidato de antes, que continua
        valendo. ``motivo`` (como "repete o exemplo") vai para o pedido.
        """
        nova = (
            "CASE WHEN remendando = 1 THEN 'em_revisao' "
            "WHEN tentativas + 1 >= max_tentativas THEN 'falhou' ELSE 'em_desenho' END"
        )
        no_teto = "remendando = 0 AND tentativas + 1 >= max_tentativas"
        return self._uma(
            f"""
            UPDATE pedidos SET
                tentativas = tentativas + (1 - remendando),
                remendos = remendos + remendando,
                situacao = {nova},
                asset_id = CASE WHEN remendando = 1 THEN asset_id ELSE :asset END,
                job_id = CASE WHEN remendando = 1 THEN job_id ELSE :job END,
                asset_projeto = CASE WHEN remendando = 1 THEN asset_projeto ELSE :projeto END,
                ultimo_laudo = :laudo, desenhando_desde = NULL, remendando = 0,
                motivo = CASE WHEN {no_teto}
                    THEN 'não aprovado em ' || max_tentativas || ' tentativas'
                    ELSE COALESCE(:motivo, motivo) END,
                reservado_ate = CASE WHEN {no_teto} THEN NULL ELSE reservado_ate END,
                atualizado_em = :agora, {_evento(nova)}
            WHERE id = :id AND situacao = 'em_desenho'
            RETURNING *
            """,
            {
                "id": pedido_id,
                "asset": asset_id,
                "job": job_id,
                "projeto": asset_projeto,
                "laudo": laudo,
                "motivo": motivo,
                "agora": _carimbo(agora or agora_utc()),
                "nota": f"não aprovado: {asset_id}" + (f" ({motivo})" if motivo else ""),
            },
        )

    def desenho_interrompido(
        self, pedido_id: str, *, nota: str, agora: datetime | None = None
    ) -> Pedido | None:
        """O desenho não produziu asset (receita recusada, erro): só limpa a marca.

        Um remendo interrompido volta para ``em_revisao`` sem gastar remendo.
        """
        volta = "CASE WHEN remendando = 1 THEN 'em_revisao' ELSE situacao END"
        return self._uma(
            f"""
            UPDATE pedidos SET
                situacao = {volta}, desenhando_desde = NULL, remendando = 0,
                atualizado_em = :agora, {_evento(volta)}
            WHERE id = :id AND situacao = 'em_desenho'
            RETURNING *
            """,
            {"id": pedido_id, "agora": _carimbo(agora or agora_utc()), "nota": nota},
        )

    def cancelar(self, pedido_id: str, agora: datetime | None = None) -> Pedido:
        linha = self._uma(
            f"""
            UPDATE pedidos SET
                situacao = 'cancelado', motivo = 'cancelado na tela',
                leva = NULL, reservado_ate = NULL, desenhando_desde = NULL,
                remendando = 0, atualizado_em = :agora, {_evento("'cancelado'")}
            WHERE id = :id AND situacao IN ('pendente', 'em_desenho', 'em_revisao', 'escolhendo')
            RETURNING *
            """,
            {"id": pedido_id, "agora": _carimbo(agora or agora_utc()), "nota": "cancelado na tela"},
        )
        if linha is None:
            atual = self.obter(pedido_id)
            raise TransicaoRecusada(
                f"o pedido {pedido_id} já está {_situacao_lida(atual)}: não há o que cancelar",
                atual,
            )
        return linha

    def devolver(self, pedido_id: str, agora: datetime | None = None) -> Pedido:
        """Tira a reserva e volta para ``pendente``, sem cancelar nem zerar tentativas.

        Os candidatos ficam: quem pegar o pedido de novo só precisa olhar.
        """
        linha = self._uma(
            f"""
            UPDATE pedidos SET
                situacao = 'pendente', leva = NULL, reservado_ate = NULL,
                desenhando_desde = NULL, remendando = 0, atualizado_em = :agora,
                {_evento("'pendente'")}
            WHERE id = :id AND situacao IN ('em_desenho', 'em_revisao')
            RETURNING *
            """,
            {"id": pedido_id, "agora": _carimbo(agora or agora_utc()), "nota": "devolvido à fila na tela"},
        )
        if linha is None:
            atual = self.obter(pedido_id)
            raise TransicaoRecusada(
                f"o pedido {pedido_id} está {_situacao_lida(atual)}: só um pedido em "
                "desenho ou em revisão volta para a fila",
                atual,
            )
        return linha

    # ------------------------------------------------------------------
    # Etapa de conceito (lote 1)
    # ------------------------------------------------------------------
    def gravar_conceitos(
        self,
        pedido_id: str,
        conceitos: Sequence[dict[str, Any]],
        *,
        escolhido: dict[str, Any] | None = None,
        motivo: str | None = None,
        direcao: str | None = None,
        agora: datetime | None = None,
    ) -> Pedido:
        """Os três conceitos do Claude.

        Sem ``escolhido`` (modo ``eu_escolho``), o pedido vai para
        ``escolhendo`` e sai da reserva: espera a autora. Com ele (modo
        ``claude_escolhe``), o conceito fica escolhido, vira a direção de
        arte, e o pedido segue em desenho, na mesma reserva.
        """
        momento = agora or agora_utc()
        valores = {
            "id": pedido_id,
            "conceitos": json.dumps(list(conceitos), ensure_ascii=False),
            "agora": _carimbo(momento),
        }
        if escolhido is None:
            sql = f"""
                UPDATE pedidos SET
                    situacao = 'escolhendo', conceitos = :conceitos, leva = NULL,
                    reservado_ate = NULL, desenhando_desde = NULL,
                    atualizado_em = :agora, {_evento("'escolhendo'")}
                WHERE id = :id AND situacao IN ('pendente', 'em_desenho')
                  AND modo_conceito = 'eu_escolho' AND conceito IS NULL
                RETURNING *
            """
            valores["nota"] = "três conceitos propostos; esperando a escolha"
        else:
            sql = f"""
                UPDATE pedidos SET
                    situacao = 'em_desenho', conceitos = :conceitos, conceito = :escolhido,
                    motivo_conceito = :motivo, direcao_de_arte = :direcao,
                    atualizado_em = :agora, {_evento("'em_desenho'")}
                WHERE id = :id AND situacao IN ('pendente', 'em_desenho')
                  AND modo_conceito = 'claude_escolhe' AND conceito IS NULL
                RETURNING *
            """
            valores.update(
                escolhido=json.dumps(escolhido, ensure_ascii=False),
                motivo=motivo,
                direcao=direcao,
                nota=f"conceito escolhido pelo Claude: {motivo or ''}".strip(),
            )
        linha = self._uma(sql, valores)
        if linha is None:
            atual = self.obter(pedido_id)
            raise TransicaoRecusada(_por_que_nao_conceitua(atual, escolhido is not None), atual)
        return linha

    def escolher_conceito(
        self,
        pedido_id: str,
        conceito: dict[str, Any],
        *,
        direcao: str,
        agora: datetime | None = None,
    ) -> Pedido:
        """A autora escolheu (e talvez editou) um conceito: o pedido volta à fila."""
        linha = self._uma(
            f"""
            UPDATE pedidos SET
                situacao = 'pendente', conceito = :conceito, direcao_de_arte = :direcao,
                atualizado_em = :agora, {_evento("'pendente'")}
            WHERE id = :id AND situacao = 'escolhendo'
            RETURNING *
            """,
            {
                "id": pedido_id,
                "conceito": json.dumps(conceito, ensure_ascii=False),
                "direcao": direcao,
                "agora": _carimbo(agora or agora_utc()),
                "nota": "conceito escolhido na tela",
            },
        )
        if linha is None:
            atual = self.obter(pedido_id)
            raise TransicaoRecusada(
                f"o pedido {pedido_id} está {_situacao_lida(atual)}: só se escolhe conceito "
                "de um pedido com três conceitos propostos",
                atual,
            )
        return linha

    def outros_conceitos(self, pedido_id: str, agora: datetime | None = None) -> Pedido:
        """A autora pediu outros três: os propostos vão para os recusados."""
        linha = self._uma(
            f"""
            UPDATE pedidos SET
                situacao = 'pendente',
                conceitos_recusados = (
                    SELECT json_group_array(json(value)) FROM (
                        SELECT value FROM json_each(pedidos.conceitos_recusados)
                        UNION ALL
                        SELECT value FROM json_each(pedidos.conceitos))),
                conceitos = '[]', atualizado_em = :agora, {_evento("'pendente'")}
            WHERE id = :id AND situacao = 'escolhendo'
            RETURNING *
            """,
            {"id": pedido_id, "agora": _carimbo(agora or agora_utc()), "nota": "outros três conceitos pedidos"},
        )
        if linha is None:
            atual = self.obter(pedido_id)
            raise TransicaoRecusada(
                f"o pedido {pedido_id} está {_situacao_lida(atual)}: não há conceitos para trocar",
                atual,
            )
        return linha

    def somar_custo(
        self,
        pedido_id: str,
        *,
        entrada: int = 0,
        saida_texto: int = 0,
        saida_receita: int = 0,
        imagens: int = 0,
    ) -> None:
        """Soma o que passou pela conversa por este pedido (caracteres e imagens)."""
        with self._conexao() as conexao:
            conexao.execute(
                """
                UPDATE pedidos SET custo = json_object(
                    'entrada', COALESCE(json_extract(custo, '$.entrada'), 0) + :entrada,
                    'saida_texto', COALESCE(json_extract(custo, '$.saida_texto'), 0) + :texto,
                    'saida_receita', COALESCE(json_extract(custo, '$.saida_receita'), 0) + :receita,
                    'imagens', COALESCE(json_extract(custo, '$.imagens'), 0) + :imagens)
                WHERE id = :id
                """,
                {
                    "id": pedido_id,
                    "entrada": int(entrada),
                    "texto": int(saida_texto),
                    "receita": int(saida_receita),
                    "imagens": int(imagens),
                },
            ).fetchall()

    def _uma(self, sql: str, valores: dict[str, Any]) -> Pedido | None:
        # fetchall: a instrução vai até o fim e confirma antes de a conexão fechar.
        with self._conexao() as conexao:
            linhas = conexao.execute(sql, valores).fetchall()
        return _pedido(linhas[0]) if linhas else None


def _situacao_lida(pedido: Pedido) -> str:
    return {
        Situacao.PENDENTE: "na fila",
        Situacao.EM_DESENHO: "em desenho",
        Situacao.EM_REVISAO: "esperando o olhar",
        Situacao.ESCOLHENDO: "esperando a escolha do conceito",
        Situacao.CONCLUIDO: "concluído",
        Situacao.FALHOU: "falho",
        Situacao.CANCELADO: "cancelado",
    }[pedido.situacao]


def _por_que_nao_desenha(pedido: Pedido) -> str:
    if pedido.situacao is Situacao.CANCELADO:
        return f"o pedido {pedido.id} foi cancelado na tela: não desenhe"
    if pedido.situacao is Situacao.CONCLUIDO:
        return (
            f"o pedido {pedido.id} já foi concluído com {pedido.asset_id}: para mudar o "
            f"desenho, use base={pedido.asset_id} sem pedido_id (vira um asset avulso) "
            "ou peça um ajuste na tela"
        )
    if pedido.precisa_conceito and pedido.situacao is Situacao.ESCOLHENDO:
        return (
            f"o pedido {pedido.id} espera a autora escolher um dos três conceitos na tela: "
            "não desenhe agora"
        )
    if pedido.precisa_conceito:
        return (
            f"o pedido {pedido.id} precisa de conceito antes do desenho: proponha três com "
            f"propor_conceitos(pedido_id={pedido.id}, conceitos=[...])"
        )
    if pedido.candidatos and pedido.remendos >= pedido.max_remendos:
        return (
            f"o pedido {pedido.id} já usou os {pedido.max_remendos} remendos do olhar: "
            f"conclua com concluir_pedido(pedido_id={pedido.id}, olhar=\"<a linha>\")"
            + (", escolhendo asset_id entre " + ", ".join(pedido.candidatos) if len(pedido.candidatos) > 1 else "")
        )
    return (
        f"o pedido {pedido.id} terminou sem aprovação ({pedido.motivo or 'falhou'}): "
        "faça outro pedido na tela para tentar de novo"
    )


def _por_que_nao_conclui(pedido: Pedido, asset_id: str | None) -> str:
    if pedido.situacao is Situacao.EM_REVISAO and asset_id:
        return (
            f"{asset_id} não é um desenho aprovado do pedido {pedido.id}: escolha entre "
            + ", ".join(pedido.candidatos)
        )
    if pedido.situacao is Situacao.EM_DESENHO:
        return (
            f"o pedido {pedido.id} ainda não tem desenho aprovado esperando o olhar: "
            f"desenhe com desenhar(pedido_id={pedido.id}, ...)"
        )
    if pedido.situacao is Situacao.PENDENTE:
        return (
            f"o pedido {pedido.id} está na fila, sem reserva: pegue-o com pedidos_pendentes "
            "antes de concluir"
        )
    return f"o pedido {pedido.id} já está {_situacao_lida(pedido)}: não há o que concluir"


def _por_que_nao_conceitua(pedido: Pedido, com_escolha: bool) -> str:
    if pedido.modo_conceito is ModoConceito.SEM_CONCEITO:
        return f"o pedido {pedido.id} é sem conceito: desenhe direto"
    if pedido.conceito is not None:
        return f"o pedido {pedido.id} já tem conceito escolhido: desenhe"
    if pedido.situacao is Situacao.ESCOLHENDO:
        return f"o pedido {pedido.id} já tem três conceitos esperando a escolha da autora"
    if pedido.modo_conceito is ModoConceito.EU_ESCOLHO and com_escolha:
        return (
            f"no pedido {pedido.id} quem escolhe é a autora (modo eu_escolho): mande os três "
            "sem 'escolhido' nem 'motivo'"
        )
    if pedido.modo_conceito is ModoConceito.CLAUDE_ESCOLHE and not com_escolha:
        return (
            f"no pedido {pedido.id} quem escolhe é você (modo claude_escolhe): mande "
            "'escolhido' (1 a 3) e 'motivo'"
        )
    return f"o pedido {pedido.id} está {_situacao_lida(pedido)}: não recebe conceitos agora"


def _momento(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


def _pedido(linha: sqlite3.Row) -> Pedido:
    dados = dict(linha)
    return Pedido(
        id=dados["id"],
        tipo=Tipo(dados["tipo"]),
        situacao=Situacao(dados["situacao"]),
        projeto=dados["projeto"],
        texto=dados["texto"],
        liberdade=dados["liberdade"],
        direcao_de_arte=dados["direcao_de_arte"],
        corpo=json.loads(dados["corpo"]),
        leitura=json.loads(dados["leitura"]),
        origem_asset_id=dados["origem_asset_id"],
        asset_id=dados["asset_id"],
        job_id=dados["job_id"],
        asset_projeto=dados["asset_projeto"],
        tentativas=int(dados["tentativas"]),
        max_tentativas=int(dados["max_tentativas"]),
        remendos=int(dados.get("remendos") or 0),
        max_remendos=int(dados.get("max_remendos") or 0),
        remendando=bool(dados.get("remendando")),
        candidatos=tuple(
            str(c["asset_id"]) for c in json.loads(dados.get("candidatos") or "[]")
        ),
        olhar=dados.get("olhar"),
        envio=json.loads(dados["envio"]) if dados.get("envio") else None,
        modo_conceito=ModoConceito(dados.get("modo_conceito") or "sem_conceito"),
        conceitos=tuple(json.loads(dados.get("conceitos") or "[]")),
        conceitos_recusados=tuple(json.loads(dados.get("conceitos_recusados") or "[]")),
        conceito=json.loads(dados["conceito"]) if dados.get("conceito") else None,
        motivo_conceito=dados.get("motivo_conceito"),
        banca=json.loads(dados["banca"]) if dados.get("banca") else None,
        custo=json.loads(dados.get("custo") or "{}"),
        ultimo_laudo=dados["ultimo_laudo"],
        leva=dados["leva"],
        reservado_ate=_momento(dados["reservado_ate"]),
        desenhando_desde=_momento(dados["desenhando_desde"]),
        motivo=dados["motivo"],
        eventos=tuple(Evento.model_validate(e) for e in json.loads(dados["eventos"] or "[]")),
        criado_em=datetime.fromisoformat(dados["criado_em"]),
        atualizado_em=datetime.fromisoformat(dados["atualizado_em"]),
    )
