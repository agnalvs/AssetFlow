"""Pré-visualização do prompt (planos §26, §28 e §52).

Antes de existir este endpoint, a leitura que o AssetFlow fazia de uma
descrição só aparecia depois — dentro do ``GenerationRecord``, quando a
imagem já tinha custado GPU. Quem olhasse um asset errado não tinha como
saber se o problema foi o modelo ou a interpretação da frase.

    POST /api/generation/prompt/preview
        corpo:     o MESMO AssetGenerationRequest do POST /jobs
        resposta:  PromptPreview (profile, semântica, texto neutro)
        efeito:    nenhum — não cria job, não toca no Kernel, não grava nada

O corpo é o mesmo de propósito: o cliente pergunta "o que aconteceria se eu
mandasse isto?" com o objeto que ele mandaria. Qualquer divergência entre a
resposta daqui e o que a geração faz seria um bug, não uma diferença de
contrato — as duas pontas passam por ``resolve_semantic_prompt``.

Discordou da leitura? Devolva a semântica corrigida em
``semantic_prompt`` no pedido de geração: lá ela substitui o builder.
"""

from __future__ import annotations

from fastapi import APIRouter

from ...generation.schemas import AssetGenerationRequest, PromptPreview
from ..deps import ServiceDep

router = APIRouter(prefix="/api/generation/prompt", tags=["prompt"])


@router.post(
    "/preview",
    response_model=PromptPreview,
    summary="Mostra o que o AssetFlow entenderia deste pedido, sem gerar",
)
async def preview_prompt(
    request: AssetGenerationRequest, service: ServiceDep
) -> PromptPreview:
    return service.preview_prompt(request)
