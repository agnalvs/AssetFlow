"""O editor de pixels da tela (lote 5, FUNDAMENTOS_E_FERRAMENTAS §6).

A autora troca alguns pixels de um asset pronto com o mouse, e a troca vira um
**remendo**: uma camada nova no fim da receita da base (``retoque_N``), com um
``px`` sobre o retângulo do que mudou (``.`` mantém, ``-`` apaga, a chave
pinta). O desenho passa pelo caminho de sempre — a gaveta pelo nome e sem
fallback, pós-processamento, Optimizer, validador — e sai um asset novo; a base
fica como era. Nenhum token: o Claude não é chamado.

Aprovado, o resultado vira um pedido de ajuste já concluído na fila
(``FilaDePedidos.registrar_edicao``), para aparecer em "Prontos" com o vínculo
de origem. Com "o que estava errado", a edição grava um "não gostei" com esse
motivo no asset original, e o Claude o converte em lição na próxima conversa.

Este módulo não importa API, MCP, gaveta nem jobs (tests/test_architecture_
boundaries.py): lê a receita do histórico e o PNG do storage, e submete pelo
``GenerationService`` com a requisição que o ``ServicoDePedidos`` monta.
"""

from __future__ import annotations

import asyncio
import copy
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from io import BytesIO
from typing import TYPE_CHECKING, Any

from PIL import Image

from ..aprendizado import etiquetas_do_spec
from ..generation.kernel.exceptions import GenerationError, InvalidGenerationRequest
from ..pedidos import Pedido, Situacao

if TYPE_CHECKING:  # pragma: no cover - só tipos
    from ..bootstrap import AppContainer

__all__ = [
    "DESLIGADO",
    "PREFIXO",
    "DadosDoEditor",
    "ResultadoDaEdicao",
    "ServicoDoEditor",
    "Troca",
    "camada_de_retoque",
    "grade_do_png",
]

#: O nome das camadas que o editor acrescenta: ``retoque_1``, ``retoque_2``…
PREFIXO = "retoque_"
#: A frase das duas rotas quando ``ASSETFLOW_EDITOR`` está desligado.
DESLIGADO = "o editor de pixels está desligado nesta instalação (ASSETFLOW_EDITOR)"
#: Até quanto uma cor do PNG final pode diferir da chave e ainda contar como a
#: mesma: o pós-processamento pode ajustar a cor em uma unidade.
TOLERANCIA = 8
_MANTER, _APAGAR = ".", "-"


@dataclass(frozen=True, slots=True)
class Troca:
    """Um pixel trocado: ``cor`` é uma chave da paleta, ou ``None`` para apagar."""

    x: int
    y: int
    cor: str | None


@dataclass(frozen=True, slots=True)
class DadosDoEditor:
    """O que a tela precisa para editar: a grade lógica e a paleta."""

    pedido_id: str
    asset_id: str
    largura: int
    altura: int
    #: Chave -> ``#rrggbb``.
    paleta: dict[str, str]
    #: Linha a linha, ``#rrggbb`` ou ``None`` (transparente).
    pixels: list[list[str | None]]


@dataclass(slots=True)
class ResultadoDaEdicao:
    aprovado: bool
    asset_id: str
    mudados: int
    ficaram: int
    camada: str
    #: O pedido de ajuste concluído (só quando aprovado).
    pedido: Pedido | None = None
    #: Por que não aprovou, em português.
    motivo: str | None = None
    avisos: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------
# Funções puras
# ----------------------------------------------------------------------
def grade_do_png(png: bytes, largura: int, altura: int) -> list[list[str | None]]:
    """A grade lógica de um PNG: ``#rrggbb`` por pixel, ``None`` no transparente.

    Um PNG ampliado por inteiro é amostrado no vizinho mais próximo.
    """
    imagem = Image.open(BytesIO(png)).convert("RGBA")
    if imagem.size != (largura, altura):
        imagem = imagem.resize((largura, altura), Image.Resampling.NEAREST)
    pixels = imagem.load()
    return [
        [
            None if pixels[x, y][3] < 128 else "#{:02x}{:02x}{:02x}".format(*pixels[x, y][:3])
            for x in range(largura)
        ]
        for y in range(altura)
    ]


