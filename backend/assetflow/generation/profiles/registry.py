"""Registro de Generation Profiles."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from ..kernel.exceptions import ProfileNotFound
from .models import GenerationProfile

__all__ = ["ProfileRegistry"]

_LOG = logging.getLogger("assetflow.generation.profiles")


class ProfileRegistry:
    """Coleção de profiles disponíveis para o produto."""

    def __init__(self, profiles: Iterable[GenerationProfile] = ()) -> None:
        self._profiles: dict[str, GenerationProfile] = {
            profile.id: profile for profile in profiles
        }

    @classmethod
    def from_config(cls, data: dict[str, Any]) -> "ProfileRegistry":
        """Constrói a partir do dicionário lido de ``profiles.yaml``."""
        profiles: list[GenerationProfile] = []
        for profile_id, raw in (data.get("profiles") or {}).items():
            try:
                profiles.append(GenerationProfile.model_validate({"id": profile_id, **raw}))
            except Exception as exc:
                _LOG.error("profile '%s' inválido e ignorado: %s", profile_id, exc)
        return cls(profiles)

    def register(self, profile: GenerationProfile) -> GenerationProfile:
        self._profiles[profile.id] = profile
        return profile

    def get(self, profile_id: str) -> GenerationProfile:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise ProfileNotFound(
                f"profile '{profile_id}' não existe",
                detail={"available": sorted(self._profiles)},
            )
        return profile

    def find(self, profile_id: str) -> GenerationProfile | None:
        return self._profiles.get(profile_id)

    def list(self) -> list[GenerationProfile]:
        return [self._profiles[key] for key in sorted(self._profiles)]

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._profiles))

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._profiles)
