"""Da tela para a fila: montar, pré-visualizar e criar pedidos.

O pedido de geração de um pedido da tela é montado **num lugar só**
(:meth:`ServicoDePedidos.requisicao`), e é o mesmo para as três coisas que o
usam: a pré-visualização que a tela mostra, a resolução do spec gravado na
criação, e o desenho que o Claude faz depois. Ele leva o projeto padrão, o
gerador do app pedido pelo nome e sem fallback, e uma variação — a tela não
escolhe motor nem projeto.

O spec é resolvido **uma vez**, na criação, e gravado na leitura do pedido. O
desenho executa esse spec, sem resolver de novo: mudar a taxonomia ou a base
de conhecimento entre criar e desenhar não muda o que foi pedido.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from ..generation.kernel.exceptions import InvalidGenerationRequest
from ..generation.schemas import (
    AssetFlowModel,
    AssetGenerationRequest,
    AssetOutputOverrides,
    AssetType,
    EngineSelector,
    FinalResolvedSpec,
    GeneratedAsset,
    PromptPreview,
    SemanticPrompt,
    SpecOverrides,
)
from ..generation.service import GenerationService
from ..pixel_knowledge import Liberdade
from ..storage.asset_storage import AssetStorageService
from ..storage.records import GenerationRecord
from ..storage.repository import GenerationRecordRepository
from .fila import FilaDePedidos
from .modelo import Pedido, Tipo

__all__ = ["CorpoDoPedido", "ServicoDePedidos"]


class CorpoDoPedido(AssetFlowModel):
    """O que a tela manda. Sem motor e sem projeto: os dois são do app.

    Um pedido de **desenho** traz a descrição e os controles, como a
    pré-visualização. Um **ajuste** traz ``origem_asset_id`` e ``texto`` (o que
    mudar). Os dois trazem a liberdade e, se houver, a direção de arte.
    """

    prompt: str = ""
    profile: str | None = None
    capability: str | None = None
    asset_type: AssetType | None = None
    output: AssetOutputOverrides = Field(default_factory=AssetOutputOverrides)
    spec_overrides: SpecOverrides | None = None
    semantic_prompt: SemanticPrompt | None = None
    origem_asset_id: str | None = None
    texto: str | None = None
    liberdade: Liberdade = Liberdade.EQUILIBRADO
    direcao_de_arte: str | None = Field(default=None, max_length=2000)

    @property
    def e_ajuste(self) -> bool:
        return bool(self.origem_asset_id)


class ServicoDePedidos:
    """Cria pedidos e monta, para o desenho, o pedido de geração de cada um."""

    def __init__(
        self,
        fila: FilaDePedidos,
        service: GenerationService,
        storage: AssetStorageService,
        records: GenerationRecordRepository | None,
        *,
        projeto: str,
        gerador: str | None,
    ) -> None:
        self.fila = fila
        self._service = service
        self._storage = storage
        self._records = records
        self.projeto = projeto
        self._gerador = gerador

    @property
    def gerador(self) -> str:
        if not self._gerador:
            raise InvalidGenerationRequest(
                "o engines.yaml não define o gerador do app (chave 'gerador'): "
                "sem ele, um pedido não tem quem o desenhe"
            )
        return self._gerador

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------
    def requisicao(
        self,
        corpo: CorpoDoPedido,
        *,
        projeto: str | None = None,
        semantica: SemanticPrompt | None = None,
        receita: dict[str, Any] | None = None,
    ) -> AssetGenerationRequest:
        """O pedido de geração de um pedido de desenho, montado num lugar só."""
        if corpo.e_ajuste:
            raise InvalidGenerationRequest("um ajuste não tem pré-visualização de desenho novo")
        variacoes = corpo.output.variations
        if variacoes not in (None, 1):
            raise InvalidGenerationRequest(
                "um pedido é um desenho: para mais de uma variação, faça mais pedidos"
            )
        return AssetGenerationRequest(
            project_id=projeto or self.projeto,
            profile=corpo.profile,
            capability=corpo.capability,
            prompt=corpo.prompt,
            asset_type=corpo.asset_type,
            output=corpo.output.model_copy(update={"variations": 1}),
            spec_overrides=corpo.spec_overrides,
            semantic_prompt=semantica or corpo.semantic_prompt,
            engine=EngineSelector(mode="manual", engine_id=self.gerador, allow_fallback=False),
            engine_options={self.gerador: {"receita": receita}} if receita is not None else {},
        )

    def previa(self, corpo: CorpoDoPedido) -> PromptPreview:
        """O que a tela mostra: o mesmo spec que a criação vai gravar."""
        return self._service.preview_prompt(self.requisicao(corpo))

    # ------------------------------------------------------------------
    # Criação
    # ------------------------------------------------------------------
    async def criar(self, corpo: CorpoDoPedido) -> Pedido:
        if corpo.e_ajuste:
            return await self._criar_ajuste(corpo)
        texto = corpo.prompt.strip()
        if not texto:
            raise InvalidGenerationRequest("o pedido precisa de uma descrição")
        previa = self.previa(corpo)
        return self.fila.criar(
            tipo=Tipo.DESENHO,
            projeto=self.projeto,
            texto=texto,
            liberdade=corpo.liberdade.value,
            direcao_de_arte=_texto_ou_nada(corpo.direcao_de_arte),
            corpo=corpo.model_dump(mode="json", exclude_none=True),
            leitura=previa.model_dump(mode="json"),
        )

    async def _criar_ajuste(self, corpo: CorpoDoPedido) -> Pedido:
        texto = (corpo.texto or "").strip()
        if not texto:
            raise InvalidGenerationRequest("um ajuste precisa dizer o que mudar")
        registro = await self.registro(corpo.origem_asset_id or "")
        receita = (registro.engine_options.get(self.gerador) or {}).get("receita")
        if not isinstance(receita, dict):
            raise InvalidGenerationRequest(
                f"o asset '{corpo.origem_asset_id}' não foi desenhado pela "
                f"{self.gerador}: não há receita para ajustar"
            )
        spec = await self.spec_do_asset(registro)
        leitura = {
            "resolved": spec.model_dump(mode="json"),
            "semantic": registro.semantic_prompt.model_dump(mode="json")
            if registro.semantic_prompt
            else None,
        }
        return self.fila.criar(
            tipo=Tipo.AJUSTE,
            projeto=self.projeto,
            texto=texto,
            liberdade=corpo.liberdade.value,
            direcao_de_arte=_texto_ou_nada(corpo.direcao_de_arte),
            corpo=corpo.model_dump(mode="json", exclude_none=True),
            leitura=leitura,
            origem_asset_id=registro.asset_id,
        )

    # ------------------------------------------------------------------
    # Para o desenho (o MCP) e para a tela (a API)
    # ------------------------------------------------------------------
    async def requisicao_do_pedido(
        self, pedido: Pedido, receita: dict[str, Any]
    ) -> AssetGenerationRequest:
        """O pedido de geração do desenho de ``pedido``, com a receita."""
        if pedido.tipo is Tipo.DESENHO:
            corpo = CorpoDoPedido.model_validate(pedido.corpo)
            return self.requisicao(
                corpo, projeto=pedido.projeto, semantica=pedido.semantica, receita=receita
            )
        registro = await self.registro(pedido.origem_asset_id or "")
        return AssetGenerationRequest(
            project_id=pedido.projeto,
            profile=pedido.spec.profile_id,
            prompt=registro.user_prompt,
            output=AssetOutputOverrides(variations=1),
            semantic_prompt=pedido.semantica,
            engine=EngineSelector(mode="manual", engine_id=self.gerador, allow_fallback=False),
            engine_options={self.gerador: {"receita": receita}},
        )

    async def registro(self, asset_id: str) -> GenerationRecord:
        """O registro de um asset no histórico (varredura; a Fase C indexa)."""
        if self._records is not None and asset_id:
            for registro in await self._records.list(limit=1_000_000):
                if registro.asset_id == asset_id:
                    return registro
        raise InvalidGenerationRequest(f"não há asset '{asset_id}' no histórico")

    async def asset(self, projeto: str | None, job_id: str | None) -> GeneratedAsset | None:
        """O ``asset.json`` de um job; ``None`` se o arquivo não estiver lá."""
        if not projeto or not job_id:
            return None
        try:
            bruto = await self._storage.backend.get(f"projects/{projeto}/jobs/{job_id}/asset.json")
        except Exception:  # noqa: BLE001 - arquivo ausente não derruba a lista
            return None
        return GeneratedAsset.model_validate_json(bruto)

    async def spec_do_asset(self, registro: GenerationRecord) -> FinalResolvedSpec:
        """O spec com que um asset foi desenhado, do artefato gravado no job."""
        asset = await self.asset(registro.project_id, registro.job_id)
        uri = None
        if asset is not None and asset.variants:
            uri = asset.variants[0].artifacts.get("resolved_spec.json")
        if not uri:
            raise InvalidGenerationRequest(
                f"o asset '{registro.asset_id}' não guardou o spec do desenho: não dá "
                "para ajustá-lo pela fila"
            )
        documento = json.loads(await self._storage.read(uri))
        documento.pop("raw_prompt", None)  # o artefato guarda a frase junto do spec
        return FinalResolvedSpec.model_validate(documento)


def _texto_ou_nada(valor: str | None) -> str | None:
    valor = (valor or "").strip()
    return valor or None
