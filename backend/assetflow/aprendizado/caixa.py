"""Lições, opiniões e exemplos mostrados, num SQLite em ``data/aprendizado/``.

A API (a tela lista, edita, desliga e apaga lições; grava opiniões) e o
servidor MCP (registra lições, lê as opiniões pendentes, escolhe as lições de
um pedido) são dois processos: o arquivo segue as regras de
:mod:`assetflow.sqlite_curto`, como a fila de pedidos. É da instalação — não
vai ao git — e nunca é apagado: travado ou danificado vira
:class:`AprendizadoIndisponivel`, com o caminho.

**Lição repetida não duplica.** Ela soma no contador de uma lição existente
quando quem registra diz qual (``mesma_que``), ou quando outra lição da mesma
origem, do mesmo tipo e do mesmo tema tem a regra com ao menos 70% das
mesmas palavras.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..sqlite_curto import BancoCurto
from .modelo import (
    MAX_ERROU,
    MAX_MOTIVO,
    MAX_PORQUE,
    MAX_REGRA,
    QUALQUER,
    Licao,
    Natureza,
    Opiniao,
    Origem,
    SituacaoDaOpiniao,
    Tema,
    ler_tema,
    palavras,
)

__all__ = [
    "SEMELHANCA_MINIMA",
    "AprendizadoIndisponivel",
    "CaixaDeAprendizado",
    "ErroDoAprendizado",
    "LicaoInvalida",
    "LicaoNaoEncontrada",
    "Registro",
]

#: Fração de palavras em comum (Jaccard) a partir da qual duas regras são a mesma.
SEMELHANCA_MINIMA = 0.7

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS licoes (
    numero          INTEGER PRIMARY KEY AUTOINCREMENT,
    errou           TEXT NOT NULL,
    porque          TEXT NOT NULL,
    regra           TEXT NOT NULL,
    tema            TEXT NOT NULL,
    tipo            TEXT NOT NULL,
    corpo           TEXT NOT NULL,
    porte           TEXT NOT NULL,
    origem          TEXT NOT NULL,
    texto_da_autora TEXT,
    contador        INTEGER NOT NULL DEFAULT 1,
    ligada          INTEGER NOT NULL DEFAULT 1,
    asset_id        TEXT,
    pedido_id       TEXT,
    assets          TEXT NOT NULL DEFAULT '[]',
    criada_em       TEXT NOT NULL,
    atualizada_em   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS opinioes (
    asset_id  TEXT PRIMARY KEY,
    gostei    INTEGER NOT NULL,
    motivo    TEXT,
    situacao  TEXT NOT NULL,
    licao     INTEGER,
    tipo      TEXT,
    corpo     TEXT,
    porte     TEXT,
    em        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exemplos_mostrados (
    fonte        TEXT PRIMARY KEY,
    mostrado_em  TEXT NOT NULL,
    vezes        INTEGER NOT NULL DEFAULT 1
);
"""


class ErroDoAprendizado(Exception):
    """Algo nas lições ou opiniões; a mensagem é para ser lida, em português."""

    codigo = "aprendizado_indisponivel"


class AprendizadoIndisponivel(ErroDoAprendizado):
    codigo = "aprendizado_indisponivel"


class LicaoNaoEncontrada(ErroDoAprendizado):
    codigo = "licao_nao_encontrada"


class LicaoInvalida(ErroDoAprendizado):
    codigo = "licao_invalida"


