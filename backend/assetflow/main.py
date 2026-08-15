"""Ponto de entrada do servidor.

    python -m assetflow.main
    # ou
    uvicorn assetflow.main:app --reload
"""

from __future__ import annotations

import logging
import os

from .api import create_app

logging.basicConfig(
    level=os.environ.get("ASSETFLOW_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

app = create_app()


def main() -> None:  # pragma: no cover - execução manual
    import uvicorn

    uvicorn.run(
        "assetflow.main:app",
        host=os.environ.get("ASSETFLOW_HOST", "127.0.0.1"),
        port=int(os.environ.get("ASSETFLOW_PORT", "8000")),
        reload=os.environ.get("ASSETFLOW_RELOAD", "").lower() in {"1", "true"},
    )


if __name__ == "__main__":  # pragma: no cover
    main()
