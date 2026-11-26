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

Fase B2 — ver, corrigir e aprender:

* o ``desenhar`` devolve, junto do laudo, a **imagem do olhar** (ampliada,
  silhueta em preto e tamanho real) e o **olho do app** (os desvios em relação
  às referências do mesmo porte, que só informam);
* num pedido da fila, **aprovado no validador não é pronto**: o pedido espera
  o olhar e só conclui com ``concluir_pedido``. O olhar pode pedir até
  ``settings.pedidos.remendos`` remendos;
* o recorte traz **um exemplo de construção** (um sprite CC0, ou um asset
  com "gostei", convertido para receita) e **as lições** mais repetidas, cada
  um com o seu interruptor; o que foi entregue fica gravado no pedido e no
  asset (``olhar.json``), para medir se ajuda;
* ``registrar_licao`` guarda o que o olhar aprendeu; as opiniões da autora
  ("não gostei" com motivo) chegam no ``pedidos_pendentes`` para virar lição.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..aprendizado import (
    QUALQUER,
    ErroDoAprendizado,
    Opiniao,
    Origem,
    SituacaoDaOpiniao,
    etiquetas_do_spec,
)
from ..aprendizado.modelo import palavras
from ..bootstrap import AppContainer
from ..generation.kernel.exceptions import GenerationError
from ..generation.schemas import (
    AssetGenerationRequest,
    AssetMode,
    AssetOutputOverrides,
    EngineSelector,
)
from ..pedidos import (
    CAMPOS_DO_CONCEITO,
    ErroDaFila,
    Liberdade,
    ModoConceito,
    Pedido,
    Situacao,
    Tipo,
    agora_utc,
    nova_leva,
)
from ..pedidos.custo import tokens_hoje
from ..pedidos.servico import direcao_com_conceito
from ..pixel_knowledge import (
    forma_do_olhar,
    lembrete_da_lista,
    lista_de_verificacao,
    montar_recorte,
    perguntas_da_lista,
    porte,
    rampas_da_base,
)
from ..pixel_knowledge.temas import (
    linha_dos_temas,
    linha_geral_dos_temas,
    regras_que_valem,
    texto_do_tema,
)
from ..referencias.exemplo import (
    FONTE_GOSTEI,
    CandidatoDeGostei,
    ExemploConvertido,
    escolher_exemplo,
    fontes_do_exemplo,
)
from ..referencias.olho import RelatorioDoOlho, olhar_desenho, repete_o_exemplo
from ..storage.records import GenerationRecord
from .ficha import montar_ficha
from .imagem import imagem_do_olhar
from .laudo import (
    MAX_CAMPO_CONCEITO,
    MAX_OLHAR,
    MAX_SIMPLIFICAR,
    TETO_PENDENTES,
    bloco_de_conceito,
    bloco_do_pedido,
    bloco_em_revisao,
    formatar_consulta,
    formatar_laudo,
    formatar_pendentes,
    formato_curto,
    formato_da_receita,
    instrucao_avulsa,
    instrucao_do_pedido,
    secao_de_licoes,
    secao_de_opinioes,
)
from .remendo import RemendoInvalido, aplicar_remendo

__all__ = [
    "MOTOR",
    "PERFIL_PADRAO",
    "PROJETO",
    "ErroDoPedido",
    "Laudo",
    "ServicoDesenhista",
]

#: A gaveta que o MCP pede, sempre pelo nome (plano desenhista §5).
MOTOR = "desenhista-v1"
#: Onde os assets desenhados pela conversa ficam: ``data/assets/projects/mcp/``.
PROJETO = "mcp"
#: Profile de partida quando o Claude não diz qual. Ele só vale no que o texto
#: não disser — é a camada mais fraca da precedência depois do padrão global.
PERFIL_PADRAO = "pixel_character_32"
#: Quantos pedidos ``pedidos_pendentes`` traz, no máximo, de uma vez.
MAXIMO_PENDENTES = 10
#: Quantos assets com "gostei" são lidos do disco para virar exemplo, no máximo.
MAXIMO_GOSTEI = 3
#: Fração de palavras em comum a partir da qual dois conceitos são o mesmo.
CONCEITOS_PARECIDOS = 0.5
#: Teto do motivo da escolha de um conceito (modo "o Claude escolhe").
MAX_MOTIVO_CONCEITO = 200


class ErroDoPedido(Exception):
    """Algo que o Claude precisa corrigir; a mensagem diz o quê, em português."""


class Laudo(str):
    """O laudo em texto, com a imagem do olhar pendurada (``imagem``).

    É um ``str`` para quem só lê o texto; o servidor devolve as duas partes.
    """

    imagem: bytes | None = None
    ampliacao: int | None = None

    @classmethod
    def com_imagem(cls, texto: str, imagem: bytes | None, ampliacao: int | None) -> Laudo:
        laudo = cls(texto)
        laudo.imagem = imagem
        laudo.ampliacao = ampliacao
        return laudo


