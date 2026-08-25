"""Benchmark interno entre motores (plano de motores §19 a §21).

    BenchmarkSuite   os casos, iguais para todos      (config/benchmark_suite.yaml)
    BenchmarkTarget  o que medir: método + motor      (plano de correção §43)
    BenchmarkRunner  roda cada caso em cada alvo      (pelo caminho normal do sistema)
    BenchmarkReport  o resultado, em dois eixos       (técnico medido, visual humano)

A regra que organiza o módulo é o §21: **não misturar "engine bonito" com
"engine exato"**. O que o AssetFlow mede sozinho — resolução entregue, cores,
órfãos, nota do validador, quanto o pós-processamento teve de corrigir, tempo,
falhas — é uma coisa. Composição, design e legibilidade são outra, e ficam num
campo separado que só uma pessoa preenche.
"""

from .metrics import (
    BenchmarkReport,
    CaseOutcome,
    EngineReport,
    TargetReport,
    TechnicalMetrics,
    VisualScore,
)
from .runner import BenchmarkRunner
from .suite import (
    DEFAULT_CASES,
    BenchmarkCase,
    BenchmarkSuite,
    BenchmarkTarget,
)

__all__ = [
    "DEFAULT_CASES",
    "BenchmarkCase",
    "BenchmarkReport",
    "BenchmarkRunner",
    "BenchmarkSuite",
    "BenchmarkTarget",
    "CaseOutcome",
    "EngineReport",
    "TargetReport",
    "TechnicalMetrics",
    "VisualScore",
]
