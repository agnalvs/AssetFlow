"""AssetFlow — backend da plataforma de criação de assets para jogos 2D.

Organização de alto nível::

    assetflow/
    ├── generation/    # a estante: kernel, contratos, gavetas, pipelines
    ├── jobs/          # fila, workers e ciclo de vida dos jobs
    ├── storage/       # persistência de imagens e metadados
    ├── api/           # camada web (FastAPI)
    ├── settings.py    # configuração externa (YAML + variáveis de ambiente)
    └── bootstrap.py   # composition root: monta o sistema inteiro
"""

from .version import __version__

__all__ = ["__version__"]
