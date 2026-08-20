"""Versões dos módulos Pixel Exact (plano Pixel §76).

Todo relatório carrega a versão do componente que o produziu. Sem isso é
impossível comparar dois benchmarks feitos com semanas de diferença: o número
muda e não se sabe se foi o motor, o algoritmo ou o profile.
"""

from __future__ import annotations

__all__ = [
    "ACCEPTANCE_POLICY_VERSION",
    "PIXEL_PIPELINE_VERSION",
    "POSTPROCESSOR_VERSION",
    "PREVIEW_GENERATOR_VERSION",
    "VALIDATOR_VERSION",
]

#: Versão do conjunto (processamento + validação + aceitação).
#:
#: 1.1.0 — recalibração da penalidade de ocupação: a distância fora da faixa
#: passou a ser normalizada pelo espaço do lado violado, e não pela largura da
#: faixa (ver `validation/scoring.py`). Só o validador mudou, mas a nota é
#: dele, então o conjunto muda junto: um `quality_score` de 1.0.0 e um de
#: 1.1.0 não são comparáveis, e é exatamente para isso que estes números
#: viajam em todo relatório.
PIXEL_PIPELINE_VERSION = "1.1.0"
POSTPROCESSOR_VERSION = "1.0.0"
VALIDATOR_VERSION = "1.1.0"
ACCEPTANCE_POLICY_VERSION = "1.0.0"
PREVIEW_GENERATOR_VERSION = "1.0.0"
