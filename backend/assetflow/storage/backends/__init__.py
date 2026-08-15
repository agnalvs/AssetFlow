"""Backends de armazenamento disponíveis."""

from .base import StorageBackend, StoredObject
from .local import LOCAL_URI_SCHEME, LocalFilesystemBackend

__all__ = [
    "LOCAL_URI_SCHEME",
    "LocalFilesystemBackend",
    "StorageBackend",
    "StoredObject",
]
