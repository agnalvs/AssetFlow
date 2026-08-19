"""Asset Storage Service (planos §39 e §40).

Quem salva é este serviço. **Nunca** o motor.

    engine.generate()  ->  bytes + metadados
    AssetStorageService ->  arquivo, thumbnail, metadata, URI, histórico

Essa separação evita acoplamento entre IA e infraestrutura: a gaveta não sabe
o que é um projeto, e o storage não sabe o que é um modelo de difusão.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from ..generation.kernel.exceptions import StorageError
from ..generation.postprocessing import build_thumbnail, encode_png
from ..generation.schemas import GeneratedAsset
from .backends import StorageBackend
from .records import GenerationRecord
from .repository import AssetRepository, GenerationRecordRepository

__all__ = ["StoredVariant", "AssetStorageService"]

_LOG = logging.getLogger("assetflow.storage")

#: Content-type por extensão dos arquivos auxiliares.
_CONTENT_TYPES = {"png": "image/png", "json": "application/json"}


@dataclass(frozen=True, slots=True)
class StoredVariant:
    """Resultado da persistência de uma variação."""

    uri: str
    thumbnail_uri: str | None
    size_bytes: int
    key: str


class AssetStorageService:
    """Persiste imagens, thumbnails, metadados e histórico."""

    def __init__(
        self,
        backend: StorageBackend,
        *,
        records: GenerationRecordRepository | None = None,
        assets: AssetRepository | None = None,
    ) -> None:
        self._backend = backend
        self._records = records
        self._assets = assets

    @property
    def backend(self) -> StorageBackend:
        return self._backend

    # ------------------------------------------------------------------
    # Imagens
    # ------------------------------------------------------------------
    @staticmethod
    def variant_key(project_id: str, job_id: str, index: int, *, suffix: str = "") -> str:
        """Chave determinística — facilita depuração e limpeza."""
        name = f"{index:03d}{suffix}.png"
        return f"projects/{project_id}/jobs/{job_id}/{name}"

    async def persist_variant(
        self,
        *,
        project_id: str,
        job_id: str,
        index: int,
        data: bytes,
        thumbnail_scale: float = 0.0,
        image=None,
    ) -> StoredVariant:
        """Grava a imagem e, opcionalmente, um thumbnail.

        Args:
            image: imagem PIL já decodificada (evita decodificar de novo).
            thumbnail_scale: >1 amplia (Pixel Art), <1 reduz, 0 desativa.
        """
        key = self.variant_key(project_id, job_id, index)
        stored = await self._backend.put(key, data, content_type="image/png")

        thumbnail_uri: str | None = None
        if thumbnail_scale and image is not None:
            thumbnail = build_thumbnail(image, thumbnail_scale)
            if thumbnail is not None:
                thumb_key = self.variant_key(project_id, job_id, index, suffix="_thumb")
                thumb_stored = await self._backend.put(
                    thumb_key, encode_png(thumbnail), content_type="image/png"
                )
                thumbnail_uri = thumb_stored.uri

        return StoredVariant(
            uri=stored.uri,
            thumbnail_uri=thumbnail_uri,
            size_bytes=stored.size,
            key=key,
        )

    async def persist_artifacts(
        self,
        *,
        project_id: str,
        job_id: str,
        index: int,
        artifacts: dict[str, bytes],
    ) -> dict[str, str]:
        """Grava os arquivos irmãos de uma variação (plano Pixel §70).

        Um asset de Pixel Art não é só um PNG: ele vem acompanhado de
        ``raw.png`` (a saída crua do motor), ``preview.png`` (ampliação só
        para visualizar), ``palette.json``, ``processing.json`` e
        ``validation.json``. Sem esses arquivos não há como depurar nem
        comparar motores depois (plano Pixel §71 a §75).

        Devolve ``{"preview.png": "assetflow-local://...", ...}``.
        """
        stored: dict[str, str] = {}
        for name in sorted(artifacts):
            data = artifacts[name]
            if not data:
                continue
            key = self.artifact_key(project_id, job_id, index, name)
            content_type = _CONTENT_TYPES.get(name.rsplit(".", 1)[-1].lower(), "application/octet-stream")
            try:
                result = await self._backend.put(key, data, content_type=content_type)
            except Exception as exc:  # pragma: no cover - arquivo auxiliar nunca derruba job
                _LOG.warning("falha ao gravar o artefato '%s' do job %s: %s", name, job_id, exc)
                continue
            stored[name] = result.uri
        return stored

    @staticmethod
    def artifact_key(project_id: str, job_id: str, index: int, name: str) -> str:
        """``projects/p/jobs/j/000_preview.png`` — irmão determinístico da variação."""
        safe = name.replace("/", "_").replace("\\", "_")
        return f"projects/{project_id}/jobs/{job_id}/{index:03d}_{safe}"

    async def read(self, uri: str) -> bytes:
        """Lê os bytes de uma URI produzida por este serviço."""
        key = self._backend.key_from_uri(uri)
        if key is None:
            raise StorageError(f"URI não pertence a este backend: {uri!r}")
        return await self._backend.get(key)

    # ------------------------------------------------------------------
    # Metadados e histórico
    # ------------------------------------------------------------------
    async def persist_asset_metadata(self, asset: GeneratedAsset) -> str:
        """Grava o JSON do asset ao lado das imagens."""
        key = f"projects/{asset.project_id}/jobs/{asset.job_id}/asset.json"
        payload = json.dumps(asset.model_dump(mode="json"), ensure_ascii=False, indent=2)
        stored = await self._backend.put(
            key, payload.encode("utf-8"), content_type="application/json"
        )
        if self._assets is not None:
            await self._assets.add(asset)
        return stored.uri

    async def record_generation(self, record: GenerationRecord) -> GenerationRecord:
        """Acrescenta a geração ao histórico (plano §41)."""
        if self._records is None:
            return record
        try:
            return await self._records.add(record)
        except Exception as exc:  # pragma: no cover - histórico nunca derruba job
            _LOG.warning("falha ao registrar histórico da geração: %s", exc)
            return record

    @property
    def records(self) -> GenerationRecordRepository | None:
        return self._records

    @property
    def assets(self) -> AssetRepository | None:
        return self._assets