def camada_de_retoque(
    receita: Mapping[str, Any],
    trocas: Sequence[Troca],
    *,
    largura: int,
    altura: int,
    paleta: Mapping[str, str],
) -> tuple[dict[str, Any], dict[tuple[int, int], str | None]]:
    """A camada ``retoque_N`` com as trocas, e as trocas finais por posição.

    Uma troca repetida vale a última. Fora da grade ou fora da paleta é erro
    em português.
    """
    if not trocas:
        raise InvalidGenerationRequest("nenhum pixel mudou: não há o que salvar")
    finais: dict[tuple[int, int], str | None] = {}
    for troca in trocas:
        if not (0 <= troca.x < largura and 0 <= troca.y < altura):
            raise InvalidGenerationRequest(
                f"o pixel ({troca.x}, {troca.y}) está fora da grade {largura}×{altura}"
            )
        if troca.cor is not None and troca.cor not in paleta:
            raise InvalidGenerationRequest(
                f"a cor '{troca.cor}' não está na paleta do asset "
                f"({', '.join(sorted(paleta))}): o editor só usa as cores do desenho"
            )
        finais[(troca.x, troca.y)] = troca.cor

    xs = [x for x, _ in finais]
    ys = [y for _, y in finais]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    linhas = []
    for y in range(y0, y1 + 1):
        linha = []
        for x in range(x0, x1 + 1):
            if (x, y) not in finais:
                linha.append(_MANTER)
            else:
                cor = finais[(x, y)]
                linha.append(_APAGAR if cor is None else cor)
        linhas.append("".join(linha))

    nomes = {
        camada.get("nome")
        for camada in receita.get("camadas") or []
        if isinstance(camada, Mapping)
    }
    numero = 1
    while f"{PREFIXO}{numero}" in nomes:
        numero += 1
    camada = {"nome": f"{PREFIXO}{numero}", "ops": [{"px": linhas, "em": [x0, y0]}]}
    return camada, finais


