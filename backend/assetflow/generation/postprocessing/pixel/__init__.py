"""Encaixe do Pixel Exact na cadeia de pós-processamento.

A tecnologia mora em ``assetflow.pixel``; este pacote só a conecta ao
pipeline de geração e traduz os relatórios para o vocabulário do asset.
"""

from .exact import PixelExactProcessor
from .processor import build_pixel_chain
from .spec import spec_from_profile

__all__ = [
    "PixelExactProcessor",
    "build_pixel_chain",
    "spec_from_profile",
]
