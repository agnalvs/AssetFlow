"""Gaveta `flux-pixel-v1` — FLUX.2-klein-4B + LoRA de Pixel Art (plano de motores §8.1).

O pacote não exporta a classe do motor: quem a instancia é o
:mod:`~assetflow.generation.kernel.discovery`, a partir do ``entrypoint`` do
manifesto. Importá-la aqui faria o pacote `engines` puxar `torch` no boot.
"""
