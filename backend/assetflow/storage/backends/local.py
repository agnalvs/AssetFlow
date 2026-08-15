"""Backend de armazenamento em sistema de arquivos local."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...generation.kernel.exceptions import StorageError
from .base import StorageBackend, StoredObject

__all__ = ["LocalFilesystemBackend", "LOCAL_URI_SCHEME"]

LOCAL_URI_SCHEME = "assetflow-local"


class LocalFilesystemBackend(StorageBackend):
    """Grava arquivos sob um diretório raiz.

    As chaves são caminhos relativos (``projects/p1/jobs/j1/000.png``) e são
    validadas para nunca escaparem da raiz.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    def _resolve(self, key: str) -> Path:
        normalized = key.replace("\\", "/").strip("/")
        if not normalized:
            raise StorageError("chave de storage vazia")
        candidate = (self._root / normalized).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise StorageError(
                f"chave de storage inválida (fora da raiz): {key!r}"
            ) from exc
        return candidate

    async def put(
        self, key: str, data: bytes, *, content_type: str = "image/png"
    ) -> StoredObject:
        path = self._resolve(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        try:
            await asyncio.to_thread(_write)
        except OSError as exc:
            raise StorageError(f"falha ao gravar '{key}': {exc}") from exc

        return StoredObject(
            key=key,
            uri=self.uri_for(key),
            size=len(data),
            content_type=content_type,
            path=str(path),
        )

    async def get(self, key: str) -> bytes:
        path = self._resolve(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except OSError as exc:
            raise StorageError(f"falha ao ler '{key}': {exc}") from exc

    async def delete(self, key: str) -> None:
        path = self._resolve(key)

        def _delete() -> None:
            if path.exists():
                path.unlink()

        await asyncio.to_thread(_delete)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._resolve(key).exists)

    def uri_for(self, key: str) -> str:
        normalized = key.replace("\\", "/").strip("/")
        return f"{LOCAL_URI_SCHEME}://{normalized}"

    def key_from_uri(self, uri: str) -> str | None:
        prefix = f"{LOCAL_URI_SCHEME}://"
        if not uri.startswith(prefix):
            return None
        return uri[len(prefix) :]
