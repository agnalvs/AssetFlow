"""A banca de teste: rodadas ligadas a uma versão da base, e a comparação cega.

Etapa K1 do ``PLANO_BASE_CONHECIMENTO.md`` (seções 7 e 8), na versão enxuta.

- **Rodada**: os seis pedidos de ``config/banca.yaml``, criados na fila (no
  projeto ``banca``, para não misturar com a galeria) com o modo de conceito
  da rodada. Guarda a versão da base (a impressão de ``config/pixel_knowledge/``
  e dos interruptores), o commit e as lições ligadas naquele momento.
- **Comparar**: duas rodadas, item a item, lado a lado. O lado de cada rodada é
  sorteado por par (de forma determinística: recarregar não troca) e não é
  dito. A autora escolhe o melhor e dá uma nota de 1 a 5 a cada imagem.
- **Resumo**: só depois dos votos de todos os pares, revelando os lados.
  Item sem desenho (falhou, cancelado) perde, com nota 1.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from ..aprendizado import CaixaDeAprendizado, ErroDoAprendizado
from ..pedidos import CorpoDoPedido, ErroDaFila, ModoConceito, Pedido, ServicoDePedidos
from .caixa import CaixaDaBanca, Rodada, Voto
from .config import Banca, BancaInvalida, commit_do_git, impressao_da_base, ler_banca

__all__ = ["ESCOLHAS", "ServicoDaBanca", "tokens_estimados"]

ESCOLHAS = ("esquerda", "direita", "empate")
#: Etapas em que um item da rodada não muda mais.
_FIM = {"pronto", "nao_aprovado", "cancelado"}


def tokens_estimados(custo: Mapping[str, Any]) -> int:
    """Tokens a partir dos caracteres: ~3 por token em texto, ~2,3 em pixels, 294 por imagem."""
    return round(
        (custo.get("entrada", 0) + custo.get("saida_texto", 0)) / 3
        + custo.get("saida_receita", 0) / 2.3
        + 294 * custo.get("imagens", 0)
    )


def _esquerda_e_a(a: str, b: str, item: str) -> bool:
    return hashlib.sha256(f"{a}|{b}|{item}".encode()).digest()[0] % 2 == 0


class ServicoDaBanca:
    def __init__(
        self,
        caixa: CaixaDaBanca,
        pedidos: ServicoDePedidos,
        *,
        config_path,
        base_dir,
        conhecimento_dir,
        projeto: str,
        aprendizado: CaixaDeAprendizado | None = None,
        interruptores: Mapping[str, Any] | None = None,
    ) -> None:
        self.caixa = caixa
        self._pedidos = pedidos
        self._config_path = config_path
        self._base_dir = base_dir
        self._conhecimento_dir = conhecimento_dir
        self.projeto = projeto
        self._aprendizado = aprendizado
        self._interruptores = dict(interruptores or {})

    def banca(self) -> Banca:
        return ler_banca(self._config_path)

    # ------------------------------------------------------------------
    async def criar_rodada(self, rotulo: str, modo_conceito: str) -> Rodada:
        banca = self.banca()
        modo = ModoConceito(modo_conceito)
        interruptores = {**self._interruptores, "modo_conceito": modo.value}
        licoes = []
        if self._aprendizado is not None:
            try:
                licoes = [
                    {"id": l.id, "contador": l.contador, "origem": l.origem.value}
                    for l in self._aprendizado.listar()
                    if l.ligada
                ]
            except ErroDoAprendizado:
                licoes = []
        rodada = self.caixa.nova_rodada(
            rotulo=(rotulo or "").strip() or "sem rótulo",
            modo_conceito=modo.value,
            versao_base=impressao_da_base(self._conhecimento_dir, interruptores),
            git_commit=commit_do_git(self._base_dir),
            interruptores=interruptores,
            licoes=licoes,
        )
        itens = []
        for ordem, item in enumerate(banca.itens, start=1):
            corpo = CorpoDoPedido(
                prompt=item.texto,
                profile=item.perfil,
                liberdade=banca.liberdade,
                modo_conceito=modo,
            )
            pedido = await self._pedidos.criar(
                corpo,
                projeto=self.projeto,
                banca={"rodada": rodada.id, "item": item.id, "ordem": ordem, "total": len(banca.itens)},
            )
            itens.append({"item": item.id, "pedido_id": pedido.id, "ordem": ordem})
        return self.caixa.gravar_itens(rodada.numero, itens)

    def rodadas(self) -> list[Rodada]:
        return self.caixa.rodadas()

    def pedidos_da_rodada(self, rodada: Rodada) -> dict[str, Pedido | None]:
        resultado: dict[str, Pedido | None] = {}
        for entrada in rodada.itens:
            try:
                resultado[entrada["item"]] = self._pedidos.fila.obter(entrada["pedido_id"])
            except ErroDaFila:
                resultado[entrada["item"]] = None
        return resultado

    # ------------------------------------------------------------------
    async def comparar(self, a: str, b: str) -> dict[str, Any]:
        """Os pares de duas rodadas, sem dizer o lado; o resumo, se todos tiverem voto."""
        rodada_a, rodada_b = self.caixa.rodada(a), self.caixa.rodada(b)
        a, b = rodada_a.id, rodada_b.id
        if a == b:
            raise BancaInvalida("compare duas rodadas diferentes")
        pedidos_a, pedidos_b = self.pedidos_da_rodada(rodada_a), self.pedidos_da_rodada(rodada_b)
        votos = self.caixa.votos(a, b)
        try:
            banca = {item.id: item for item in self.banca().itens}
        except BancaInvalida:
            banca = {}
        pares = []
        for item in [i["item"] for i in rodada_a.itens if i["item"] in pedidos_b]:
            a_esquerda = _esquerda_e_a(a, b, item)
            esquerda = pedidos_a[item] if a_esquerda else pedidos_b[item]
            direita = pedidos_b[item] if a_esquerda else pedidos_a[item]
            voto = votos.get(item)
            pares.append(
                {
                    "item": item,
                    "texto": banca[item].texto if item in banca else (esquerda or direita).texto,
                    "testa": banca[item].testa if item in banca else "",
                    "esquerda": esquerda,
                    "direita": direita,
                    "voto": voto,
                    "esquerda_rodada": a if a_esquerda else b,
                }
            )
        avaliados = sum(1 for par in pares if par["voto"] is not None or _sem_desenho(par))
        resumo = None
        if pares and avaliados == len(pares):
            resumo = await self._resumo(rodada_a, rodada_b, pares)
        return {"a": a, "b": b, "pares": pares, "avaliados": avaliados, "resumo": resumo}

    def votar(
        self, a: str, b: str, item: str, escolha: str, nota_esquerda: int, nota_direita: int
    ) -> Voto:
        a, b = self.caixa.rodada(a).id, self.caixa.rodada(b).id
        if escolha not in ESCOLHAS:
            raise BancaInvalida(f"escolha é {', '.join(ESCOLHAS)}")
        for nota in (nota_esquerda, nota_direita):
            if not 1 <= int(nota) <= 5:
                raise BancaInvalida("a nota vai de 1 a 5")
        esquerda = a if _esquerda_e_a(a, b, item) else b
        return self.caixa.votar(
            Voto(a=a, b=b, item=item, esquerda=esquerda, escolha=escolha,
                 nota_esquerda=int(nota_esquerda), nota_direita=int(nota_direita))
        )

    async def _resumo(self, rodada_a: Rodada, rodada_b: Rodada, pares: list[dict[str, Any]]) -> dict[str, Any]:
        a, b = rodada_a.id, rodada_b.id
        # A mais nova é a "mudança"; a outra, a referência.
        nova, velha = (b, a) if rodada_b.numero > rodada_a.numero else (a, b)
        vitorias = {a: 0, b: 0, "empate": 0}
        notas: dict[str, list[int]] = {a: [], b: []}
        quedas = []
        for par in pares:
            lado_esq = par["esquerda_rodada"]
            lado_dir = b if lado_esq == a else a
            voto: Voto | None = par["voto"]
            if voto is None:  # um lado sem desenho perde, com nota 1
                tem_esq = _tem_desenho(par["esquerda"])
                nota_esq, nota_dir = (3, 1) if tem_esq else (1, 3)
                escolha = "esquerda" if tem_esq else "direita"
            else:
                nota_esq, nota_dir, escolha = voto.nota_esquerda, voto.nota_direita, voto.escolha
            notas[lado_esq].append(nota_esq)
            notas[lado_dir].append(nota_dir)
            if escolha == "empate":
                vitorias["empate"] += 1
            else:
                vitorias[lado_esq if escolha == "esquerda" else lado_dir] += 1
            nota_nova = nota_esq if lado_esq == nova else nota_dir
            nota_velha = nota_dir if lado_esq == nova else nota_esq
            quedas.append((nota_nova - nota_velha, par["item"], nota_velha, nota_nova))

        def media(lista: list[int]) -> float:
            return round(sum(lista) / len(lista), 2) if lista else 0.0

        pior = min(quedas) if quedas else None
        mantem = vitorias[nova] > len(pares) / 2 and all(q[0] > -2 for q in quedas)
        extras = {}
        for rodada in (rodada_a, rodada_b):
            pedidos = [p for p in self.pedidos_da_rodada(rodada).values() if p is not None]
            desvios = []
            for pedido in pedidos:
                olhar = await self._pedidos.olhar_do_asset(pedido.asset_projeto, pedido.job_id)
                if olhar:
                    desvios.append(len((olhar.get("olho") or {}).get("desvios") or []))
            extras[rodada.id] = {
                "remendos": media([p.remendos for p in pedidos]),
                "desvios_do_olho": media(desvios),
                "tokens_estimados": sum(tokens_estimados(p.custo) for p in pedidos),
                "modo_conceito": rodada.modo_conceito,
                "versao_base": rodada.versao_base,
                "rotulo": rodada.rotulo,
            }
        return {
            "nova": nova,
            "referencia": velha,
            "vitorias": vitorias,
            "nota_media": {a: media(notas[a]), b: media(notas[b])},
            "maior_queda": (
                {"item": pior[1], "de": pior[2], "para": pior[3]} if pior and pior[0] < 0 else None
            ),
            "por_rodada": extras,
            "lados": {par["item"]: par["esquerda_rodada"] for par in pares},
            "veredito": (
                "mantém: a maioria dos pares melhorou e nenhum caiu 2 ou mais"
                if mantem
                else "não mantém: a mudança não venceu a maioria, ou algum par caiu 2 ou mais"
            ),
        }


def _tem_desenho(pedido: Pedido | None) -> bool:
    """Um lado com desenho concluído (falhou ou cancelado contam como sem desenho)."""
    return pedido is not None and pedido.situacao.value == "concluido"


def _sem_desenho(par: dict[str, Any]) -> bool:
    """Um dos lados não tem desenho e não vai ter: o par conta como avaliado."""
    return any(
        p is None or p.situacao.value in ("falhou", "cancelado")
        for p in (par["esquerda"], par["direita"])
    )
