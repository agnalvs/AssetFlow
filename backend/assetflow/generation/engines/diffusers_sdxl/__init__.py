"""Gaveta `diffusers-sdxl-v1`.

Importar este pacote **não** importa torch nem diffusers: as dependências
pesadas só entram quando o motor é realmente inicializado.
"""

from .engine import DiffusersSDXLEngine

__all__ = ["DiffusersSDXLEngine"]
