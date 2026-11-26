"""Lições e opiniões da tela (Fase B2 do plano do app).

A tela lista as lições com o contador e pode editar a regra, trocar o tema,
desligar e apagar cada uma. Cada asset pronto ganha "gostei" e "não gostei",
com um motivo: "não gostei" com motivo fica **pendente** até o Claude
convertê-lo em lição (``registrar_licao``, no ``pedidos_pendentes``); sem
motivo, é só nota do asset.

O arquivo é o SQLite de ``data/aprendizado/``, que o servidor MCP também usa.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from ...aprendizado import Licao, Opiniao, Tema, etiquetas_do_spec
from ...generation.kernel.exceptions import InvalidGenerationRequest
from ..deps import ContainerDep
from ..schemas import (
    LicaoEdicao,
    LicaoListResponse,
    LicaoView,
    OpiniaoCorpo,
    OpiniaoView,
    OpinioesResponse,
)

router = APIRouter(prefix="/api/aprendizado", tags=["aprendizado"])


@router.get("/licoes", response_model=LicaoListResponse)
async def listar_licoes(container: ContainerDep) -> LicaoListResponse:
    return LicaoListResponse(
        items=[_licao(licao) for licao in container.aprendizado.listar()],
        temas={tema.value: tema.natureza.value for tema in Tema},
    )


@router.patch("/licoes/{licao_id}", response_model=LicaoView)
async def editar_licao(licao_id: str, edicao: LicaoEdicao, container: ContainerDep) -> LicaoView:
    licao = container.aprendizado.editar(
        licao_id, regra=edicao.regra, tema=edicao.tema, ligada=edicao.ligada
    )
    return _licao(licao)


@router.delete("/licoes/{licao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_licao(licao_id: str, container: ContainerDep) -> Response:
    container.aprendizado.apagar(licao_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/opinioes/{asset_id}", response_model=OpiniaoView)
async def opinar(asset_id: str, corpo: OpiniaoCorpo, container: ContainerDep) -> OpiniaoView:
    registro = await container.pedidos.registro(asset_id)
    try:
        spec = await container.pedidos.spec_do_asset(registro)
        tipo, corpo_do_asset, grade = etiquetas_do_spec(spec)
    except InvalidGenerationRequest:
        # Sem o spec gravado, a opinião vale como nota, sem etiquetas.
        tipo = corpo_do_asset = grade = None
    opiniao = container.aprendizado.opinar(
        asset_id,
        gostei=corpo.gostei,
        motivo=corpo.motivo,
        tipo=tipo,
        corpo=corpo_do_asset,
        porte=grade,
    )
    return _opiniao(opiniao)


@router.get("/opinioes", response_model=OpinioesResponse)
async def opinioes(
    container: ContainerDep,
    assets: Annotated[str | None, Query(description="Ids separados por vírgula.")] = None,
) -> OpinioesResponse:
    ids = [a.strip() for a in (assets or "").split(",") if a.strip()]
    encontradas = container.aprendizado.opinioes(ids)
    return OpinioesResponse(items={aid: _opiniao(o) for aid, o in encontradas.items()})


def _licao(licao: Licao) -> LicaoView:
    return LicaoView(
        id=licao.id,
        regra=licao.regra,
        errou=licao.errou,
        porque=licao.porque,
        tema=licao.tema.value,
        natureza=licao.natureza.value,
        tipo=licao.tipo,
        corpo=licao.corpo,
        porte=licao.porte,
        origem=licao.origem.value,
        texto_da_autora=licao.texto_da_autora,
        contador=licao.contador,
        ligada=licao.ligada,
        asset_id=licao.asset_id,
        assets=list(licao.assets),
        criada_em=licao.criada_em,
        atualizada_em=licao.atualizada_em,
    )


def _opiniao(opiniao: Opiniao) -> OpiniaoView:
    return OpiniaoView(
        asset_id=opiniao.asset_id,
        gostei=opiniao.gostei,
        motivo=opiniao.motivo,
        situacao=opiniao.situacao.value,
        licao=f"L{opiniao.licao}" if opiniao.licao else None,
        em=opiniao.em,
    )
