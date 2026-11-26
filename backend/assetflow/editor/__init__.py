"""O editor de pixels da tela (lote 5). Ver ``servico.py`` e docs/LOTE_5_EDITOR.md."""

from __future__ import annotations

from .servico import (
    DESLIGADO,
    PREFIXO,
    DadosDoEditor,
    ResultadoDaEdicao,
    ServicoDoEditor,
    Troca,
    camada_de_retoque,
    grade_do_png,
)

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
