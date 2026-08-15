"""Gera assets de verdade e deixa os arquivos onde você consegue abrir.

Os testes provam que o sistema funciona, mas escrevem em diretórios
temporários. Este script é o contrário: ele existe para você **olhar** o que
cada gaveta produz.

Exemplos::

    # gera com a gaveta habilitada hoje
    python scripts/preview_engine.py

    # compara as duas gavetas mock lado a lado
    python scripts/preview_engine.py --engine all

    # personagem 32x32, 4 variações, seed fixa
    python scripts/preview_engine.py --profile pixel_character_32 -n 4 --seed 7

    # arte 2D convencional
    python scripts/preview_engine.py --profile studio_character \\
        --prompt "cartoon knight with a red cape"

Os PNGs vão para ``backend/data/preview/`` (ignorado pelo git).
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from assetflow.bootstrap import build_container  # noqa: E402
from assetflow.generation.schemas import (  # noqa: E402
    AssetGenerationRequest,
    AssetOutputOverrides,
    JobStatus,
)
from assetflow.settings import load_settings  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera assets e mostra o que cada gaveta produziu.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--engine",
        default="config",
        help=(
            "id da gaveta, 'all' para rodar uma por vez em todas as "
            "disponíveis, ou 'config' para respeitar engines.yaml (padrão)."
        ),
    )
    parser.add_argument("--profile", default="pixel_character_64", help="Generation Profile.")
    parser.add_argument(
        "--prompt", default="young warrior with blue armor", help="Descrição do asset."
    )
    parser.add_argument("-n", "--variations", type=int, default=2, help="Quantas variações.")
    parser.add_argument("--seed", type=int, default=None, help="Seed (fixa = resultado repetível).")
    parser.add_argument(
        "--out",
        default=str(BACKEND_ROOT / "data" / "preview"),
        help="Pasta de saída.",
    )
    parser.add_argument(
        "--keep", action="store_true", help="Não limpa a pasta de saída antes de gerar."
    )
    return parser.parse_args()


def activate_only(container, engine_id: str) -> None:
    """Deixa apenas uma gaveta ligada — é assim que se isola um motor."""
    for record in container.registry.list():
        container.service.disable_engine(record.id)
    container.service.enable_engine(engine_id)


async def generate(container, args, engine_id: str | None) -> list[dict]:
    """Roda um job e devolve a descrição das variações produzidas."""
    request = AssetGenerationRequest(
        project_id="preview",
        profile=args.profile,
        prompt=args.prompt,
        attributes={"view": "side", "pose": "idle"},
        output=AssetOutputOverrides(variations=args.variations),
        seed=args.seed,
    )

    job = await container.service.submit(request)
    await container.worker.run_once(timeout=120)
    job = await container.service.get_job(job.id)

    if job.status is not JobStatus.COMPLETED:
        print(f"  !! job {job.status.value}: {job.error.message if job.error else '—'}")
        return []

    rows = []
    for variant in job.asset.variants:
        key = container.storage.backend.key_from_uri(variant.uri)
        rows.append(
            {
                "engine": job.engine.id,
                "model": job.engine.model_id,
                "index": variant.index,
                "size": f"{variant.width}x{variant.height}",
                "logical": (
                    f"{variant.logical_width}x{variant.logical_height}"
                    if variant.logical_width
                    else "—"
                ),
                "colors": variant.color_count,
                "palette": len(variant.palette),
                "seed": variant.seed,
                "path": container.storage.backend.root / key,
                "thumb": (
                    container.storage.backend.root
                    / container.storage.backend.key_from_uri(variant.thumbnail_uri)
                    if variant.thumbnail_uri
                    else None
                ),
                "issues": [issue.code for issue in variant.validation.issues],
                "fallback": job.fallback_used,
                "timings": job.timings,
            }
        )
    return rows


async def main() -> int:
    args = parse_args()
    out_dir = Path(args.out)
    if out_dir.exists() and not args.keep:
        shutil.rmtree(out_dir)

    settings = load_settings(data_dir=out_dir)
    settings.worker.embedded = False  # o script controla quando o job roda
    container = build_container(settings)

    if args.engine == "all":
        targets = [record.id for record in container.registry.list()]
    elif args.engine == "config":
        targets = [None]
    else:
        targets = [args.engine]

    print(f"\nprofile : {args.profile}")
    print(f"prompt  : {args.prompt}")
    print(f"saída   : {out_dir}\n")

    all_rows: list[dict] = []
    for target in targets:
        label = target or "(conforme engines.yaml)"
        print(f"── gerando com {label} " + "─" * max(0, 50 - len(label)))

        if target is not None:
            activate_only(container, target)
            health = await container.registry.get(target).handle.health(force=True)
            if not health.is_usable:
                print(f"  ⊘ indisponível: {health.detail}\n")
                continue

        try:
            rows = await generate(container, args, target)
        except Exception as exc:
            print(f"  !! {type(exc).__name__}: {exc}\n")
            continue

        for row in rows:
            print(
                f"  #{row['index']}  {row['size']:>9}  lógico {row['logical']:>7}  "
                f"{row['colors'] or '—':>3} cores  seed {row['seed']}"
                + ("  [FALLBACK]" if row["fallback"] else "")
            )
            print(f"      {row['path']}")
            if row["thumb"]:
                print(f"      {row['thumb']}  (ampliado para inspeção)")
            if row["issues"]:
                print(f"      avisos: {', '.join(row['issues'])}")
        if rows:
            timings = rows[0]["timings"]
            print(
                f"  motor: {rows[0]['engine']}  modelo: {rows[0]['model']}\n"
                f"  tempos: inferência {timings.inference_ms:.0f}ms · "
                f"pós {timings.postprocess_ms:.0f}ms · "
                f"storage {timings.storage_ms:.0f}ms\n"
            )
        all_rows.extend(rows)

    await container.shutdown()

    if not all_rows:
        print("nenhum asset gerado — verifique se há alguma gaveta habilitada.")
        return 1

    print(f"{len(all_rows)} arquivo(s) gerado(s). Abra a pasta:\n  {out_dir / 'assets'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