class ServicoDesenhista:
    """As ferramentas do desenhista, sobre um container já montado."""

    def __init__(self, container: AppContainer, *, timeout_s: float | None = None) -> None:
        self._container = container
        self._service = container.service
        self._caixa = container.aprendizado
        self._config = container.settings.aprendizado
        # O teto do worker já envolve o pipeline inteiro; esperar além dele
        # não faria um job terminar.
        self._timeout_s = timeout_s or (container.settings.worker.job_timeout_s + 30.0)
        # Os grupos de comandos opcionais ligados na gaveta: o formato da
        # receita só cita os que ela aceita.
        ligados = _grupos_ligados(container)
        self._formato_completo = formato_da_receita(ligados)
        self._formato_curto = formato_curto(ligados)
        self._formato_entregue = False
        # O que o último consultar_pedido avulso entregou, por (texto, perfil):
        # o desenho avulso não tem pedido na fila para guardar o envio.
        self._envios: dict[tuple[str, str], dict[str, Any]] = {}

    # ------------------------------------------------------------------
    def _formato(self, *, completo: bool = False) -> str:
        """O formato da receita: inteiro na primeira vez desta conversa, curto depois.

        O servidor MCP é um processo por sessão do Claude Code: "a primeira vez
        neste processo" é a primeira resposta da conversa. ``completo`` (o
        ``formato=true`` do ``consultar_pedido``) o repete.
        """
        if completo or not self._config.formato_uma_vez or not self._formato_entregue:
            self._formato_entregue = True
            return self._formato_completo
        return self._formato_curto

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
        formato: bool = False,
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
        extras, envio, fonte = self._extras(spec, livre, set())
        if self._config.consultar_base:
            temas = linha_dos_temas(self._container.conhecimento, spec, livre.value)
            extras = "\n".join(parte for parte in (extras, temas) if parte)
        if fonte:
            self._exemplo_mostrado(fonte)
        self._envios[(texto, perfil)] = envio
        resposta = formatar_consulta(
            texto,
            perfil,
            spec,
            conhecimento=recorte,
            liberdade=livre.value,
            extras=extras,
            formato=self._formato(completo=formato),
        )
        self._custo(None, entrada=len(resposta))
        return self._com_aviso_de_limite(resposta)

    # ------------------------------------------------------------------
    async def pedidos_pendentes(self, limite: int = 5) -> str:
        """Os pedidos da tela que esperam desenho (ou olhar), já com a consulta de cada um.

        Reserva só os que entram na resposta: o pedido que não couber no teto
        fica na fila, sem reserva, para a próxima chamada. As opiniões novas
        da autora vêm primeiro, para virarem lição.
        """
        limite = max(1, min(int(limite), MAXIMO_PENDENTES))
        fila = self._container.pedidos.fila
        agora = agora_utc()
        try:
            candidatos = fila.candidatos(limite, agora)
        except ErroDaFila as exc:
            raise ErroDoPedido(str(exc)) from exc

        opinioes = await self._opinioes_pendentes()
        rampas = rampas_da_base(self._container.conhecimento)
        if self._config.consultar_base:
            # Lote 8: os temas uma vez só, no topo, e não por pedido.
            geral = linha_geral_dos_temas(self._container.conhecimento)
            rampas = "\n".join(parte for parte in (rampas, geral) if parte)
        # O que vem uma vez só (cabeçalho, formato da receita, rampas,
        # opiniões) entra na conta antes dos pedidos; cada pedido entra
        # inteiro ou não entra.
        total = 400 + len(rampas) + 600 + len(opinioes)
        escolhidos: list[tuple[str, str, dict[str, Any] | None, str | None, bool]] = []
        usadas: set[str] = set()
        for candidato in candidatos:
            bloco, envio, fonte, desenho = await self._bloco(candidato, agora, usadas)
            if escolhidos and total + len(bloco) + 2 > TETO_PENDENTES:
                break
            escolhidos.append((candidato.id, bloco, envio, fonte, desenho))
            if fonte:
                usadas.add(fonte)
            total += len(bloco) + 2

        try:
            reservados = {
                pedido.id
                for pedido in fila.reservar([pid for pid, *_ in escolhidos], nova_leva(), agora)
            }
            for pid, _, envio, fonte, _desenho in escolhidos:
                if pid not in reservados or envio is None:
                    continue
                fila.gravar_envio(pid, envio)
                if fonte:
                    self._exemplo_mostrado(fonte)
            restantes = fila.contar_na_fila(agora)
        except ErroDaFila as exc:
            raise ErroDoPedido(str(exc)) from exc
        entregues = [item for item in escolhidos if item[0] in reservados]
        texto = formatar_pendentes(
            [bloco for _, bloco, *_ in entregues],
            restantes=restantes,
            reserva_min=fila.reserva.total_seconds() / 60,
            rampas=rampas,
            opinioes=opinioes,
            com_formato=any(desenho for *_, desenho in entregues),
            formato=(
                self._formato()
                if any(desenho for *_, desenho in entregues)
                else self._formato_curto
            ),
        )
        if entregues:
            # O que é comum à resposta se divide entre os pedidos dela.
            comum = (len(texto) - sum(len(bloco) for _, bloco, *_ in entregues)) // len(entregues)
            for pid, bloco, *_ in entregues:
                self._custo(pid, entrada=len(bloco) + comum)
        return self._com_aviso_de_limite(texto)

    # ------------------------------------------------------------------
    async def propor_conceitos(
        self,
        pedido_id: str,
        conceitos: list[dict[str, Any]],
        escolhido: int | None = None,
        motivo: str | None = None,
    ) -> str:
        """Os três conceitos de um pedido (lote 1), conferidos antes de gravar."""
        fila = self._container.pedidos.fila
        try:
            pedido = fila.obter(pedido_id)
        except ErroDaFila as exc:
            raise ErroDoPedido(str(exc)) from exc
        limpos = _conceitos_conferidos(conceitos, pedido.conceitos_recusados)
        conceito = None
        direcao = None
        if escolhido is not None or motivo:
            if escolhido is None or not 1 <= int(escolhido) <= 3:
                raise ErroDoPedido("'escolhido' é o número do conceito mais forte, de 1 a 3")
            motivo = (motivo or "").strip()
            if not motivo:
                raise ErroDoPedido("falta 'motivo': por que esse conceito é o mais forte")
            if len(motivo) > MAX_MOTIVO_CONCEITO:
                raise ErroDoPedido(
                    f"'motivo' tem {len(motivo)} caracteres; o teto é {MAX_MOTIVO_CONCEITO}"
                )
            conceito = {**limpos[int(escolhido) - 1], "indice": int(escolhido), "editado": False}
            direcao = direcao_com_conceito(pedido, conceito)
        try:
            depois = fila.gravar_conceitos(
                pedido_id, limpos, escolhido=conceito, motivo=motivo, direcao=direcao
            )
        except ErroDaFila as exc:
            raise ErroDoPedido(str(exc)) from exc

        if conceito is None:
            resposta = (
                f"pedido {pedido_id}: três conceitos na tela, em \"escolha um conceito\". Não "
                "desenhe agora: quando a autora escolher (e talvez editar), o pedido volta à "
                "fila com o conceito como direção de arte."
            )
        else:
            bloco, envio, fonte, _ = await self._bloco(depois, agora_utc(), set())
            if envio is not None:
                fila.gravar_envio(pedido_id, envio)
                if fonte:
                    self._exemplo_mostrado(fonte)
            rampas = rampas_da_base(self._container.conhecimento)
            resposta = "\n".join(
                [
                    (
                        f"pedido {pedido_id}: conceito {escolhido} escolhido — {motivo}. Desenhe "
                        f"agora com desenhar(pedido_id={pedido_id}, receita=...)."
                    ),
                    "",
                    self._formato(),
                    *(["", rampas] if rampas else []),
                    "",
                    bloco,
                ]
            )
        self._custo(
            pedido_id,
            entrada=len(resposta),
            saida_texto=len(json.dumps(limpos, ensure_ascii=False)) + len(motivo or ""),
        )
        return resposta

    # ------------------------------------------------------------------
    async def desenhar(
        self,
        pedido: str | None = None,
        receita: dict[str, Any] | None = None,
        base: str | None = None,
        perfil: str | None = None,
        pedido_id: str | None = None,
    ) -> Laudo:
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

        envio = self._envios.get((texto, perfil))
        olhado = await self._olhar(job, envio)
        falhas = (
            (
                (
                    f"repete o exemplo de construção (silhueta com IoU {_virgula(olhado.iou)}): "
                    "este desenho não vale; desenhe outro do zero"
                ),
            )
            if olhado.iou is not None
            else ()
        )
        aprovado = job.asset.variants[0].status == "approved" and not falhas
        laudo = await self._laudo(
            job,
            texto,
            primeira_linha,
            falhas_extra=falhas,
            olho=olhado.relatorio.linhas(),
            olhar=(
                self._lista(job.resolved_spec, olhado.ampliacao)
                if not base
                else lembrete_da_lista(job.resolved_spec, self._container.conhecimento.olhar)
            ),
            instrucao=instrucao_avulsa(job.asset.id) if aprovado else None,
        )
        await self._gravar_olhar(job, olhado, envio, primeiro_olhar=not base)
        self._custo(
            None,
            entrada=len(laudo),
            saida_receita=len(json.dumps(receita, ensure_ascii=False)) if receita else 0,
            imagens=1,
        )
        return Laudo.com_imagem(laudo, olhado.png, olhado.ampliacao)

    # ------------------------------------------------------------------
    async def concluir(
        self,
        pedido_id: str,
        olhar: str,
        asset_id: str | None = None,
        respostas: dict[str, str] | None = None,
    ) -> str:
        """O olhar terminou: o pedido conclui com um dos desenhos aprovados dele.

        ``respostas`` (lote F5): uma por pergunta da lista do olhar, "sim" ou
        "não: <onde>". Vão para a ficha de verificação do asset.
        """
        olhar = (olhar or "").strip()
        if not olhar:
            raise ErroDoPedido("falta 'olhar': a linha do que você viu no desenho")
        if len(olhar) > MAX_OLHAR:
            raise ErroDoPedido(f"'olhar' tem {len(olhar)} caracteres; o teto é {MAX_OLHAR}")
        try:
            concluido = self._container.pedidos.fila.concluir(
                pedido_id, olhar=olhar, asset_id=asset_id or None
            )
        except ErroDaFila as exc:
            raise ErroDoPedido(str(exc)) from exc
        linhas = [
            (
                f"pedido {pedido_id}: concluído com {concluido.asset_id} depois do olhar; ele já "
                "aparece na tela."
            )
        ]
        sem_licao = self._remendos_sem_licao(concluido)
        if sem_licao:
            linhas.append(
                "remendo sem lição registrada: "
                + ", ".join(sem_licao)
                + " — se o olhar achou algo, registre com registrar_licao(asset_id=...)."
            )
        if self._config.ficha:
            ficha = await self._gravar_ficha(concluido, respostas)
            if ficha is not None:
                faltam = ficha["sem_resposta"]
                if faltam:
                    linhas.append(
                        "ficha: sem resposta para " + ", ".join(faltam)
                        + " — da próxima vez, responda cada pergunta em respostas={...}."
                    )
                for divergencia in ficha["divergencias"]:
                    linhas.append(
                        f"ficha: divergência — você respondeu \"{divergencia['resposta']}\" para "
                        f"{divergencia['pergunta']}, e o app mediu: {divergencia['detalhe']}"
                    )
        resposta = "\n".join(linhas)
        self._custo(
            pedido_id,
            entrada=len(resposta),
            saida_texto=len(olhar) + len(json.dumps(respostas or {}, ensure_ascii=False)),
        )
        return resposta

    async def _gravar_ficha(self, pedido: Pedido, respostas: dict[str, str] | None) -> dict[str, Any] | None:
        """Monta e grava ``000_ficha.json`` do asset que concluiu o pedido (lote F5)."""
        servico = self._container.pedidos
        asset = await servico.asset(pedido.asset_projeto, pedido.job_id)
        if asset is None or not asset.variants:
            return None
        base = self._container.conhecimento
        spec = pedido.spec
        forma = base.formas.get(forma_do_olhar(spec))
        regras = [*(forma.regras if forma else ()), *(base.luz.regras if base.luz else ())]
        if self._config.consultar_base:
            # Lote 8: as regras de tema que o pedido aciona também vão para a ficha.
            for tema in base.temas.values():
                regras.extend(regras_que_valem(tema, spec, pedido.liberdade.value))
        traco = (pedido.conceito or {}).get("traco")
        variante = asset.variants[0]
        try:
            receita = (await self._registro(pedido.asset_id or "")).engine_options.get(MOTOR, {}).get("receita")
        except ErroDoPedido:
            receita = None
        try:
            gostei = self._caixa.opiniao(pedido.asset_id or "")
        except ErroDoAprendizado:
            gostei = None
        ficha = montar_ficha(
            regras=regras,
            perguntas=perguntas_da_lista(spec, base.olhar, traco=traco),
            respostas=respostas,
            olhar=await servico.olhar_do_asset(pedido.asset_projeto, pedido.job_id),
            validacao=await self._json(variante.artifacts.get("validation.json")),
            receita=receita,
            gostei=gostei.gostei if gostei is not None else None,
        )
        ficha["pedido_id"] = pedido.id
        ficha["asset_id"] = pedido.asset_id
        await self._container.storage.persist_artifacts(
            project_id=pedido.asset_projeto,
            job_id=pedido.job_id,
            index=0,
            artifacts={"ficha.json": json.dumps(ficha, ensure_ascii=False, indent=2).encode("utf-8")},
        )
        return ficha

    # ------------------------------------------------------------------
    async def registrar_licao(
        self,
        asset_id: str,
        tema: str,
        errou: str,
        porque: str,
        regra: str,
        geral: bool = False,
        mesma_que: str | None = None,
        da_autora: bool = False,
    ) -> str:
        """Guarda a lição de um olhar; as etiquetas vêm do spec do asset."""
        registro = await self._registro(asset_id)
        try:
            spec = await self._container.pedidos.spec_do_asset(registro)
        except GenerationError as exc:
            raise ErroDoPedido(exc.message) from exc
        tipo, corpo, grade = etiquetas_do_spec(spec)
        if geral:
            tipo = corpo = grade = QUALQUER
        opiniao: Opiniao | None = None
        try:
            if da_autora:
                opiniao = self._caixa.opiniao(asset_id)
                if opiniao is None or opiniao.situacao is SituacaoDaOpiniao.NOTA:
                    raise ErroDoPedido(
                        f"não há opinião pendente da autora sobre {asset_id}: da_autora=true "
                        "só converte um \"não gostei\" com motivo"
                    )
                if opiniao.situacao is SituacaoDaOpiniao.CONVERTIDA:
                    raise ErroDoPedido(
                        f"a opinião sobre {asset_id} já virou a lição L{opiniao.licao}"
                    )
            registrado = self._caixa.registrar(
                errou=errou,
                porque=porque,
                regra=regra,
                tema=tema,
                tipo=tipo,
                corpo=corpo,
                porte=grade,
                origem=Origem.AUTORA if da_autora else Origem.CLAUDE,
                texto_da_autora=opiniao.motivo if opiniao else None,
                asset_id=asset_id,
                pedido_id=self._pedido_do_asset(asset_id),
                mesma_que=mesma_que,
            )
            if opiniao is not None:
                self._caixa.converter(asset_id, registrado.licao.numero)
        except ErroDoAprendizado as exc:
            raise ErroDoPedido(str(exc)) from exc
        etiquetas = f"{registrado.licao.tipo} · {registrado.licao.corpo} · {registrado.licao.porte}"
        resposta = f"{registrado.texto()} · {etiquetas}" + (
            " · da autora, com o texto original guardado ao lado" if da_autora else ""
        )
        if registrado.licao.pedido_id:
            self._custo(
                registrado.licao.pedido_id,
                entrada=len(resposta),
                saida_texto=len(errou) + len(porque) + len(regra),
            )
        return resposta

    # ------------------------------------------------------------------
    async def ver(self, asset_id: str) -> tuple[bytes, str]:
        """A imagem do olhar de um asset (ampliada, silhueta e tamanho real), e uma legenda."""
        registro = await self._registro(asset_id)
        if not registro.outputs:
            raise ErroDoPedido(f"o asset '{asset_id}' não tem arquivo gravado")
        saida = registro.outputs[0]
        png = await self._container.storage.read(saida.uri)
        imagem, ampliacao, _ = imagem_do_olhar(png)
        legenda = (
            f"{asset_id} · {saida.logical_width or saida.width}×{saida.logical_height or saida.height}"
            f" · ampliado {ampliacao}×, silhueta em preto e tamanho real (2× e 1×) · "
            f"{saida.status or 'sem veredito'}"
        )
        self._custo(None, entrada=len(legenda), imagens=1)
        return imagem, legenda

    # ------------------------------------------------------------------
    def consultar_base(
        self,
        tema: str,
        pedido: str | None = None,
        perfil: str | None = None,
        liberdade: str | None = None,
    ) -> str:
        """Um tema da base (lote 8), filtrado pelo pedido quando ele vem."""
        if not self._config.consultar_base:
            raise ErroDoPedido(
                "consultar_base está desligada nesta instalação (ASSETFLOW_CONSULTAR_BASE)"
            )
        temas = self._container.conhecimento.temas
        chave = (tema or "").strip().lower()
        if chave not in temas:
            raise ErroDoPedido(
                f"não há o tema '{tema}' na base; os temas são: {', '.join(temas) or 'nenhum'}"
            )
        spec = self._resolver(self._texto(pedido), self._perfil(perfil)) if pedido else None
        livre = self._liberdade(liberdade)
        resposta = texto_do_tema(temas[chave], spec, livre.value)
        self._custo(None, entrada=len(resposta))
        return resposta

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
        self._custo(None, entrada=len(exemplo[1]), imagens=1)
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
    ) -> Laudo:
        """Desenha um pedido da fila com o spec gravado nele, sem resolver de novo."""
        if pedido or perfil:
            raise ErroDoPedido(
                "com pedido_id, omita 'pedido' e 'perfil': eles vêm do pedido da fila"
            )
        if receita is None:
            raise ErroDoPedido("falta 'receita': a completa, ou, com base, só o que muda")
        servico = self._container.pedidos
        fila = servico.fila
        receita_original = receita
        try:
            registro = fila.iniciar(pedido_id)
        except ErroDaFila as exc:
            raise ErroDoPedido(str(exc)) from exc

        remendo_do_olhar = registro.remendando
        primeiro_olhar = not registro.candidatos and registro.tentativas == 0
        anterior = registro.asset_id if remendo_do_olhar else None
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

        olhado = await self._olhar(job, registro.envio)
        motivo = (
            f"repete o exemplo de construção (IoU {_virgula(olhado.iou)})"
            if olhado.iou is not None
            else None
        )
        asset_id = job.asset.id
        aprovado = job.asset.variants[0].status == "approved" and motivo is None
        laudo_curto = await self._laudo(job, registro.texto, primeira_linha)
        dados = {
            "asset_id": asset_id,
            "job_id": job.id,
            "asset_projeto": registro.projeto,
            "laudo": laudo_curto,
        }
        try:
            depois = (
                fila.aprovar(pedido_id, **dados)
                if aprovado
                else fila.reprovar(pedido_id, **dados, motivo=motivo)
            )
        except ErroDaFila as exc:
            depois = None
            situacao = f"pedido {pedido_id}: o desenho saiu, mas a fila não respondeu — {exc}"
        else:
            situacao = self._situacao_do_pedido(
                pedido_id, asset_id, depois, aprovado, remendo=remendo_do_olhar, anterior=anterior
            )

        instrucao = None
        if depois is not None and depois.situacao is Situacao.EM_REVISAO:
            instrucao = instrucao_do_pedido(
                pedido_id,
                depois.asset_id or asset_id,
                remendos=depois.remendos,
                max_remendos=depois.max_remendos,
                candidatos=depois.candidatos,
            )
        aviso = []
        if remendo_do_olhar and anterior and not self._tem_licao(anterior):
            aviso.append(
                f"o remendo saiu sem lição registrada para {anterior}: se o olhar achou algo, "
                f"registre com registrar_licao(asset_id={anterior}, ...)"
            )
        traco = (registro.conceito or {}).get("traco")
        laudo = await self._laudo(
            job,
            registro.texto,
            primeira_linha,
            falhas_extra=(motivo,) if motivo else (),
            olho=olhado.relatorio.linhas(),
            olhar=(
                self._lista(registro.spec, olhado.ampliacao, traco=traco)
                if primeiro_olhar
                else lembrete_da_lista(
                    registro.spec, self._container.conhecimento.olhar, traco=traco
                )
            ),
            instrucao="\n".join([*aviso, instrucao]) if instrucao else ("\n".join(aviso) or None),
        )
        await self._gravar_olhar(
            job, olhado, registro.envio, primeiro_olhar=primeiro_olhar, pedido_id=pedido_id
        )
        texto = f"{situacao}\n{laudo}"
        self._custo(
            pedido_id,
            entrada=len(texto),
            saida_receita=len(json.dumps(receita_original, ensure_ascii=False)),
            imagens=1,
        )
        return Laudo.com_imagem(texto, olhado.png, olhado.ampliacao)

    def _situacao_do_pedido(
        self,
        pedido_id: str,
        asset_id: str,
        depois: Pedido | None,
        aprovado: bool,
        *,
        remendo: bool = False,
        anterior: str | None = None,
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
        remendos = f"remendos: {depois.remendos} de {depois.max_remendos}"
        if aprovado:
            quem = "remendo aprovado" if remendo else "aprovado"
            return (
                f"pedido {pedido_id}: {quem} no validador com {asset_id}; falta o seu olhar "
                f"({remendos})"
            )
        if remendo and depois.situacao is Situacao.EM_REVISAO:
            return (
                f"pedido {pedido_id}: o remendo {asset_id} não foi aprovado"
                + (f" ({depois.motivo})" if depois.motivo else "")
                + f"; o candidato continua {depois.asset_id or anterior} ({remendos})"
            )
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

    async def _bloco(
        self, pedido: Pedido, agora, usadas: set[str]
    ) -> tuple[str, dict[str, Any] | None, str | None, bool]:
        """Um pedido na resposta de ``pedidos_pendentes``.

        Devolve o bloco, o envio, a fonte do exemplo e se é um bloco de
        desenho (os de olhar e de conceito não pedem o formato da receita).
        """
        esperando = max(0, int((agora - pedido.criado_em).total_seconds() // 60))
        if not pedido.candidatos and pedido.precisa_conceito:
            spec = pedido.spec
            logica = spec.logical_resolution
            tipo, corpo, _grade = etiquetas_do_spec(spec)
            paleta = spec.palette
            cores = (
                f"até {paleta.max_colors} cores" if paleta is not None and paleta.max_colors else "cores livres"
            )
            resumo = (
                f"pedido: {pedido.texto} · {tipo}"
                + (f" · corpo {corpo}" if corpo != QUALQUER else "")
                + f" · grade {logica.width}×{logica.height} · {cores}"
            )
            bloco = bloco_de_conceito(
                pedido_id=pedido.id,
                modo=pedido.modo_conceito.value,
                liberdade=pedido.liberdade.value,
                esperando_min=esperando,
                resumo=resumo,
                largura=logica.width,
                altura=logica.height,
                direcao_de_arte=pedido.direcao_de_arte,
                recusados=pedido.conceitos_recusados,
                banca=pedido.banca,
            )
            return bloco, None, None, False
        if pedido.candidatos:
            # Já há desenho aprovado: falta só o olhar. Nada de exemplo nem
            # lição — o envio do primeiro desenho continua valendo.
            bloco = bloco_em_revisao(
                pedido_id=pedido.id,
                texto=pedido.texto,
                candidato=pedido.asset_id or pedido.candidatos[-1],
                remendos=pedido.remendos,
                max_remendos=pedido.max_remendos,
                esperando_min=esperando,
            )
            return bloco, None, None, False
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
        extras, envio, fonte = self._extras(spec, pedido.liberdade, usadas)
        consulta = formatar_consulta(
            texto,
            spec.profile_id,
            spec,
            conhecimento=recorte,
            liberdade=pedido.liberdade.value,
            com_formato=False,
            extras=extras,
        )
        bloco = bloco_do_pedido(
            pedido_id=pedido.id,
            tipo=pedido.tipo.value,
            liberdade=pedido.liberdade.value,
            esperando_min=esperando,
            consulta=consulta,
            direcao_de_arte=pedido.direcao_de_arte,
            tentativas=pedido.tentativas,
            max_tentativas=pedido.max_tentativas,
            ultimo_asset=pedido.asset_id,
            ajuste=ajuste,
            base=base_linha,
            conceito_por=(
                None
                if pedido.conceito is None
                else ("pelo Claude" if pedido.modo_conceito is ModoConceito.CLAUDE_ESCOLHE else "pela autora")
            ),
            banca=pedido.banca,
        )
        return bloco, envio, fonte, True

    async def _opinioes_pendentes(self) -> str:
        try:
            pendentes = self._caixa.pendentes()
        except ErroDoAprendizado as exc:
            return f"opiniões da autora: indisponíveis ({exc})"
        itens = []
        for opiniao in pendentes:
            try:
                prompt = (await self._registro(opiniao.asset_id)).user_prompt
            except ErroDoPedido:
                prompt = "fora do histórico"
            itens.append((opiniao.asset_id, prompt, opiniao.motivo or ""))
        return secao_de_opinioes(itens)

    # ------------------------------------------------------------------
    # Exemplo de construção e lições (Fase B2)
    # ------------------------------------------------------------------
    def _extras(
        self, spec: Any, liberdade: Liberdade, usadas: set[str]
    ) -> tuple[str, dict[str, Any], str | None]:
        """O exemplo e as lições do recorte, o envio para gravar e a fonte do exemplo."""
        ligado_exemplo = bool(self._config.exemplo)
        ligado_licoes = bool(self._config.licoes)
        envio: dict[str, Any] = {
            "liberdade": liberdade.value,
            "exemplo_ligado": ligado_exemplo,
            "licoes_ligadas": ligado_licoes,
            "exemplo": None,
            "licoes": [],
        }
        alvo = porte(spec, self._container.conhecimento)
        if alvo is None:
            return "", envio, None
        ousado = liberdade is Liberdade.OUSADO
        logica = spec.logical_resolution
        grade = f"{logica.width}x{logica.height}"
        partes: list[str] = []
        fonte = None

        if ligado_exemplo:
            exemplo = self._exemplo(alvo, grade, ousado, usadas)
            if exemplo is not None:
                partes.append(exemplo.texto)
                envio["exemplo"] = exemplo.como_dict()
                fonte = exemplo.fonte

        if ligado_licoes:
            try:
                licoes = self._caixa.escolher(
                    tipo=alvo.tipo,
                    corpo=alvo.corpo,
                    porte=grade,
                    so_tecnica=ousado,
                    peso_autora=self._config.peso_autora,
                    maximo=self._config.max_licoes,
                )
            except ErroDoAprendizado as exc:
                partes.append(f"lições: indisponíveis ({exc})")
                licoes = []
            secao = secao_de_licoes(
                [(l.id, l.contador, l.origem.value, l.regra) for l in licoes], so_tecnica=ousado
            )
            if secao:
                partes.append(secao)
                mostradas = {linha.split(" ", 2)[1] for linha in secao.splitlines()[1:]}
                envio["licoes"] = [
                    {"id": l.id, "contador": l.contador, "origem": l.origem.value}
                    for l in licoes
                    if l.id in mostradas
                ]
        return "\n".join(partes), envio, fonte

    def _exemplo(
        self, alvo: Any, grade: str, ousado: bool, usadas: set[str]
    ) -> ExemploConvertido | None:
        referencias = self._container.referencias
        fontes = fontes_do_exemplo(
            referencias,
            alvo.tipo,
            alvo.corpo,
            alvo.altura,
            por_estilo=ousado,
            so_bons=self._config.exemplo_so_bons,
        )
        gostei = self._gostei(alvo, grade)
        nomes = list(fontes) + ([FONTE_GOSTEI] if gostei else [])
        if not nomes:
            return None
        try:
            ordem = self._caixa.ordem_das_fontes(nomes)
        except ErroDoAprendizado:
            ordem = sorted(nomes)
        # Na mesma resposta, uma fonte já usada vai para o fim: pedidos
        # seguidos recebem exemplos de pacotes diferentes.
        ordem = [f for f in ordem if f not in usadas] + [f for f in ordem if f in usadas]
        return escolher_exemplo(referencias, fontes, ordem, gostei=gostei)

    def _gostei(self, alvo: Any, grade: str) -> list[CandidatoDeGostei]:
        """Os assets com "gostei" do mesmo tipo, corpo e grade, lidos do disco local."""
        try:
            opinioes = self._caixa.gostei(tipo=alvo.tipo, corpo=alvo.corpo, porte=grade)
        except ErroDoAprendizado:
            return []
        storage = self._container.storage
        raiz = getattr(storage.backend, "root", None)
        por_asset = {opiniao.asset_id for opiniao in opinioes[:MAXIMO_GOSTEI]}
        if raiz is None or not por_asset:
            return []
        candidatos = []
        # O consultar é síncrono e o repositório do histórico é assíncrono:
        # o histórico é lido direto do arquivo, como o repositório o lê.
        for registro in self._registros_sincronos():
            if registro.asset_id in por_asset and registro.outputs:
                chave = storage.backend.key_from_uri(registro.outputs[0].uri)
                if not chave:
                    continue
                try:
                    with Image.open(Path(raiz) / chave) as imagem:
                        rgba = np.asarray(imagem.convert("RGBA")).copy()
                except OSError:
                    continue
                rgba[rgba[..., 3] < 128] = 0
                candidatos.append(CandidatoDeGostei(asset_id=registro.asset_id, rgba=rgba))
        return candidatos

    def _registros_sincronos(self) -> list[GenerationRecord]:
        """O histórico lido direto do arquivo (o ``consultar`` é síncrono)."""
        caminho = self._container.settings.history_path
        if not caminho.is_file():
            return []
        registros = []
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            try:
                registros.append(GenerationRecord.do_historico(json.loads(linha)))
            except (ValueError, TypeError):
                continue
        return registros

    def _exemplo_mostrado(self, fonte: str) -> None:
        try:
            self._caixa.exemplo_mostrado(fonte)
        except ErroDoAprendizado:
            pass  # a rotação é conforto; o exemplo já foi entregue

    def _tem_licao(self, asset_id: str) -> bool:
        try:
            return any(
                licao.asset_id == asset_id or asset_id in licao.assets
                for licao in self._caixa.listar()
            )
        except ErroDoAprendizado:
            return True  # sem como saber, não acusa

    def _remendos_sem_licao(self, pedido: Pedido) -> list[str]:
        """Os candidatos que foram remendados (todos menos o último) e não têm lição."""
        remendados = list(pedido.candidatos[:-1]) if len(pedido.candidatos) > 1 else []
        return [asset for asset in remendados if not self._tem_licao(asset)]

    def _pedido_do_asset(self, asset_id: str) -> str | None:
        try:
            for pedido in self._container.pedidos.fila.listar(limite=300):
                if asset_id in pedido.candidatos or pedido.asset_id == asset_id:
                    return pedido.id
        except ErroDaFila:
            return None
        return None

    # ------------------------------------------------------------------
    # O olhar: imagem, olho do app, guarda do exemplo
    # ------------------------------------------------------------------
    async def _olhar(self, job, envio: dict[str, Any] | None) -> _Olhado:
        variante = job.asset.variants[0]
        png = await self._container.storage.read(variante.uri)
        with Image.open(io.BytesIO(png)) as aberta:
            rgba = np.asarray(aberta.convert("RGBA")).copy()
        rgba[rgba[..., 3] < 128] = 0
        saida_motor = await self._json(variante.artifacts.get("engine_output.json"))
        mapa_bruto = ((saida_motor or {}).get("engine_metadata") or {}).get("mapa_de_camadas")
        mapa = (
            (mapa_bruto.get("nomes") or [], mapa_bruto.get("linhas") or [])
            if isinstance(mapa_bruto, dict)
            else None
        )
        spec = job.resolved_spec
        alvo = porte(spec, self._container.conhecimento)
        referencias = self._container.referencias
        relatorio = olhar_desenho(
            rgba,
            referencias,
            tipo=alvo.tipo if alvo else str(getattr(spec.asset.type, "value", spec.asset.type)),
            corpo=alvo.corpo if alvo else None,
            altura_do_corpo=alvo.altura if alvo else None,
            mapa_de_camadas=mapa,
        )
        exemplo = (envio or {}).get("exemplo") or {}
        iou = repete_o_exemplo(rgba, exemplo.get("px") or (), referencias.configuracao.olho.iou_copia)
        imagem, ampliacao, _ = imagem_do_olhar(png)
        return _Olhado(png=imagem, ampliacao=ampliacao, relatorio=relatorio, iou=iou)

    def _lista(self, spec: Any, ampliacao: int, *, traco: str | None = None) -> str:
        base = self._container.conhecimento
        luz = base.luz.padrao if base.luz is not None else None
        return lista_de_verificacao(
            spec,
            base.olhar,
            ampliacao=ampliacao,
            luz_padrao=luz,
            traco=traco,
            curta=bool(self._config.lista_curta),
        )

    def _custo(self, pedido_id: str | None, **partes: int) -> None:
        """Soma o que passou pela conversa (lote 1; lote 12: datado, e também o avulso)."""
        try:
            self._container.pedidos.fila.somar_custo(pedido_id, **partes)
        except ErroDaFila:
            pass  # a conta é registro; o desenho não depende dela

    def _com_aviso_de_limite(self, resposta: str) -> str:
        """Uma linha no topo quando o limite diário de tokens foi atingido (lote 12)."""
        limite = self._container.settings.custo.limite_diario
        if not limite:
            return resposta
        try:
            hoje = tokens_hoje(self._container.pedidos.fila)
        except ErroDaFila:
            return resposta
        if hoje < limite:
            return resposta
        def milhar(n: int) -> str:
            return f"{n:,}".replace(",", ".")

        return (
            f"aviso: hoje já passaram ~{milhar(hoje)} tokens estimados pela conversa, e o "
            f"limite diário da autora é {milhar(limite)} (ASSETFLOW_LIMITE_DIARIO_TOKENS) — "
            "prefira remendos curtos e pergunte antes de começar pedidos novos.\n\n"
            + resposta
        )

    async def _gravar_olhar(
        self,
        job,
        olhado: _Olhado,
        envio: dict[str, Any] | None,
        *,
        primeiro_olhar: bool,
        pedido_id: str | None = None,
    ) -> None:
        """``olhar.json`` ao lado do PNG: o olho, o que foi entregue e a guarda."""
        documento = {
            "pedido_id": pedido_id,
            "primeiro_olhar": primeiro_olhar,
            "olho": olhado.relatorio.como_dict(),
            "repete_o_exemplo": olhado.iou,
            "envio": envio,
        }
        await self._container.storage.persist_artifacts(
            project_id=job.asset.project_id,
            job_id=job.id,
            index=0,
            artifacts={"olhar.json": json.dumps(documento, ensure_ascii=False, indent=2).encode("utf-8")},
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

    async def _laudo(
        self,
        job,
        texto: str,
        primeira_linha: str | None,
        *,
        falhas_extra: tuple[str, ...] = (),
        olho: list[str] | None = None,
        olhar: str | None = None,
        instrucao: str | None = None,
    ) -> str:
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
            falhas_extra=falhas_extra,
            olho=olho,
            olhar=olhar,
            instrucao=instrucao,
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


class _Olhado:
    """O que ``_olhar`` produz: a imagem, a ampliação, o olho e a guarda."""

    __slots__ = ("ampliacao", "iou", "png", "relatorio")

    def __init__(
        self, *, png: bytes, ampliacao: int, relatorio: RelatorioDoOlho, iou: float | None
    ) -> None:
        self.png = png
        self.ampliacao = ampliacao
        self.relatorio = relatorio
        self.iou = iou


def _grupos_ligados(container: AppContainer) -> set[str]:
    """Os grupos de comandos opcionais que a gaveta aceita (``comandos_<grupo>``)."""
    from ..settings import engine_runtime_configs

    try:
        opcoes = engine_runtime_configs(container.settings)[MOTOR].options
    except (KeyError, ValueError):
        return set()
    grupos = {"cor_e_luz", "construcao", "linha", "acabamento"}
    return {g for g in grupos if bool(opcoes.get(f"comandos_{g}", True))}


def _conceitos_conferidos(
    conceitos: Any, recusados: tuple[dict[str, Any], ...]
) -> list[dict[str, str]]:
    """Os três conceitos limpos, ou o erro que diz o que corrigir.

    Confere formato, tamanho, a diferença entre os três (menos da metade das
    palavras de traço, silhueta e objeto em comum) e que nenhum repita um
    recusado. Se um conceito "serve para qualquer personagem", só quem lê sabe:
    isso fica com a autora e com a pergunta do olhar.
    """
    if not isinstance(conceitos, list) or len(conceitos) != 3:
        raise ErroDoPedido("mande exatamente 3 conceitos")
    limpos: list[dict[str, str]] = []
    for n, bruto in enumerate(conceitos, start=1):
        if not isinstance(bruto, dict):
            raise ErroDoPedido(f"o conceito {n} não é um objeto com {', '.join(CAMPOS_DO_CONCEITO)}")
        limpo = {}
        for campo in CAMPOS_DO_CONCEITO:
            valor = str(bruto.get(campo) or "").strip()
            teto = MAX_SIMPLIFICAR if campo == "simplificar" else MAX_CAMPO_CONCEITO
            if not valor:
                raise ErroDoPedido(f"falta '{campo}' no conceito {n}")
            if len(valor) > teto:
                raise ErroDoPedido(
                    f"'{campo}' do conceito {n} tem {len(valor)} caracteres; o teto é {teto}"
                )
            limpo[campo] = valor
        limpos.append(limpo)

    def nucleo(conceito: dict[str, Any]) -> frozenset[str]:
        return palavras(" ".join(str(conceito.get(c, "")) for c in ("traco", "silhueta", "objeto")))

    for i in range(3):
        for j in range(i + 1, 3):
            a, b = nucleo(limpos[i]), nucleo(limpos[j])
            if a and b and len(a & b) / len(a | b) >= CONCEITOS_PARECIDOS:
                raise ErroDoPedido(
                    f"os conceitos {i + 1} e {j + 1} são parecidos demais: troque um por uma ideia "
                    "de outra natureza"
                )
    for n, conceito in enumerate(limpos, start=1):
        for velho in recusados:
            a, b = nucleo(conceito), nucleo(velho)
            if a and b and len(a & b) / len(a | b) >= CONCEITOS_PARECIDOS:
                raise ErroDoPedido(
                    f"o conceito {n} repete um que a autora recusou (\"{velho.get('traco')}\"): "
                    "proponha outro"
                )
    return limpos


def _virgula(valor: float | None) -> str:
    return f"{valor:.2f}".replace(".", ",") if valor is not None else "?"


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
