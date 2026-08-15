"""Persistência de assets, metadados e histórico do AssetFlow."""

from .asset_storage import AssetStorageService, StoredVariant
from .backends import LOCAL_URI_SCHEME, LocalFilesystemBackend, StorageBackend, StoredObject
from .records import GenerationRecord, GenerationRecordOutput
from .repository import (
    AssetRepository,
    GenerationRecordRepository,
    InMemoryAssetRepository,
    InMemoryGenerationRecordRepository,
    JsonLinesGenerationRecordRepository,
)

__all__ = [
    "LOCAL_URI_SCHEME",
    "AssetRepository",
    "AssetStorageService",
    "GenerationRecord",
    "GenerationRecordOutput",
    "GenerationRecordRepository",
    "InMemoryAssetRepository",
    "InMemoryGenerationRecordRepository",
    "JsonLinesGenerationRecordRepository",
    "LocalFilesystemBackend",
    "StorageBackend",
    "StoredObject",
    "StoredVariant",
]
