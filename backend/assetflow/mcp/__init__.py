"""Servidor MCP do AssetFlow: o Claude desenha pela conversa (plano desenhista, Fase 2).

Três ferramentas — ``consultar_pedido``, ``desenhar`` e ``ver_asset`` — sobre o
mesmo ``GenerationService`` que a API usa, montado pelo mesmo ``bootstrap``.

* :mod:`.servico` — o que as ferramentas fazem; não depende do SDK do MCP;
* :mod:`.servidor` — o protocolo (SDK ``mcp``, dependência opcional);
* :mod:`.laudo` — os textos que o Claude lê;
* :mod:`.remendo` — receita parcial sobre a receita de um asset anterior.

Rodar: ``python -m assetflow.mcp`` (stdio). Registrar no Claude Code: SETUP.md.

Este ``__init__`` não importa nada de propósito: importar o pacote não pode
exigir o SDK, que é opcional.
"""
