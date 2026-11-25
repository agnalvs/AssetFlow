"""A fila de pedidos, num SQLite que a API e o servidor MCP dividem.

São dois processos — o uvicorn e o ``python -m assetflow.mcp`` que o Claude
Code sobe —, cada um com a sua fila de jobs em memória. A fila de pedidos é o
que os dois precisam ver, e por isso mora em disco (``data/pedidos/``).

Quatro regras de acesso, todas por causa de haver dois processos:

* **conexão curta**: cada operação abre, faz e fecha. Nenhum processo segura
  o arquivo entre uma chamada e outra;
* **WAL e ``busy_timeout``**: leitores não esperam escritores, e um escritor
  espera o outro por ``espera_s`` antes de desistir com erro. Com conexão
  curta, cada fechamento seria o último, e o SQLite faria checkpoint e
  apagaria o ``-wal`` a cada operação — 130 ms por escrita no Windows, contra
  7 ms mantendo-o (``SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE``). O checkpoint segue
  automático, a cada 1000 páginas. Por isso a fila são três arquivos
  (``.sqlite3``, ``-wal``, ``-shm``), e uma cópia de segurança leva os três.
  ``synchronous=NORMAL``, o par recomendado do WAL: o banco não corrompe se um
  processo cair; uma queda de energia perde no máximo a última transação;
* **uma transição, uma instrução**: toda mudança de situação é um ``UPDATE``
  condicional só (``WHERE situacao = ...``), com o evento anexado na mesma
  instrução e o resultado lido pelo ``RETURNING``. Não há "ler, decidir,
  escrever" em que outro processo possa entrar no meio;
* **o arquivo nunca é apagado nem recriado**: banco travado vira
  :class:`FilaIndisponivel`; banco danificado vira :class:`FilaCorrompida`,
  com o caminho, e fica como está.
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

from .modelo import Evento, Pedido, Situacao, Tipo

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


_ATIVAS = ("pendente", "em_desenho")

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
        reserva: timedelta = timedelta(minutes=30),
    ) -> None:
        self._caminho = Path(caminho)
        self._espera_s = float(espera_s)
        self._max_tentativas = int(max_tentativas)
        self._reserva = reserva
        self._preparada = False

    @property
    def caminho(self) -> Path:
        return self._caminho

    @property
    def reserva(self) -> timedelta:
        return self._reserva

    @property
    def max_tentativas(self) -> int:
        return self._max_tentativas

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------
    @contextmanager
    def _conexao(self) -> Iterator[sqlite3.Connection]:
        try:
            self._caminho.parent.mkdir(parents=True, exist_ok=True)
            conexao = sqlite3.connect(
                self._caminho, timeout=self._espera_s, isolation_level=None
            )
        except (OSError, sqlite3.Error) as exc:
            raise self._traduzir(exc) from exc
        try:
            conexao.row_factory = sqlite3.Row
            # O -wal fica entre conexões (ver o topo do módulo).
            conexao.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
            conexao.execute(f"PRAGMA busy_timeout = {int(self._espera_s * 1000)}")
            conexao.execute("PRAGMA synchronous = NORMAL")
            if not self._preparada:
                self._preparar(conexao)
            yield conexao
        except sqlite3.Error as exc:
            raise self._traduzir(exc) from exc
        finally:
            conexao.close()

    def _preparar(self, conexao: sqlite3.Connection) -> None:
        # WAL é persistente no arquivo; pedir de novo é barato e idempotente.
        conexao.execute("PRAGMA journal_mode = WAL")
        conexao.executescript(_ESQUEMA)
        self._preparada = True

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
                    corpo, leitura, origem_asset_id, max_tentativas, eventos,
                    criado_em, atualizado_em
                ) VALUES (?, ?, 'pendente', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        projeto: str | None = None,
        situacoes: Sequence[Situacao] = (),
        limite: int = 30,
    ) -> list[Pedido]:
        """Do mais novo para o mais antigo."""
        condicoes, valores = [], []
        if projeto is not None:
            condicoes.append("projeto = ?")
            valores.append(projeto)
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
        """Os que esperam desenho, dos mais antigos: pendentes e reservas vencidas."""
        with self._conexao() as conexao:
            linhas = conexao.execute(
                """
                SELECT * FROM pedidos
                WHERE situacao = 'pendente'
                   OR (situacao = 'em_desenho' AND reservado_ate < :agora)
                ORDER BY criado_em ASC LIMIT :limite
                """,
                {"agora": _carimbo(agora or agora_utc()), "limite": max(1, int(limite))},
            ).fetchall()
        return [_pedido(linha) for linha in linhas]

    def contar_na_fila(self, agora: datetime | None = None) -> int:
        with self._conexao() as conexao:
            (quantos,) = conexao.execute(
                """
                SELECT count(*) FROM pedidos
                WHERE situacao = 'pendente'
                   OR (situacao = 'em_desenho' AND reservado_ate < :agora)
                """,
                {"agora": _carimbo(agora or agora_utc())},
            ).fetchone()
        return int(quantos)

    # ------------------------------------------------------------------
    # Transições — cada uma, um UPDATE condicional
    # ------------------------------------------------------------------
    def reservar(
        self, ids: Sequence[str], leva: str, agora: datetime | None = None
    ) -> list[Pedido]:
        """Reserva os que ainda estiverem livres; devolve só os reservados agora."""
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
        with self._conexao() as conexao:
            linhas = conexao.execute(
                f"""
                UPDATE pedidos SET
                    situacao = 'em_desenho', leva = :leva, reservado_ate = :ate,
                    desenhando_desde = NULL, atualizado_em = :agora,
                    {_evento("'em_desenho'")}
                WHERE id IN ({marcadores})
                  AND (situacao = 'pendente'
                       OR (situacao = 'em_desenho' AND reservado_ate < :agora))
                RETURNING *
                """,
                valores,
            ).fetchall()
        reservados = [_pedido(linha) for linha in linhas]
        return sorted(reservados, key=lambda pedido: pedido.criado_em)

    def iniciar(self, pedido_id: str, agora: datetime | None = None) -> Pedido:
        """Um ``desenhar(pedido_id)`` começou: marca e renova a leva inteira.

        Aceita pedido pendente (por exemplo, devolvido à fila) ou em desenho;
        recusa concluído, falho e cancelado.
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
                    reservado_ate = :ate, leva = COALESCE(leva, :leva),
                    atualizado_em = :agora, {_evento("'em_desenho'")}
                WHERE id = :id AND situacao IN ('pendente', 'em_desenho')
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
                    WHERE leva = :leva AND situacao = 'em_desenho' AND id != :id
                    """,
                    {"ate": valores["ate"], "leva": linha["leva"], "id": pedido_id},
                )
        if linha is None:
            atual = self.obter(pedido_id)
            raise TransicaoRecusada(_por_que_nao_desenha(atual), atual)
        return _pedido(linha)

    def concluir(
        self,
        pedido_id: str,
        *,
        asset_id: str,
        job_id: str,
        asset_projeto: str,
        laudo: str,
        agora: datetime | None = None,
    ) -> Pedido | None:
        """Aprovado: conclui, se o pedido ainda estiver em desenho. ``None`` se não."""
        return self._uma(
            f"""
            UPDATE pedidos SET
                situacao = 'concluido', asset_id = :asset, job_id = :job,
                asset_projeto = :projeto, ultimo_laudo = :laudo, motivo = NULL,
                desenhando_desde = NULL, reservado_ate = NULL,
                atualizado_em = :agora, {_evento("'concluido'")}
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
                "nota": f"aprovado: {asset_id}",
            },
        )

    def reprovar(
        self,
        pedido_id: str,
        *,
        asset_id: str,
        job_id: str,
        asset_projeto: str,
        laudo: str,
        agora: datetime | None = None,
    ) -> Pedido | None:
        """Não aprovado: conta a tentativa; no teto, o pedido vai para ``falhou``."""
        nova = (
            "CASE WHEN tentativas + 1 >= max_tentativas "
            "THEN 'falhou' ELSE 'em_desenho' END"
        )
        return self._uma(
            f"""
            UPDATE pedidos SET
                tentativas = tentativas + 1, situacao = {nova},
                asset_id = :asset, job_id = :job, asset_projeto = :projeto,
                ultimo_laudo = :laudo, desenhando_desde = NULL,
                motivo = CASE WHEN tentativas + 1 >= max_tentativas
                    THEN 'não aprovado em ' || max_tentativas || ' tentativas'
                    ELSE motivo END,
                reservado_ate = CASE WHEN tentativas + 1 >= max_tentativas
                    THEN NULL ELSE reservado_ate END,
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
                "agora": _carimbo(agora or agora_utc()),
                "nota": f"não aprovado: {asset_id}",
            },
        )

    def desenho_interrompido(
        self, pedido_id: str, *, nota: str, agora: datetime | None = None
    ) -> Pedido | None:
        """O desenho não produziu asset (receita recusada, erro): só limpa a marca."""
        return self._uma(
            f"""
            UPDATE pedidos SET
                desenhando_desde = NULL, atualizado_em = :agora,
                {_evento("situacao")}
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
                atualizado_em = :agora, {_evento("'cancelado'")}
            WHERE id = :id AND situacao IN ('pendente', 'em_desenho')
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
        """Tira a reserva e volta para ``pendente``, sem cancelar nem zerar tentativas."""
        linha = self._uma(
            f"""
            UPDATE pedidos SET
                situacao = 'pendente', leva = NULL, reservado_ate = NULL,
                desenhando_desde = NULL, atualizado_em = :agora,
                {_evento("'pendente'")}
            WHERE id = :id AND situacao = 'em_desenho'
            RETURNING *
            """,
            {"id": pedido_id, "agora": _carimbo(agora or agora_utc()), "nota": "devolvido à fila na tela"},
        )
        if linha is None:
            atual = self.obter(pedido_id)
            raise TransicaoRecusada(
                f"o pedido {pedido_id} está {_situacao_lida(atual)}: só um pedido em "
                "desenho volta para a fila",
                atual,
            )
        return linha

    def _uma(self, sql: str, valores: dict[str, Any]) -> Pedido | None:
        # fetchall: a instrução vai até o fim e confirma antes de a conexão fechar.
        with self._conexao() as conexao:
            linhas = conexao.execute(sql, valores).fetchall()
        return _pedido(linhas[0]) if linhas else None


def _situacao_lida(pedido: Pedido) -> str:
    return {
        Situacao.PENDENTE: "na fila",
        Situacao.EM_DESENHO: "em desenho",
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
    return (
        f"o pedido {pedido.id} terminou sem aprovação ({pedido.motivo or 'falhou'}): "
        "faça outro pedido na tela para tentar de novo"
    )


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
        ultimo_laudo=dados["ultimo_laudo"],
        leva=dados["leva"],
        reservado_ate=_momento(dados["reservado_ate"]),
        desenhando_desde=_momento(dados["desenhando_desde"]),
        motivo=dados["motivo"],
        eventos=tuple(Evento.model_validate(e) for e in json.loads(dados["eventos"] or "[]")),
        criado_em=datetime.fromisoformat(dados["criado_em"]),
        atualizado_em=datetime.fromisoformat(dados["atualizado_em"]),
    )