class Registro:
    """O que ``registrar`` fez: lição nova, ou +1 numa existente."""

    def __init__(self, licao: Licao, *, nova: bool) -> None:
        self.licao = licao
        self.nova = nova

    def texto(self) -> str:
        if self.nova:
            return f"lição {self.licao.id} registrada ({self.licao.tema.value})"
        return (
            f"lição {self.licao.id} já existia: contador agora {self.licao.contador} "
            f"— \"{self.licao.regra}\""
        )


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class CaixaDeAprendizado:
    """Operações sobre o arquivo. Cada uma abre e fecha a conexão."""

    def __init__(self, caminho: Path, *, espera_s: float = 5.0) -> None:
        self._caminho = Path(caminho)
        self._espera_s = float(espera_s)
        self._banco = BancoCurto(
            self._caminho, esquema=_ESQUEMA, traduzir=self._traduzir, espera_s=espera_s
        )

    @property
    def caminho(self) -> Path:
        return self._caminho

    @contextmanager
    def _conexao(self) -> Iterator[sqlite3.Connection]:
        with self._banco.conexao() as conexao:
            yield conexao

    def _traduzir(self, exc: Exception) -> ErroDoAprendizado:
        texto = str(exc).lower()
        if isinstance(exc, sqlite3.OperationalError) and ("locked" in texto or "busy" in texto):
            return AprendizadoIndisponivel(
                f"as lições estão ocupadas por outro processo há mais de {self._espera_s:g} s; "
                f"tente de novo em instantes ({self._caminho})"
            )
        if isinstance(exc, sqlite3.DatabaseError) and (
            "not a database" in texto or "malformed" in texto or "corrupt" in texto
        ):
            return AprendizadoIndisponivel(
                f"o arquivo das lições está danificado e não foi alterado: {self._caminho}. "
                "Feche a API e o servidor MCP, guarde uma cópia dele (com os arquivos -wal "
                "e -shm ao lado) e tire os três do lugar para começar um arquivo novo."
            )
        return AprendizadoIndisponivel(f"as lições não responderam ({self._caminho}): {exc}")

    # ------------------------------------------------------------------
    # Lições
    # ------------------------------------------------------------------
    def registrar(
        self,
        *,
        errou: str,
        porque: str,
        regra: str,
        tema: str,
        tipo: str,
        corpo: str,
        porte: str,
        origem: Origem = Origem.CLAUDE,
        texto_da_autora: str | None = None,
        asset_id: str | None = None,
        pedido_id: str | None = None,
        mesma_que: str | None = None,
    ) -> Registro:
        """Lição nova, ou +1 numa que já diz a mesma coisa."""
        tema_lido = ler_tema(tema)
        if tema_lido is None:
            raise LicaoInvalida(
                f"tema '{tema}' não existe: use {', '.join(t.value for t in Tema)}"
            )
        errou, porque, regra = (texto.strip() for texto in (errou, porque, regra))
        for nome, texto, teto in (
            ("errou", errou, MAX_ERROU),
            ("porque", porque, MAX_PORQUE),
            ("regra", regra, MAX_REGRA),
        ):
            if not texto:
                raise LicaoInvalida(f"falta '{nome}' na lição")
            if len(texto) > teto:
                raise LicaoInvalida(
                    f"'{nome}' tem {len(texto)} caracteres; o teto é {teto}: encurte"
                )

        repetida = self._repetida(mesma_que, regra, tema_lido, tipo, Origem(origem))
        agora = _agora()
        with self._conexao() as conexao:
            if repetida is not None:
                linha = conexao.execute(
                    """
                    UPDATE licoes SET
                        contador = contador + 1, atualizada_em = :agora,
                        assets = CASE WHEN :asset IS NULL THEN assets ELSE (
                            SELECT json_group_array(value) FROM (
                                SELECT :asset AS value
                                UNION ALL
                                SELECT value FROM (
                                    SELECT value FROM json_each(licoes.assets)
                                    WHERE value != :asset LIMIT 9)
                            )) END
                    WHERE numero = :numero
                    RETURNING *
                    """,
                    {"numero": repetida, "agora": agora, "asset": asset_id},
                ).fetchall()
                if linha:
                    return Registro(_licao(linha[0]), nova=False)
            linha = conexao.execute(
                """
                INSERT INTO licoes (
                    errou, porque, regra, tema, tipo, corpo, porte, origem,
                    texto_da_autora, asset_id, pedido_id, assets, criada_em, atualizada_em
                ) VALUES (
                    :errou, :porque, :regra, :tema, :tipo, :corpo, :porte, :origem,
                    :texto, :asset, :pedido, :assets, :agora, :agora
                )
                RETURNING *
                """,
                {
                    "errou": errou,
                    "porque": porque,
                    "regra": regra,
                    "tema": tema_lido.value,
                    "tipo": tipo or QUALQUER,
                    "corpo": corpo or QUALQUER,
                    "porte": porte or QUALQUER,
                    "origem": Origem(origem).value,
                    "texto": texto_da_autora,
                    "asset": asset_id,
                    "pedido": pedido_id,
                    "assets": json.dumps([asset_id] if asset_id else []),
                    "agora": agora,
                },
            ).fetchall()
        return Registro(_licao(linha[0]), nova=True)

    def _repetida(
        self, mesma_que: str | None, regra: str, tema: Tema, tipo: str, origem: Origem
    ) -> int | None:
        if mesma_que:
            numero = _numero(mesma_que)
            self.obter(numero)  # erro claro se não existir
            return numero
        minhas = palavras(regra)
        if not minhas:
            return None
        melhor, maior = None, 0.0
        for licao in self.listar():
            if licao.origem is not origem or licao.tema is not tema or licao.tipo != (tipo or QUALQUER):
                continue
            outras = palavras(licao.regra)
            if not outras:
                continue
            semelhanca = len(minhas & outras) / len(minhas | outras)
            if semelhanca >= SEMELHANCA_MINIMA and semelhanca > maior:
                melhor, maior = licao.numero, semelhanca
        return melhor

    def obter(self, licao: str | int) -> Licao:
        numero = _numero(licao)
        with self._conexao() as conexao:
            linha = conexao.execute("SELECT * FROM licoes WHERE numero = ?", (numero,)).fetchone()
        if linha is None:
            raise LicaoNaoEncontrada(f"não há lição L{numero}")
        return _licao(linha)

    def listar(self) -> list[Licao]:
        """Todas, as de maior contador primeiro."""
        with self._conexao() as conexao:
            linhas = conexao.execute(
                "SELECT * FROM licoes ORDER BY contador DESC, atualizada_em DESC"
            ).fetchall()
        return [_licao(linha) for linha in linhas]

    def editar(
        self,
        licao: str | int,
        *,
        regra: str | None = None,
        tema: str | None = None,
        ligada: bool | None = None,
    ) -> Licao:
        """O que a tela muda: o texto da regra, o tema, ligada ou desligada."""
        numero = _numero(licao)
        mudancas: dict[str, Any] = {}
        if regra is not None:
            regra = regra.strip()
            if not regra:
                raise LicaoInvalida("a regra não pode ficar vazia")
            if len(regra) > MAX_REGRA:
                raise LicaoInvalida(f"a regra tem {len(regra)} caracteres; o teto é {MAX_REGRA}")
            mudancas["regra"] = regra
        if tema is not None:
            lido = ler_tema(tema)
            if lido is None:
                raise LicaoInvalida(f"tema '{tema}' não existe")
            mudancas["tema"] = lido.value
        if ligada is not None:
            mudancas["ligada"] = 1 if ligada else 0
        if not mudancas:
            return self.obter(numero)
        campos = ", ".join(f"{campo} = :{campo}" for campo in mudancas)
        with self._conexao() as conexao:
            linhas = conexao.execute(
                f"UPDATE licoes SET {campos}, atualizada_em = :agora WHERE numero = :numero RETURNING *",
                {**mudancas, "numero": numero, "agora": _agora()},
            ).fetchall()
        if not linhas:
            raise LicaoNaoEncontrada(f"não há lição L{numero}")
        return _licao(linhas[0])

    def apagar(self, licao: str | int) -> None:
        numero = _numero(licao)
        with self._conexao() as conexao:
            apagadas = conexao.execute(
                "DELETE FROM licoes WHERE numero = ? RETURNING numero", (numero,)
            ).fetchall()
            # A opinião que tinha virado esta lição volta a ser só nota.
            conexao.execute(
                "UPDATE opinioes SET situacao = 'nota', licao = NULL WHERE licao = ?", (numero,)
            )
        if not apagadas:
            raise LicaoNaoEncontrada(f"não há lição L{numero}")

    def escolher(
        self,
        *,
        tipo: str,
        corpo: str | None,
        porte: str | None,
        so_tecnica: bool = False,
        peso_autora: int = 3,
        maximo: int = 5,
    ) -> list[Licao]:
        """As lições de um pedido: ligadas, do tipo e do corpo dele (ou gerais).

        Ordem: contador × peso (a autora pesa ``peso_autora``), depois as do
        mesmo porte, depois as mais recentes. Em ``ousado`` (``so_tecnica``),
        só as de técnica: a forma é livre.
        """
        if maximo <= 0:
            return []
        corpo = corpo or QUALQUER

        def serve(licao: Licao) -> bool:
            return (
                licao.ligada
                and licao.tipo in (tipo, QUALQUER)
                and licao.corpo in (corpo, QUALQUER)
                and (not so_tecnica or licao.natureza is Natureza.TECNICA)
            )

        def ordem(licao: Licao) -> tuple:
            peso = peso_autora if licao.origem is Origem.AUTORA else 1
            return (-licao.contador * peso, licao.porte != porte, -licao.atualizada_em.timestamp())

        return sorted(filter(serve, self.listar()), key=ordem)[:maximo]

    # ------------------------------------------------------------------
    # Opiniões
    # ------------------------------------------------------------------
    def opinar(
        self,
        asset_id: str,
        *,
        gostei: bool,
        motivo: str | None = None,
        tipo: str | None = None,
        corpo: str | None = None,
        porte: str | None = None,
    ) -> Opiniao:
        """Grava (ou troca) a opinião da autora sobre um asset.

        Só um "não gostei" com motivo fica pendente para virar lição; o resto
        é nota do asset. Trocar a opinião não apaga a lição já escrita.
        """
        motivo = (motivo or "").strip() or None
        if motivo and len(motivo) > MAX_MOTIVO:
            raise LicaoInvalida(f"o motivo tem {len(motivo)} caracteres; o teto é {MAX_MOTIVO}")
        situacao = (
            SituacaoDaOpiniao.PENDENTE if (not gostei and motivo) else SituacaoDaOpiniao.NOTA
        )
        with self._conexao() as conexao:
            linha = conexao.execute(
                """
                INSERT INTO opinioes (asset_id, gostei, motivo, situacao, licao, tipo, corpo, porte, em)
                VALUES (:asset, :gostei, :motivo, :situacao, NULL, :tipo, :corpo, :porte, :em)
                ON CONFLICT(asset_id) DO UPDATE SET
                    gostei = excluded.gostei, motivo = excluded.motivo,
                    situacao = CASE
                        WHEN opinioes.situacao = 'convertida'
                             AND COALESCE(opinioes.motivo, '') = COALESCE(excluded.motivo, '')
                             AND excluded.gostei = 0
                        THEN 'convertida' ELSE excluded.situacao END,
                    licao = CASE
                        WHEN opinioes.situacao = 'convertida'
                             AND COALESCE(opinioes.motivo, '') = COALESCE(excluded.motivo, '')
                             AND excluded.gostei = 0
                        THEN opinioes.licao ELSE NULL END,
                    tipo = COALESCE(excluded.tipo, opinioes.tipo),
                    corpo = COALESCE(excluded.corpo, opinioes.corpo),
                    porte = COALESCE(excluded.porte, opinioes.porte),
                    em = excluded.em
                RETURNING *
                """,
                {
                    "asset": asset_id,
                    "gostei": 1 if gostei else 0,
                    "motivo": motivo,
                    "situacao": situacao.value,
                    "tipo": tipo,
                    "corpo": corpo,
                    "porte": porte,
                    "em": _agora(),
                },
            ).fetchall()
        return _opiniao(linha[0])

    def opiniao(self, asset_id: str) -> Opiniao | None:
        with self._conexao() as conexao:
            linha = conexao.execute(
                "SELECT * FROM opinioes WHERE asset_id = ?", (asset_id,)
            ).fetchone()
        return _opiniao(linha) if linha else None

    def opinioes(self, asset_ids: Sequence[str] = ()) -> dict[str, Opiniao]:
        with self._conexao() as conexao:
            if asset_ids:
                marcadores = ", ".join("?" * len(asset_ids))
                linhas = conexao.execute(
                    f"SELECT * FROM opinioes WHERE asset_id IN ({marcadores})", tuple(asset_ids)
                ).fetchall()
            else:
                linhas = conexao.execute("SELECT * FROM opinioes").fetchall()
        return {linha["asset_id"]: _opiniao(linha) for linha in linhas}

    def pendentes(self) -> list[Opiniao]:
        """Os "não gostei" com motivo que ainda não viraram lição, dos mais antigos."""
        with self._conexao() as conexao:
            linhas = conexao.execute(
                "SELECT * FROM opinioes WHERE situacao = 'pendente' ORDER BY em ASC"
            ).fetchall()
        return [_opiniao(linha) for linha in linhas]

    def gostei(self, *, tipo: str, corpo: str | None, porte: str) -> list[Opiniao]:
        """Os assets marcados com "gostei" do mesmo tipo, corpo e porte."""
        with self._conexao() as conexao:
            linhas = conexao.execute(
                """
                SELECT * FROM opinioes
                WHERE gostei = 1 AND tipo = :tipo AND porte = :porte
                  AND COALESCE(corpo, :qualquer) = COALESCE(:corpo, :qualquer)
                ORDER BY em DESC
                """,
                {"tipo": tipo, "corpo": corpo, "porte": porte, "qualquer": QUALQUER},
            ).fetchall()
        return [_opiniao(linha) for linha in linhas]

    def converter(self, asset_id: str, licao: int) -> None:
        """A opinião pendente virou a lição ``licao``."""
        with self._conexao() as conexao:
            conexao.execute(
                "UPDATE opinioes SET situacao = 'convertida', licao = :licao WHERE asset_id = :asset",
                {"asset": asset_id, "licao": licao},
            ).fetchall()

    # ------------------------------------------------------------------
    # Exemplos mostrados (rotação entre pacotes)
    # ------------------------------------------------------------------
    def ordem_das_fontes(self, fontes: Sequence[str]) -> list[str]:
        """As fontes na ordem da rotação: nunca mostradas, depois a mais antiga."""
        with self._conexao() as conexao:
            vistas = {
                linha["fonte"]: linha["mostrado_em"]
                for linha in conexao.execute("SELECT fonte, mostrado_em FROM exemplos_mostrados")
            }
        return sorted(fontes, key=lambda fonte: (fonte in vistas, vistas.get(fonte, ""), fonte))

    def exemplo_mostrado(self, fonte: str) -> None:
        with self._conexao() as conexao:
            conexao.execute(
                """
                INSERT INTO exemplos_mostrados (fonte, mostrado_em) VALUES (:fonte, :agora)
                ON CONFLICT(fonte) DO UPDATE SET
                    mostrado_em = excluded.mostrado_em, vezes = exemplos_mostrados.vezes + 1
                """,
                {"fonte": fonte, "agora": _agora()},
            ).fetchall()


