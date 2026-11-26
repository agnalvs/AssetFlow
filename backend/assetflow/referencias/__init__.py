"""Biblioteca de referências: pacotes de pixel art livres, importados e medidos.

O app importa pacotes que alguém baixou à mão (nada é baixado aqui), mede cada
quadro com código comum — sem IA — e soma o que os pacotes ativos dizem. O
Claude consulta o resultado: uma linha ``referências:`` no recorte de
``consultar_pedido`` e, quando julgar que precisa ver, uma imagem por
``ver_referencia``. Desde a Fase B2, sprites **CC0** podem ser convertidos para
receita e mostrados como **exemplo de construção** (:mod:`.exemplo`) — nunca
base de um asset nem remendo —, e o **olho do app** (:mod:`.olho`) compara o
desenho novo com as referências do mesmo porte.

Detalhes, comandos e o que não dá para medir: ``backend/docs/REFERENCIAS.md``.
"""

from .calibracao import gerar_relatorio
from .colecao import LADO_DA_AMPLIACAO, QuadroMedido, ReferenciasAtivas
from .importador import importar, medir_pacote
from .pacote import (
    LICENCA_PRINCIPAL,
    Ativo,
    ConfiguracaoDeReferencias,
    Manifesto,
    Parte,
    ReferenciaInvalida,
    ler_configuracao,
    ler_manifesto,
    normalizar_licenca,
)

__all__ = [
    "LADO_DA_AMPLIACAO",
    "LICENCA_PRINCIPAL",
    "Ativo",
    "ConfiguracaoDeReferencias",
    "Manifesto",
    "Parte",
    "QuadroMedido",
    "ReferenciaInvalida",
    "ReferenciasAtivas",
    "gerar_relatorio",
    "importar",
    "ler_configuracao",
    "ler_manifesto",
    "medir_pacote",
    "normalizar_licenca",
]
