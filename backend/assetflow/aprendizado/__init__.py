"""O que o desenho aprende com o uso: lições, opiniões e exemplos mostrados.

Fase B2 do plano do app. O arquivo mora em ``data/aprendizado/`` (é da
instalação, não vai ao git) e é dividido pela API e pelo servidor MCP.

Este pacote não importa API, MCP, gaveta nem jobs (teste de fronteiras): ele
guarda e escolhe. Quem lê um asset para tirar as etiquetas é quem o chama.
Detalhes: ``backend/docs/OLHAR.md``.
"""

from .caixa import (
    SEMELHANCA_MINIMA,
    AprendizadoIndisponivel,
    CaixaDeAprendizado,
    ErroDoAprendizado,
    LicaoInvalida,
    LicaoNaoEncontrada,
    Registro,
)
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
    etiquetas_do_spec,
    ler_tema,
)

__all__ = [
    "MAX_ERROU",
    "MAX_MOTIVO",
    "MAX_PORQUE",
    "MAX_REGRA",
    "QUALQUER",
    "SEMELHANCA_MINIMA",
    "AprendizadoIndisponivel",
    "CaixaDeAprendizado",
    "ErroDoAprendizado",
    "Licao",
    "LicaoInvalida",
    "LicaoNaoEncontrada",
    "Natureza",
    "Opiniao",
    "Origem",
    "Registro",
    "SituacaoDaOpiniao",
    "Tema",
    "etiquetas_do_spec",
    "ler_tema",
]
