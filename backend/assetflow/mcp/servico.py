"""O que as ferramentas MCP fazem, sem depender do SDK do MCP.

Este módulo é o servidor MCP inteiro menos o protocolo: resolve o pedido,
desenha, monta o laudo, aplica o remendo, devolve a imagem. Ficar separado do
SDK (que mora em :mod:`.servidor`) é o que permite testá-lo sem a dependência
opcional instalada — e trocar de SDK sem tocar nele.

Ele fala com o AssetFlow como a API fala: pelo :class:`GenerationService` do
container montado em ``bootstrap.py``, sem HTTP. E pede a gaveta
``desenhista-v1`` **de forma explícita, sem fallback** (plano desenhista §5):
motor escolhido é motor usado, e um desenho que falhe falha dizendo por quê,
em vez de virar a saída de um mock.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any

from PIL import Image

from ..bootstrap import AppContainer
from ..generation.kernel.exceptions import GenerationError
from ..generation.schemas import (
    AssetGenerationRequest,
    AssetMode,
    AssetOutputOverrides,
    EngineSelector,
)
from ..pixel_knowledge import montar_recorte, porte
from ..storage.records import GenerationRecord
from .laudo import formatar_consulta, formatar_laudo
from .remendo import RemendoInvalido, aplicar_remendo

__all__ = [
    "MOTOR",
    "PERFIL_PADRAO",
    "PROJETO",
    "ErroDoPedido",
    "ServicoDesenhista",
]

#: A gaveta que o MCP pede, sempre pelo nome (plano desenhista §5).
MOTOR = "desenhista-v1"
#: Onde os assets desenhados pela conversa ficam: ``data/assets/projects/mcp/``.
PROJETO = "mcp"
#: Profile de partida quando o Claude não diz qual. Ele só vale no que o texto
#: não disser — é a camada mais fraca da precedência depois do padrão global.
PERFIL_PADRAO = "pixel_character_32"
#: Lado aproximado, em pixels, da imagem que ``ver_asset`` devolve.
LADO_DA_AMPLIACAO = 256


class ErroDoPedido(Exception):
    """Algo que o Claude precisa corrigir; a mensagem diz o quê, em português."""


class ServicoDesenhista:
    """As ferramentas do desenhista, sobre um container já montado."""

    def __init__(self, container: AppContainer, *, timeout_s: float | None = None) -> None:
        self._container = container
        self._service = container.service
        # O teto do worker já envolve o pipeline inteiro; esperar além dele
        # não faria um job terminar.
        self._timeout_s = timeout_s or (container.settings.worker.job_timeout_s + 30.0)

    # ------------------------------------------------------------------
    def perfis(self) -> list[str]:
        """Os profiles Pixel Art, que a descrição de ``perfil`` oferece."""
        return sorted(
            profile.id
            for profile in self._service.profiles()
            if profile.asset.mode is AssetMode.PIXEL and not profile.id.startswith("adhoc:")
        )

    # ------------------------------------------------------------------
    def consultar(self, pedido: str, perfil: str | None = None, molde: bool = False) -> str:
        perfil = self._perfil(perfil)
        texto = self._texto(pedido)
        spec = self._resolver(texto, perfil)
        # O recorte lê o spec já resolvido e só acrescenta orientação: o que
        # o pedido virou (tamanho, paleta, tipo) não muda por causa da base.
        # A receita do molde só vem quando pedida — por padrão, só as medidas.
        recorte = montar_recorte(
            spec,
            self._container.conhecimento,
            molde=molde,
            referencias=self._container.referencias,
        )
        return formatar_consulta(texto, perfil, spec, conhecimento=recorte)

    # ------------------------------------------------------------------
    async def desenhar(
        self,
        pedido: str | None = None,
        receita: dict[str, Any] | None = None,
        base: str | None = None,
        perfil: str | None = None,
    ) -> str:
        primeira_linha: str | None = None

        if base:
            registro = await self._registro(base)
            receita_base = (registro.engine_options.get(MOTOR) or {}).get("receita")
            if not isinstance(receita_base, dict):
                raise ErroDoPedido(
                    f"o asset '{base}' não foi desenhado pela {MOTOR}: não há receita "
                    "para remendar"
                )
            if receita is None:
                raise ErroDoPedido(
                    "com base, mande em 'receita' o que muda: 'paleta' e/ou 'camadas'"
                )
            try:
                receita, resumo = aplicar_remendo(receita_base, receita)
            except RemendoInvalido as exc:
                raise ErroDoPedido(f"remendo inválido: {exc}") from exc
            primeira_linha = f"remendo de {base}: {resumo.texto()}"
            pedido = pedido or registro.user_prompt
            perfil = perfil or registro.profile_id
        else:
            if receita is None:
                raise ErroDoPedido(
                    "falta 'receita' (desenho novo) ou 'base' com a receita parcial (remendo)"
                )
            if not pedido:
                raise ErroDoPedido("falta 'pedido': o texto do que desenhar")

        texto = self._texto(pedido)
        perfil = self._perfil(perfil)
        job = await self._executar(self._pedido(texto, perfil, receita))

        if job.status.value != "completed":
            mensagem = job.error.message if job.error else f"o job terminou como {job.status.value}"
            raise ErroDoPedido(mensagem)
        return await self._laudo(job, texto, primeira_linha)

    # ------------------------------------------------------------------
    async def ver(self, asset_id: str) -> tuple[bytes, str]:
        """O PNG do asset ampliado por vizinho mais próximo, e uma legenda."""
        registro = await self._registro(asset_id)
        if not registro.outputs:
            raise ErroDoPedido(f"o asset '{asset_id}' não tem arquivo gravado")
        saida = registro.outputs[0]
        original = Image.open(io.BytesIO(await self._container.storage.read(saida.uri)))
        maior = max(original.width, original.height)
        escala = max(1, LADO_DA_AMPLIACAO // maior)
        ampliada = original.convert("RGBA").resize(
            (original.width * escala, original.height * escala), Image.NEAREST
        )
        buffer = io.BytesIO()
        ampliada.save(buffer, format="PNG")
        legenda = (
            f"{asset_id} · {original.width}×{original.height} ampliado {escala}× · "
            f"{saida.status or 'sem veredito'}"
        )
        return buffer.getvalue(), legenda

    # ------------------------------------------------------------------
    def ver_referencia(self, pedido: str, perfil: str | None = None) -> tuple[bytes, str]:
        """UM quadro de referência do tipo do pedido, ampliado, e a legenda.

        O tipo, o corpo e a altura do corpo saem do spec resolvido, pelo mesmo
        ``porte`` que monta a linha ``referências:`` do recorte.
        """
        perfil = self._perfil(perfil)
        texto = self._texto(pedido)
        spec = self._resolver(texto, perfil)
        alvo = porte(spec, self._container.conhecimento)
        if alvo is None:
            raise ErroDoPedido("o pedido não é Pixel Art: não há referência para ele")
        exemplo = self._container.referencias.exemplo(alvo.tipo, alvo.corpo, alvo.altura)
        if exemplo is None:
            onde = alvo.tipo + (f"/{alvo.corpo}" if alvo.corpo else "")
            raise ErroDoPedido(
                f"não há referência ativa de {onde}: importe e ative um pacote "
                "(python -m assetflow.referencias listar)"
            )
        return exemplo

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _pedido(
        self, texto: str, perfil: str, receita: dict[str, Any] | None
    ) -> AssetGenerationRequest:
        """O mesmo pedido para consultar e para desenhar — logo, o mesmo spec."""
        return AssetGenerationRequest(
            project_id=PROJETO,
            profile=perfil,
            prompt=texto,
            # Uma receita é um desenho: mais variações seriam cópias, e o
            # kernel recusa. "Uma" é o nível da interface na precedência; um
            # "4 variações" no texto ganharia, e a recusa diria por quê.
            output=AssetOutputOverrides(variations=1),
            engine=EngineSelector(mode="manual", engine_id=MOTOR, allow_fallback=False),
            engine_options={MOTOR: {"receita": receita}} if receita is not None else {},
        )

    def _resolver(self, texto: str, perfil: str):
        try:
            return self._service.resolve_spec(self._pedido(texto, perfil, None))
        except GenerationError as exc:
            raise ErroDoPedido(exc.message) from exc

    async def _executar(self, pedido: AssetGenerationRequest):
        """Submete o job e roda o worker até ele terminar.

        O worker roda aqui, e não em segundo plano: o servidor só existe para
        atender a conversa, e cada chamada espera o próprio desenho. Mais de
        uma chamada ao mesmo tempo não trava — cada uma processa o que estiver
        na fila até o seu job terminar.
        """
        try:
            job = await self._service.submit(pedido)
        except GenerationError as exc:
            raise ErroDoPedido(exc.message) from exc

        limite = time.monotonic() + self._timeout_s
        while not job.status.is_terminal:
            if time.monotonic() > limite:
                raise ErroDoPedido(
                    f"o job {job.id} não terminou em {self._timeout_s:.0f}s"
                )
            await self._container.worker.run_once(timeout=1.0)
            job = await self._service.get_job(job.id)
        return job

    async def _laudo(self, job, texto: str, primeira_linha: str | None) -> str:
        asset = job.asset
        variante = asset.variants[0]
        storage = self._container.storage

        validacao = await self._json(variante.artifacts.get("validation.json"))
        otimizacao = await self._json(variante.artifacts.get("optimizer.json"))
        saida_motor = await self._json(variante.artifacts.get("engine_output.json"))
        avisos = list(
            ((saida_motor or {}).get("engine_metadata") or {}).get("avisos_receita") or []
        )

        chave = storage.backend.key_from_uri(variante.uri)
        caminho = storage.backend.root / chave if chave else Path(variante.uri)
        return formatar_laudo(
            pedido=texto,
            asset_id=asset.id,
            variante=variante,
            spec=job.resolved_spec,
            validacao=validacao or {},
            otimizacao=otimizacao,
            avisos_receita=avisos,
            caminho=caminho,
            remendo=primeira_linha,
        )

    async def _json(self, uri: str | None) -> dict[str, Any] | None:
        if not uri:
            return None
        return json.loads((await self._container.storage.read(uri)).decode("utf-8"))

    async def _registro(self, asset_id: str) -> GenerationRecord:
        """O registro do histórico de um asset — sobrevive a reinícios do servidor."""
        repositorio = self._container.storage.records
        if repositorio is not None:
            for registro in await repositorio.list(limit=1_000_000):
                if registro.asset_id == asset_id:
                    return registro
        raise ErroDoPedido(f"não há asset '{asset_id}' no histórico")

    def _perfil(self, perfil: str | None) -> str:
        perfil = perfil or PERFIL_PADRAO
        validos = self.perfis()
        if perfil not in validos:
            raise ErroDoPedido(
                f"perfil '{perfil}' não é um profile de Pixel Art (opções: {', '.join(validos)})"
            )
        return perfil

    @staticmethod
    def _texto(pedido: str | None) -> str:
        texto = (pedido or "").strip()
        if not texto:
            raise ErroDoPedido("o pedido está vazio: descreva o que desenhar")
        return texto
