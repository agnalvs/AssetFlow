"""Base de conhecimento de pixel art para o desenhista (plano desenhista, Fase 3).

``config/pixel_knowledge/`` vira uma :class:`BaseDeConhecimento` no boot, e
:func:`montar_recorte` escolhe, para cada ``FinalResolvedSpec``, as poucas
linhas que ``consultar_pedido`` devolve ao Claude. Formato dos arquivos e regras
de origem: ``backend/docs/PIXEL_KNOWLEDGE.md`` §18 e os cabeçalhos dos YAML.
"""

from .base import (
    CLASSES,
    BaseDeConhecimento,
    ConhecimentoInvalido,
    Estilo,
    Forma,
    Luz,
    Medida,
    Molde,
    Paleta,
    Regra,
    luminancia,
)
from .recorte import (
    SEM_CORPO,
    TETO_CARACTERES,
    USO_DO_MOLDE,
    FonteDeReferencias,
    Porte,
    montar_recorte,
    porte,
)

__all__ = [
    "CLASSES",
    "SEM_CORPO",
    "TETO_CARACTERES",
    "USO_DO_MOLDE",
    "BaseDeConhecimento",
    "ConhecimentoInvalido",
    "Estilo",
    "FonteDeReferencias",
    "Forma",
    "Luz",
    "Medida",
    "Molde",
    "Paleta",
    "Porte",
    "Regra",
    "luminancia",
    "montar_recorte",
    "porte",
]
