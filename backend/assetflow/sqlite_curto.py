"""SQLite de conexão curta, para arquivos que a API e o servidor MCP dividem.

São dois processos — o uvicorn e o ``python -m assetflow.mcp`` que o Claude
Code sobe. O que os dois precisam ver mora em disco, e quem mora lá segue
quatro regras de acesso (a fila de pedidos as estreou; as lições as repetem):

* **conexão curta**: cada operação abre, faz e fecha. Nenhum processo segura
  o arquivo entre uma chamada e outra;
* **WAL e ``busy_timeout``**: leitores não esperam escritores, e um escritor
  espera o outro por ``espera_s`` antes de desistir com erro. Com conexão
  curta, cada fechamento seria o último, e o SQLite faria checkpoint e
  apagaria o ``-wal`` a cada operação — 130 ms por escrita no Windows, contra
  7 ms mantendo-o (``SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE``). O checkpoint segue
  automático, a cada 1000 páginas. Por isso cada banco são três arquivos
  (``.sqlite3``, ``-wal``, ``-shm``), e uma cópia de segurança leva os três.
  ``synchronous=NORMAL``, o par recomendado do WAL;
* **uma mudança, uma instrução**: quem escreve usa um ``UPDATE`` condicional
  só, lendo o resultado pelo ``RETURNING``;
* **o arquivo nunca é apagado nem recriado**: banco travado ou danificado vira
  o erro que quem usa o módulo traduz, com o caminho, e fica como está.

Colunas novas entram por ``ALTER TABLE ... ADD COLUMN`` ao abrir: o arquivo de
uma instalação anterior ganha a coluna com o valor padrão, e nada se perde.
Dois processos que abram ao mesmo tempo podem tentar acrescentar a mesma
coluna; o segundo encontra a coluna pronta e segue.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

__all__ = ["BancoCurto", "Traducao"]

#: Converte um erro do SQLite (ou de disco) no erro de quem usa o banco.
Traducao = Callable[[Exception], Exception]


class BancoCurto:
    """Um arquivo SQLite aberto e fechado a cada operação."""

    def __init__(
        self,
        caminho: Path,
        *,
        esquema: str,
        traduzir: Traducao,
        espera_s: float = 5.0,
        colunas_novas: Mapping[str, Sequence[tuple[str, str]]] | None = None,
    ) -> None:
        self._caminho = Path(caminho)
        self._esquema = esquema
        self._traduzir = traduzir
        self._espera_s = float(espera_s)
        self._colunas_novas = dict(colunas_novas or {})
        self._preparado = False

    @property
    def caminho(self) -> Path:
        return self._caminho

    @property
    def espera_s(self) -> float:
        return self._espera_s

    @contextmanager
    def conexao(self) -> Iterator[sqlite3.Connection]:
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
            if not self._preparado:
                self._preparar(conexao)
            yield conexao
        except sqlite3.Error as exc:
            raise self._traduzir(exc) from exc
        finally:
            conexao.close()

    def _preparar(self, conexao: sqlite3.Connection) -> None:
        # WAL é persistente no arquivo; pedir de novo é barato e idempotente.
        conexao.execute("PRAGMA journal_mode = WAL")
        conexao.executescript(self._esquema)
        for tabela, colunas in self._colunas_novas.items():
            existentes = {
                linha["name"] for linha in conexao.execute(f"PRAGMA table_info({tabela})")
            }
            for nome, declaracao in colunas:
                if nome in existentes:
                    continue
                try:
                    conexao.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {declaracao}")
                except sqlite3.OperationalError as exc:
                    # Outro processo acrescentou a mesma coluna no meio-tempo.
                    if "duplicate column" not in str(exc).lower():
                        raise
        self._preparado = True