def _numero(licao: str | int) -> int:
    texto = str(licao).strip().upper().lstrip("L")
    if not texto.isdigit():
        raise LicaoNaoEncontrada(f"'{licao}' não é um id de lição (como L3)")
    return int(texto)


def _licao(linha: sqlite3.Row) -> Licao:
    dados = dict(linha)
    return Licao(
        numero=int(dados["numero"]),
        errou=dados["errou"],
        porque=dados["porque"],
        regra=dados["regra"],
        tema=Tema(dados["tema"]),
        tipo=dados["tipo"],
        corpo=dados["corpo"],
        porte=dados["porte"],
        origem=Origem(dados["origem"]),
        texto_da_autora=dados["texto_da_autora"],
        contador=int(dados["contador"]),
        ligada=bool(dados["ligada"]),
        asset_id=dados["asset_id"],
        pedido_id=dados["pedido_id"],
        assets=tuple(json.loads(dados["assets"] or "[]")),
        criada_em=datetime.fromisoformat(dados["criada_em"]),
        atualizada_em=datetime.fromisoformat(dados["atualizada_em"]),
    )


def _opiniao(linha: sqlite3.Row) -> Opiniao:
    dados = dict(linha)
    return Opiniao(
        asset_id=dados["asset_id"],
        gostei=bool(dados["gostei"]),
        motivo=dados["motivo"],
        situacao=SituacaoDaOpiniao(dados["situacao"]),
        licao=dados["licao"],
        tipo=dados["tipo"],
        corpo=dados["corpo"],
        porte=dados["porte"],
        em=datetime.fromisoformat(dados["em"]),
    )
