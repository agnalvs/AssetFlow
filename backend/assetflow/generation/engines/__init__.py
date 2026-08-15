"""Pacote das gavetas.

Este ``__init__`` é intencionalmente vazio de imports. Gavetas **não** são
importadas estaticamente: elas são descobertas por ``manifest.json`` e
carregadas por ``importlib`` (ver ``kernel/discovery.py``).

Se algum dia aparecer aqui um ``from .diffusers_sdxl import ...``, a estante
passou a depender da gaveta — exatamente o que a arquitetura proíbe.
"""
