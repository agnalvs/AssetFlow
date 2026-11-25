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
from ..pedidos import (
    ErroDaFila,
    Liberdade,
    Pedido,
    Situacao,
    Tipo,
    agora_utc,
    nova_leva,
)
from ..pixel_knowledge import montar_recorte, porte, rampas_da_base
from ..storage.records import GenerationRecord
from .laudo import (
    TETO_PENDENTES,
    bloco_do_pedido,
    formatar_consulta,
    formatar_laudo,
    formatar_pendentes,
)
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
#: Quantos pedidos ``pedidos_pendentes`` traz, no máximo, de uma vez.
MAXIMO_PENDENTES = 10


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
    def consultar(
        self,
        pedido: str,
        perfil: str | None = None,
        molde: bool = False,
        liberdade: str | None = None,
    ) -> str:
        perfil = self._perfil(perfil)
        texto = self._texto(pedido)
        livre = self._liberdade(liberdade)
        spec = self._resolver(texto, perfil)
        # O recorte lê o spec já resolvido e só acrescenta orientação: o que
        # o pedido virou (tamanho, paleta, tipo) não muda por causa da base,
        # nem por causa da liberdade. A receita do molde só vem quando pedida.
        recorte = montar_recorte(
            spec,
            self._container.conhecimento,
            molde=molde,
            referencias=self._container.referencias,
            liberdade=livre,
        )
        return formatar_consulta(texto, perfil, spec, conhecimento=recorte, liberdade=livre.value)

    # ------------------------------------------------------------------
    async def pedidos_pendentes(self, limite: int = 5) -> str:
        """Os pedidos da tela que esperam desenho, já com a consulta de cada um.

        Reserva só os que entram na resposta: o pedido que não couber no teto
        fica na fila, sem reserva, para a próxima chamada.
        """
        limite = max(1, min(int(limite), MAXIMO_PENDENTES))
        fila = self._container.pedidos.fila
        agora = agora_utc()
        try:
            candidatos = fila.candidatos(limite, agora)
        except ErroDaFila as exc:
            raise ErroDoPedido(str(exc)) from exc

        rampas = rampas_da_base(self._container.conhecimento)
        # O que vem uma vez só (cabeçalho, formato da receita, rampas) entra na
        # conta antes dos pedidos; cada pedido entra inteiro ou não entra.
        total = 400 + len(rampas) + 600
        escolhidos: list[tuple[str, str]] = []
        for candidato in candidatos:
            bloco = await self._bloco(candidato, agora)
            if escolhidos and total + len(bloco) + 2 > TETO_PENDENTES:
                break
            escolhidos.append((candidato.id, bloco))
            total += len(bloco) + 2

        try:
            reservados = {
                pedido.id
                for pedido in fila.reservar([pid for pid, _ in escolhidos], nova_leva(), agora)
            }
            restantes = fila.contar_na_fila(agora)
        except ErroDaFila as exc:
            raise ErroDoPedido(str(exc)) from exc
        blocos = [bloco for pid, bloco in escolhidos if pid in reservados]
        return formatar_pendentes(
            blocos,
            restantes=restantes,
            reserva_min=fila.reserva.total_seconds() / 60,
            rampas=rampas,
        )

    # ------------------------------------------------------------------
    async def desenhar(
        self,
        pedido: str | None = None,
        receita: dict[str, Any] | None = None,
        base: str | None = None,
        perfil: str | None = None,
        pedido_id: str | None = None,
    ) -> str:
        if pedido_id:
            return await self._desenhar_pedido(
                pedido_id, receita=receita, base=base, pedido=pedido, perfil=perfil
            )
        primeira_linha: str | None = None

        if base:
            receita, primeira_linha, registro = await self._remendar(base, receita)
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
    def ver_referencia(
        self, pedido: str, perfil: str | None = None, liberdade: str | None = None
    ) -> tuple[bytes, str]:
        """UM quadro de referência do tipo do pedido, ampliado, e a legenda.

        O tipo, o corpo e a altura do corpo saem do spec resolvido, pelo mesmo
        ``porte`` que monta a linha ``referências:`` do recorte. Em ``ousado``,
        a altura não filtra: a imagem sai só pelo estilo, porque o porte é uma
        âncora de proporção, e a proporção é livre.
        """
        perfil = self._perfil(perfil)
        texto = self._texto(pedido)
        livre = self._liberdade(liberdade)
        spec = self._resolver(texto, perfil)
        alvo = porte(spec, self._container.conhecimento)
        if alvo is None:
            raise ErroDoPedido("o pedido não é Pixel Art: não há referência para ele")
        altura = None if livre is Liberdade.OUSADO else alvo.altura
        exemplo = self._container.referencias.exemplo(alvo.tipo, alvo.corpo, altura)
        if exemplo is None:
            onde = alvo.tipo + (f"/{alvo.corpo}" if alvo.corpo else "")
            raise ErroDoPedido(
                f"não há referência ativa de {onde}: importe e ative um pacote "
                "(python -m assetflow.referencias listar)"
            )
        return exemplo

    # ------------------------------------------------------------------
    # Pedidos da fila
    # ------------------------------------------------------------------
    async def _desenhar_pedido(
        self,
        pedido_id: str,
        *,
        receita: dict[str, Any] | None,
        base: str | None,
        pedido: str | None,
        perfil: str | None,
    ) -> str:
        """Desenha um pedido da fila com o spec gravado nele, sem resolver de novo."""
        if pedido or perfil:
            raise ErroDoPedido(
                "com pedido_id, omita 'pedido' e 'perfil': eles vêm do pedido da fila"
            )
        if receita is None:
            raise ErroDoPedido("falta 'receita': a completa, ou, com base, só o que muda")
        servico = self._container.pedidos
        fila = servico.fila
        try:
            registro = fila.iniciar(pedido_id)
        except ErroDaFila as exc:
            raise ErroDoPedido(str(exc)) from exc

        base = base or (registro.origem_asset_id if registro.tipo is Tipo.AJUSTE else None)
        primeira_linha: str | None = None
        try:
            if base:
                receita, primeira_linha, _ = await self._remendar(base, receita)
            requisicao = await servico.requisicao_do_pedido(registro, receita)
            job = await self._executar(requisicao, resolved=registro.spec)
            if job.status.value != "completed":
                raise ErroDoPedido(
                    job.error.message if job.error else f"o job terminou como {job.status.value}"
                )
        except (ErroDoPedido, GenerationError) as exc:
            mensagem = exc.message if isinstance(exc, GenerationError) else str(exc)
            try:
                fila.desenho_interrompido(pedido_id, nota=f"desenho sem asset: {mensagem}")
            except ErroDaFila:
                pass  # o erro do desenho é o que importa dizer
            raise ErroDoPedido(
                f"{mensagem}\n(o pedido {pedido_id} continua com você: corrija e chame "
                f"desenhar(pedido_id={pedido_id}) de novo)"
            ) from exc

        laudo = await self._laudo(job, registro.texto, primeira_linha)
        asset_id = job.asset.id
        aprovado = job.asset.variants[0].status == "approved"
        dados = {
            "asset_id": asset_id,
            "job_id": job.id,
            "asset_projeto": registro.projeto,
            "laudo": laudo,
        }
        try:
            depois = fila.concluir(pedido_id, **dados) if aprovado else fila.reprovar(pedido_id, **dados)
            situacao = self._situacao_do_pedido(pedido_id, asset_id, depois, aprovado)
        except ErroDaFila as exc:
            situacao = f"pedido {pedido_id}: o desenho saiu, mas a fila não respondeu — {exc}"
        return f"{situacao}\n{laudo}"

    def _situacao_do_pedido(
        self, pedido_id: str, asset_id: str, depois: Pedido | None, aprovado: bool
    ) -> str:
        """A primeira linha do laudo de um pedido: o que aconteceu com ele."""
        if depois is None:
            atual = self._container.pedidos.fila.obter(pedido_id)
            motivo = {
                Situacao.CANCELADO: "foi cancelado na tela durante o desenho",
                Situacao.PENDENTE: "foi devolvido à fila durante o desenho",
                Situacao.CONCLUIDO: f"já tinha sido concluído com {atual.asset_id}",
                Situacao.FALHOU: "já tinha terminado sem aprovação",
            }.get(atual.situacao, "mudou de situação durante o desenho")
            return f"pedido {pedido_id}: {motivo}; {asset_id} ficou avulso, fora do pedido"
        if aprovado:
            return f"pedido {pedido_id}: concluído com {asset_id}; ele já aparece na tela"
        if depois.situacao is Situacao.FALHOU:
            return (
                f"pedido {pedido_id}: falhou — {depois.max_tentativas} desenhos sem "
                "aprovação; o último fica na tela"
            )
        return (
            f"pedido {pedido_id}: não aprovado (tentativa {depois.tentativas} de "
            f"{depois.max_tentativas}); corrija com desenhar(pedido_id={pedido_id}, "
            f"base={asset_id}, receita=<só o que muda>)"
        )

    async def _bloco(self, pedido: Pedido, agora) -> str:
        """Um pedido na resposta de ``pedidos_pendentes``."""
        spec = pedido.spec
        texto = pedido.texto
        base_linha = None
        ajuste = None
        if pedido.tipo is Tipo.AJUSTE:
            ajuste = (pedido.origem_asset_id or "", pedido.texto)
            try:
                origem = await self._registro(pedido.origem_asset_id or "")
                texto = origem.user_prompt
                base_linha = _linha_da_base(origem)
            except ErroDoPedido:
                base_linha = f"base: {pedido.origem_asset_id} (não está mais no histórico)"
        recorte = montar_recorte(
            spec,
            self._container.conhecimento,
            referencias=self._container.referencias,
            liberdade=pedido.liberdade,
            rampas=False,
        )
        consulta = formatar_consulta(
            texto,
            spec.profile_id,
            spec,
            conhecimento=recorte,
            liberdade=pedido.liberdade.value,
            com_formato=False,
        )
        return bloco_do_pedido(
            pedido_id=pedido.id,
            tipo=pedido.tipo.value,
            liberdade=pedido.liberdade.value,
            esperando_min=max(0, int((agora - pedido.criado_em).total_seconds() // 60)),
            consulta=consulta,
            direcao_de_arte=pedido.direcao_de_arte,
            tentativas=pedido.tentativas,
            max_tentativas=pedido.max_tentativas,
            ultimo_asset=pedido.asset_id,
            ajuste=ajuste,
            base=base_linha,
        )

    async def _remendar(
        self, base: str, receita: dict[str, Any] | None
    ) -> tuple[dict[str, Any], str, GenerationRecord]:
        """A receita parcial sobre a receita de ``base``; e a linha do remendo."""
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
            completa, resumo = aplicar_remendo(receita_base, receita)
        except RemendoInvalido as exc:
            raise ErroDoPedido(f"remendo inválido: {exc}") from exc
        return completa, f"remendo de {base}: {resumo.texto()}", registro

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

    async def _executar(self, pedido: AssetGenerationRequest, *, resolved=None):
        """Submete o job e roda o worker até ele terminar.

        O worker roda aqui, e não em segundo plano: o servidor só existe para
        atender a conversa, e cada chamada espera o próprio desenho. Mais de
        uma chamada ao mesmo tempo não trava — cada uma processa o que estiver
        na fila até o seu job terminar.
        """
        try:
            job = await self._service.submit(pedido, resolved=resolved)
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
    def _liberdade(valor: str | None) -> Liberdade:
        """Sem valor, ``fiel``: o comportamento de antes da liberdade existir."""
        if not valor:
            return Liberdade.FIEL
        try:
            return Liberdade(str(valor).strip().lower())
        except ValueError as exc:
            raise ErroDoPedido(
                f"liberdade '{valor}' não existe: use fiel, equilibrado ou ousado"
            ) from exc

    @staticmethod
    def _texto(pedido: str | None) -> str:
        texto = (pedido or "").strip()
        if not texto:
            raise ErroDoPedido("o pedido está vazio: descreva o que desenhar")
        return texto


def _linha_da_base(registro: GenerationRecord) -> str:
    """A base de um ajuste em uma linha: camadas e paleta da receita dela."""
    receita = (registro.engine_options.get(MOTOR) or {}).get("receita") or {}
    camadas = ", ".join(
        str(camada.get("nome") or f"camada {n + 1}")
        for n, camada in enumerate(receita.get("camadas") or [])
    )
    paleta = " ".join(f"{chave} {cor}" for chave, cor in (receita.get("paleta") or {}).items())
    saida = registro.outputs[0] if registro.outputs else None
    partes = [f"base: {registro.asset_id}"]
    if saida is not None:
        partes.append(f"{saida.width}×{saida.height}")
        if saida.status:
            partes.append(saida.status)
    if camadas:
        partes.append(f"camadas: {camadas}")
    if paleta:
        partes.append(f"paleta: {paleta}")
    return " · ".join(partes)
