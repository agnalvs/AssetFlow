"""``python -m assetflow.mcp`` — sobe o servidor MCP do AssetFlow por stdio."""

from __future__ import annotations

import sys


def _rodar() -> None:
    try:
        from .servidor import main
    except ModuleNotFoundError as exc:
        if exc.name != "mcp" and not (exc.name or "").startswith("mcp."):
            raise
        # stderr: o stdout é o canal do protocolo.
        print(
            "o servidor MCP precisa do SDK do MCP, que é opcional. Instale com:\n"
            '    pip install -e ".[mcp]"',
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    main()


if __name__ == "__main__":
    _rodar()
