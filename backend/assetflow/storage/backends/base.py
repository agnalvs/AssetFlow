"""Contrato de backend de armazenamento.

Trocar disco local por S3/GCS é implementar esta interface. Nem o motor, nem
o pipeline, nem a API sabem onde o arquivo realmente está.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

__all__ = ["StoredObject", "StorageBackend"]


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Referência a um objeto persistido."""

    key: str
    uri: str
    size: int
    content_type: str
    #: Caminho local, quando o backend for de sistema de arquivos.
    path: str | None = None


class StorageBackend(ABC):
    """Armazenamento de bytes endereçado por chave."""

    @abstractmethod
    async def put(self, key: str, data: bytes, *, content_type: str = "image/png") -> StoredObject:
        ...

    @abstractmethod
    async def get(self, key: str) -> bytes:
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def uri_for(self, key: str) -> str:
        """URI estável usada nos metadados do asset."""

    def key_from_uri(self, uri: str) -> str | None:
        """Caminho inverso de :meth:`uri_for`, quando aplicável."""
        return None
