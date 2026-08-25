"""Roda a suíte comparativa e imprime a tabela (plano de motores §19 e §20).

Os testes provam que cada motor cumpre o contrato. Este script responde outra
pergunta: **qual deles produz o melhor asset, e a que custo?**

Exemplos::

    # todos os motores disponíveis, suíte inteira
    python scripts/benchmark_engines.py

    # só um motor, para iterar rápido
    python scripts/benchmark_engines.py --engines texel-style-v1

    # dois motores, dois casos
    python scripts/benchmark_engines.py \\
        --engines texel-style-v1,flux-pixel-v1 --cases tree_32,red_potion_16

    # guarda o relatório completo em JSON
    python scripts/benchmark_engines.py --json data/benchmark/relatorio.json

CUIDADO com o SD-πXL: se ele estiver habilitado e configurado, o projeto
declara execuções de **horas** por imagem (§2.2). Nomeie os motores com
`--engines` sempre que não for essa a intenção.

O que a tabela **não** diz: se o asset ficou bonito. Fidelidade, silhueta,
clusters, contorno e legibilidade são o eixo humano do §20, e o §21 é
categórico em não misturar os dois. Os PNGs ficam em
``backend/data/assets/projects/benchmark/`` para serem olhados.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

# O console do Windows abre em cp1252, que não codifica os caracteres de
# moldura da tabela. Sem isto o script morre com UnicodeEncodeError antes de
# imprimir qualquer coisa.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from assetflow.bootstrap import build_container  # noqa: E402
from assetflow.generation.benchmark import BenchmarkRunner, BenchmarkSuite  # noqa: E402
from assetflow.settings import load_settings  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara motores na mesma suíte de pedidos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--engines",
        default=None,
        help=(
            "Motores a comparar, separados por vírgula. Omitido, roda em "
            "todos os disponíveis — inclusive os lentos."
        ),
    )
    parser.add_argument(
        "--cases",
        default=None,
        help="Casos a rodar, separados por vírgula. Omitido, roda a suíte inteira.",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        default=None,
        help="Grava o relatório completo em JSON neste caminho.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Só lista os casos e os motores disponíveis, sem gerar nada.",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    settings = load_settings()
    settings.worker.embedded = False  # quem dirige o worker é o runner
    container = build_container(settings)

    suite = BenchmarkSuite.from_config(settings.benchmark_config)
    runner = BenchmarkRunner(container.service, container.worker, suite=suite)

    catalog = await container.service.engine_catalog(check_health=True)
    available = [entry for entry in catalog if entry.available]

    if args.list:
        print("\nCasos da suíte:")
        for case in suite.cases:
            print(f"  {case.id:20} {case.label()}")
        print("\nMotores disponíveis:")
        for entry in available:
            print(f"  {entry.engine_id:20} {entry.engine_family.value:14} {entry.speed_tier.value}")
        indisponiveis = [entry for entry in catalog if not entry.available]
        if indisponiveis:
            print("\nIndisponíveis agora:")
            for entry in indisponiveis:
                print(f"  {entry.engine_id:20} {entry.unavailable_reason}")
        return 0

    engines = _split(args.engines) or [entry.engine_id for entry in available]
    cases = _split(args.cases)

    if not engines:
        print("Nenhum motor disponível. Habilite ao menos um em config/engines.yaml.")
        return 1

    print(f"\nRodando {len(cases or suite.cases)} caso(s) em {len(engines)} motor(es)...")

    def progress(engine_id: str, case) -> None:
        print(f"  {engine_id:20} {case.id}", flush=True)

    report = await runner.run(engines=engines, cases=cases, progress=progress)
    await container.shutdown()

    _print_table(report)

    if args.json_path:
        path = Path(args.json_path)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.document(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nRelatório completo: {path}")

    return 0


def _print_table(report) -> None:
    """A tabela do §20 — só o eixo técnico, que é o único medido."""
    print("\n" + "=" * 96)
    print("QUALIDADE TÉCNICA DO ASSET FINAL (medida pelo AssetFlow)")
    print("=" * 96)
    header = (
        f"{'motor':22} {'casos':>6} {'falha':>7} {'exato':>7} "
        f"{'nota':>6} {'correção':>9} {'órfãos':>8} {'tempo(ms)':>10}"
    )
    print(header)
    print("-" * 96)
    for engine in report.engines:
        data = engine.document()
        print(
            f"{data['engine_id']:22} "
            f"{data['cases']:>6} "
            f"{_pct(data['failure_rate']):>7} "
            f"{_pct(data['pixel_exact_rate']):>7} "
            f"{_num(data['average_quality_score']):>6} "
            f"{_pct(data['average_correction_ratio']):>9} "
            f"{_pct(data['average_orphan_ratio']):>8} "
            f"{_num(data['average_duration_ms'], 0):>10}"
        )
    print("-" * 96)
    print(
        "correção = quanto o pós-processamento teve de apertar a paleta do motor.\n"
        "Perto de 0%, o motor já entrega perto do orçamento de cores pedido.\n"
    )
    print("QUALIDADE VISUAL DO MOTOR (composição, design, legibilidade)")
    print(
        "  Não medida aqui, e de propósito: é o eixo humano do §20/§21.\n"
        "  Abra os PNGs em data/assets/projects/benchmark/ e preencha as notas\n"
        "  no relatório JSON, no campo `visual` de cada caso."
    )

    falhas = [
        outcome
        for engine in report.engines
        for outcome in engine.outcomes
        if not outcome.succeeded
    ]
    if falhas:
        print("\nFalhas:")
        for outcome in falhas:
            print(f"  {outcome.engine_id:22} {outcome.case_id:18} {outcome.error}")


def _split(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None, digits: int = 1) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
