"""Testes do value object Capability e do catálogo."""

from __future__ import annotations

import json

import pytest

from assetflow.generation.kernel.capabilities import CATALOG
from assetflow.generation.schemas import Capability, CapabilityParseError
from assetflow.generation.schemas.request import PromptSpec
from assetflow.generation.schemas import ImageGenerationRequest


def test_parse_and_str_roundtrip():
    capability = Capability.parse("text_to_image.pixel")
    assert capability.family == "text_to_image"
    assert capability.variant == "pixel"
    assert str(capability) == "text_to_image.pixel"


def test_capability_is_hashable_and_frozen():
    a = Capability.parse("character.2d")
    b = Capability.parse("character.2d")
    assert a == b
    assert len({a, b}) == 1
    with pytest.raises(Exception):
        a.family = "outro"  # type: ignore[misc]


def test_capability_serializes_as_string_in_json():
    request = ImageGenerationRequest(
        capability="text_to_image.pixel", prompt=PromptSpec(positive="x")
    )
    payload = json.loads(request.model_dump_json())
    assert payload["capability"] == "text_to_image.pixel"


def test_invalid_capability_is_rejected():
    for value in ("text_to_image", "a.b.c", "", "TEXT.PIXEL."):
        with pytest.raises((CapabilityParseError, ValueError)):
            Capability.parse(value)


def test_wildcard_matching():
    generalist = Capability.parse("text_to_image.*")
    assert generalist.matches("text_to_image.pixel")
    assert generalist.matches("text_to_image.general")
    assert not generalist.matches("inpainting.general")

    specific = Capability.parse("text_to_image.pixel")
    assert specific.matches("text_to_image.pixel")
    assert not specific.matches("text_to_image.general")


def test_catalog_documents_both_modes():
    known = {str(info.capability) for info in CATALOG.all()}
    assert "text_to_image.pixel" in known
    assert "text_to_image.general" in known
    # Capacidades futuras já previstas no catálogo (edição, animação).
    assert "inpainting.general" in known
    assert "animation.pixel" in known


def test_catalog_does_not_restrict_unknown_capabilities():
    """O catálogo descreve; ele não pode impedir uma gaveta futura."""
    assert CATALOG.is_known("text_to_image.pixel")
    assert not CATALOG.is_known("holograma.4d")
    assert CATALOG.describe("holograma.4d")  # devolve texto, não levanta erro