def _mesma_cor(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return all(
        abs(int(a[i : i + 2], 16) - int(b[i : i + 2], 16)) <= TOLERANCIA for i in (1, 3, 5)
    )


# ----------------------------------------------------------------------
# O serviço
# ----------------------------------------------------------------------
class ServicoDoEditor:
    """Abre um asset pronto para editar e salva a edição como remendo."""

    def __init__(self, container: AppContainer) -> None:
        self._container = container
        self._pedidos = container.pedidos
        self._timeout_s = container.settings.worker.job_timeout_s + 30.0

    @property
    def ligado(self) -> bool:
        return self._container.settings.pedidos.editor

    async def abrir(self, pedido_id: str) -> DadosDoEditor:
        base = await self._base(pedido_id)
        png = await self._container.storage.read(base.variante.uri)
        return DadosDoEditor(
            pedido_id=pedido_id,
            asset_id=base.registro.asset_id,
            largura=base.largura,
            altura=base.altura,
            paleta=base.paleta,
            pixels=grade_do_png(png, base.largura, base.altura),
        )

    async def salvar(
        self, pedido_id: str, trocas: Sequence[Troca], motivo: str | None = None
    ) -> ResultadoDaEdicao:
        base = await self._base(pedido_id)
        motivo = (motivo or "").strip() or None
        camada, finais = camada_de_retoque(
            base.receita, trocas, largura=base.largura, altura=base.altura, paleta=base.paleta
        )
        completa = copy.deepcopy(dict(base.receita))
        completa["camadas"] = [*(completa.get("camadas") or []), camada]

        spec = await self._pedidos.spec_do_asset(base.registro)
        requisicao = self._pedidos.requisicao_de_ajuste(
            registro=base.registro,
            profile_id=spec.profile_id,
            semantica=base.registro.semantic_prompt,
            receita=completa,
        )
        job = await self._executar(requisicao, spec)
        if job.status.value != "completed":
            mensagem = job.error.message if job.error else f"o job terminou como {job.status.value}"
            raise InvalidGenerationRequest(f"a edição não foi desenhada: {mensagem}")

        variante = job.asset.variants[0]
        final = grade_do_png(
            await self._container.storage.read(variante.uri), base.largura, base.altura
        )
        ficaram = sum(
            1
            for (x, y), chave in finais.items()
            if _mesma_cor(final[y][x], base.paleta[chave] if chave is not None else None)
        )
        resultado = ResultadoDaEdicao(
            aprovado=variante.status == "approved",
            asset_id=job.asset.id,
            mudados=len(finais),
            ficaram=ficaram,
            camada=camada["nome"],
        )
        if ficaram < len(finais):
            resultado.avisos.append(
                f"o Optimizer mudou {len(finais) - ficaram} dos {len(finais)} pixels editados"
            )
        if not resultado.aprovado:
            resultado.motivo = await self._motivo_da_reprovacao(variante)
            return resultado

        texto = motivo or f"{len(finais)} pixels corrigidos no editor"
        resultado.pedido = await asyncio.to_thread(
            self._pedidos.fila.registrar_edicao,
            projeto=self._pedidos.projeto,
            texto=texto,
            corpo={"origem_asset_id": base.registro.asset_id, "texto": texto, "editor": True},
            leitura={
                "resolved": spec.model_dump(mode="json"),
                "semantic": base.registro.semantic_prompt.model_dump(mode="json")
                if base.registro.semantic_prompt
                else None,
            },
            origem_asset_id=base.registro.asset_id,
            asset_id=job.asset.id,
            job_id=job.id,
            asset_projeto=job.asset.project_id,
            olhar=f"corrigido pela autora no editor ({camada['nome']}, {len(finais)} pixels)",
        )
        if motivo:
            tipo, corpo, porte = etiquetas_do_spec(spec)
            await asyncio.to_thread(
                self._container.aprendizado.opinar,
                base.registro.asset_id,
                gostei=False,
                motivo=f"corrigido no editor: {motivo}",
                tipo=tipo,
                corpo=corpo,
                porte=porte,
            )
        return resultado

    # ------------------------------------------------------------------
    async def _base(self, pedido_id: str) -> _Base:
        if not self.ligado:
            raise InvalidGenerationRequest(DESLIGADO)
        pedido = await asyncio.to_thread(self._pedidos.fila.obter, pedido_id)
        if pedido.situacao is not Situacao.CONCLUIDO or not pedido.asset_id:
            raise InvalidGenerationRequest(
                "só um pedido pronto abre no editor: este está "
                f"'{pedido.situacao.value}'"
            )
        registro = await self._pedidos.registro(pedido.asset_id)
        receita = (registro.engine_options.get(self._pedidos.gerador) or {}).get("receita")
        if not isinstance(receita, dict):
            raise InvalidGenerationRequest(
                f"o asset '{pedido.asset_id}' não foi desenhado pela "
                f"{self._pedidos.gerador}: não há receita para remendar"
            )
        asset = await self._pedidos.asset(pedido.asset_projeto, pedido.job_id)
        if asset is None or not asset.variants:
            raise InvalidGenerationRequest(f"o asset '{pedido.asset_id}' não está no storage")
        variante = asset.variants[0]
        paleta = await self._paleta(variante, receita)
        return _Base(
            pedido=pedido,
            registro=registro,
            receita=receita,
            variante=variante,
            largura=variante.logical_width or variante.width,
            altura=variante.logical_height or variante.height,
            paleta=paleta,
        )

    async def _paleta(self, variante: Any, receita: Mapping[str, Any]) -> dict[str, str]:
        """A paleta efetiva que a gaveta gravou; antes do lote 5, a da receita."""
        saida = await self._json(variante.artifacts.get("engine_output.json"))
        gravada = ((saida or {}).get("engine_metadata") or {}).get("paleta")
        fonte = gravada if isinstance(gravada, Mapping) else receita.get("paleta") or {}
        return {str(k): str(v).lower() for k, v in fonte.items()}

    async def _motivo_da_reprovacao(self, variante: Any) -> str:
        validacao = await self._json(variante.artifacts.get("validation.json")) or {}
        falhas = [
            str(item.get("message") or item.get("code")) if isinstance(item, Mapping) else str(item)
            for item in (validacao.get("acceptance") or {}).get("failures") or []
        ]
        return "; ".join(f for f in falhas if f) or "o validador não aprovou o desenho editado"

    async def _json(self, uri: str | None) -> dict[str, Any] | None:
        if not uri:
            return None
        try:
            return json.loads(await self._container.storage.read(uri))
        except Exception:  # noqa: BLE001 - relatório ausente não impede a edição
            return None

    async def _executar(self, requisicao: Any, spec: Any) -> Any:
        """Submete o job e espera: pelo worker embutido, ou rodando-o aqui."""
        servico = self._container.service
        try:
            job = await servico.submit(requisicao, resolved=spec)
        except GenerationError as exc:
            raise InvalidGenerationRequest(exc.message) from exc
        limite = time.monotonic() + self._timeout_s
        while not job.status.is_terminal:
            if time.monotonic() > limite:
                raise InvalidGenerationRequest(
                    f"a edição não terminou em {self._timeout_s:.0f}s (job {job.id})"
                )
            if self._container.worker_rodando:
                await asyncio.sleep(0.1)
            else:
                await self._container.worker.run_once(timeout=1.0)
            job = await servico.get_job(job.id)
        return job


@dataclass(frozen=True, slots=True)
class _Base:
    pedido: Pedido
    registro: Any
    receita: Mapping[str, Any]
    variante: Any
    largura: int
    altura: int
    paleta: dict[str, str]
