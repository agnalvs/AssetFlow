"""Repositório de registros de geração e de assets.

Duas implementações: memória (testes) e JSON Lines em disco (desenvolvimento
single-node). Ambas atendem a mesma interface, então trocar por Postgres é
uma classe nova — nenhuma alteração acima.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from pathlib import Path

from ..generation.schemas import GeneratedAsset
from .records import GenerationRecord

__all__ = [
    "GenerationRecordRepository",
    "InMemoryGenerationRecordRepository",
    "JsonLinesGenerationRecordRepository",
    "AssetRepository",
    "InMemoryAssetRepository",
]


class GenerationRecordRepository(ABC):
    """Histórico de gerações (plano §41)."""

    @abstractmethod
    async def add(self, record: GenerationRecord) -> GenerationRecord:
        ...

    @abstractmethod
    async def list(
        self, *, project_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[GenerationRecord]:
        ...

    @abstractmethod
    async def get(self, record_id: str) -> GenerationRecord | None:
        ...


class InMemoryGenerationRecordRepository(GenerationRecordRepository):
    """Histórico em memória."""

    def __init__(self) -> None:
        self._records: list[GenerationRecord] = []
        self._lock = asyncio.Lock()

    async def add(self, record: GenerationRecord) -> GenerationRecord:
        async with self._lock:
            self._records.append(record)
        return record

    async def list(
        self, *, project_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[GenerationRecord]:
        records = list(reversed(self._records))
        if project_id is not None:
            records = [record for record in records if record.project_id == project_id]
        return records[offset : offset + limit]

    async def get(self, record_id: str) -> GenerationRecord | None:
        for record in self._records:
            if record.id == record_id:
                return record
        return None


class JsonLinesGenerationRecordRepository(GenerationRecordRepository):
    """Histórico append-only em arquivo ``.jsonl``.

    Escolha consciente para esta fase: durável o bastante para inspecionar
    gerações reais, simples o bastante para não introduzir um banco antes da
    hora. A troca por um repositório SQL é local a esta classe.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def add(self, record: GenerationRecord) -> GenerationRecord:
        line = json.dumps(record.model_dump(mode="json"), ensure_ascii=False)

        def _append() -> None:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

        async with self._lock:
            await asyncio.to_thread(_append)
        return record

    async def _read_all(self) -> list[GenerationRecord]:
        if not self._path.exists():
            return []

        def _read() -> list[GenerationRecord]:
            records: list[GenerationRecord] = []
            with self._path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(GenerationRecord.model_validate_json(line))
                    except Exception:
                        continue
            return records

        return await asyncio.to_thread(_read)

    async def list(
        self, *, project_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[GenerationRecord]:
        records = list(reversed(await self._read_all()))
        if project_id is not None:
            records = [record for record in records if record.project_id == project_id]
        return records[offset : offset + limit]

    async def get(self, record_id: str) -> GenerationRecord | None:
        for record in await self._read_all():
            if record.id == record_id:
                return record
        return None


class AssetRepository(ABC):
    """Biblioteca de assets do projeto."""

    @abstractmethod
    async def add(self, asset: GeneratedAsset) -> GeneratedAsset:
        ...

    @abstractmethod
    async def get(self, asset_id: str) -> GeneratedAsset | None:
        ...

    @abstractmethod
    async def list(
        self, *, project_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[GeneratedAsset]:
        ...


class InMemoryAssetRepository(AssetRepository):
    """Biblioteca em memória (substituível por banco sem impacto acima)."""

    def __init__(self) -> None:
        self._assets: dict[str, GeneratedAsset] = {}
        self._order: list[str] = []
        self._lock = asyncio.Lock()

    async def add(self, asset: GeneratedAsset) -> GeneratedAsset:
        async with self._lock:
            self._assets[asset.id] = asset
            self._order.append(asset.id)
        return asset

    async def get(self, asset_id: str) -> GeneratedAsset | None:
        return self._assets.get(asset_id)

    async def list(
        self, *, project_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[GeneratedAsset]:
        assets = [self._assets[key] for key in reversed(self._order) if key in self._assets]
        if project_id is not None:
            assets = [asset for asset in assets if asset.project_id == project_id]
        return assets[offset : offset + limit]
