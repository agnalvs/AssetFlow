"""Generation Profiles — o que gerar, nunca com qual motor."""

from .models import (
    GenerationProfile,
    ProfileOutput,
    ProfilePalette,
    ProfilePostProcessing,
)
from .registry import ProfileRegistry

__all__ = [
    "GenerationProfile",
    "ProfileOutput",
    "ProfilePalette",
    "ProfilePostProcessing",
    "ProfileRegistry",
]
