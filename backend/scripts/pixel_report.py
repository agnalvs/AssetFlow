"""Compara RAW, LOGICAL e PREVIEW em três casos de teste (plano Pixel §109).

O plano Pixel §109 pede a comparação que este script produz: a mesma imagem
vista nas três formas em que ela existe, lado a lado, para que a diferença
entre elas seja visível em vez de argumentada.

    raw.png       o que o motor devolveu       grande, muitas cores, alpha suave
    logical.png   o asset de verdade (§33)     a resolução lógica do profile
    preview.png   a lupa (§34, §73, §81)       ampliação inteira, nearest

A pergunta que a tabela responde é sempre a mesma: *o arquivo entregue é um
sprite na resolução lógica, ou é uma pintura grande com aparência de Pixel
Art?* — a violação nº 1 do plano §103.

Os três casos existem porque cada um estressa uma parte diferente do módulo:

``gradiente``
    "Falsa Pixel Art" desenhada por código: gradiente com alpha esfumado, sem
    um único pixel no lugar certo. É o pior caso — a entrada que **precisa**
    sair do outro lado com paleta limitada e alpha binário.
``mock``
    A saída real da gaveta ``mock-image-v1``, obtida pelo container do
    AssetFlow. Prova que o módulo Pixel processa o que o sistema realmente
    produz, e não apenas imagens fabricadas para o script.
``sprite``
    Um sprite já pixel-perfect ampliado por um fator inteiro — a fonte para a
    qual existe o ``block_vote`` (§18). Aqui a redução tem que devolver o
    sprite original, pixel por pixel, e o script confere isso.

Nada aqui exige GPU nem rede: a gaveta pesada é desligada antes de qualquer
resolução de capacidade, e os outros dois casos são desenhados localmente.

Exemplos::

    python scripts/pixel_report.py
    python scripts/pixel_report.py --profile pixel_tileset_16
    python scripts/pixel_report.py --case sprite
    python scripts/pixel_report.py --out C:/tmp/pixel

Os arquivos vão para ``backend/data/pixel_report/<caso>/``. Vale a regra do
projeto: ``backend/data/`` é **volátil e ignorado pelo git** — nada do que
sair daqui é entrega, é material de inspeção e pode ser apagado a qualquer
momento.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

# O console do Windows abre em cp1252, que não codifica os acentos das
# mensagens nem os traços das molduras. Sem isto o script morre com
# UnicodeEncodeError antes de gerar qualquer coisa — e também quando a saída é
# redirecionada para arquivo, caso em que o Python usa o encoding da locale.
# Ainda assim a tabela usa só ASCII: reconfigurar conserta a saída deste
# processo, não a de quem for colar o resultado em outro lugar.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image

from assetflow.bootstrap import AppContainer, build_container
from assetflow.generation.schemas import (
    Capability,
    EngineSelector,
    GenerationParams,
    ImageGenerationRequest,
    OutputSpec,
    PromptSpec,
)
from assetflow.pixel import (
    PixelAssetOutcome,
    PixelAssetProcessor,
    PixelOutputSpec,
)
from assetflow.pixel.imaging import (
    alpha_values,
    count_colors,
    decode,
    encode_png,
    scale_nearest,
    to_array,
    to_image,
)
from assetflow.pixel.processing.stages.exporter import ARTIFACT_NAMES
from assetflow.settings import load_settings

#: Lado da imagem bruta dos casos desenhados por código. 512 é múltiplo de 64,
#: 32 e 16, então nenhum profile do ``pixel_profiles.yaml`` cai em uma redução
#: fracionária só por causa do script.
RENDER_SIZE = 512

#: Ampliação do caso ``sprite``. Inteira porque é justamente o que dá sentido
#: ao ``block_vote``: cada pixel lógico vira um bloco exato de origem (§18).
SPRITE_SCALE = 8

#: Seed do caso ``mock``. Fixa por padrão porque a gaveta é determinística e um
#: relatório que muda a cada execução não serve para comparar nada.
DEFAULT_SEED = 4242

#: Profile usado quando ``--profile`` não é informado.
DEFAULT_PROFILE = "pixel_character_64_strict"

CASE_IDS = ("gradiente", "mock", "sprite")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compara RAW x LOGICAL x PREVIEW em três casos de teste "
            "(plano Pixel §109)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=f"Pixel Profile de config/pixel_profiles.yaml (padrão: {DEFAULT_PROFILE}).",
    )
    parser.add_argument(
        "--case",
        default="all",
        choices=("all", *CASE_IDS),
        help="Roda só um caso, ou todos (padrão).",
    )
    parser.add_argument(
        "--out",
        default=str(BACKEND_ROOT / "data" / "pixel_report"),
        help="Pasta de saída; cada caso ganha uma subpasta com o próprio nome.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Seed da gaveta mock (só afeta o caso 'mock').",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# As três imagens brutas
# ---------------------------------------------------------------------------
def build_gradient(size: int = RENDER_SIZE) -> bytes:
    """Desenha a "falsa Pixel Art": gradiente contínuo com alpha esfumado.

    É o anti-asset. O RGB varia pixel a pixel, então a contagem de cores fica
    na casa das dezenas de milhares; o alpha decai suavemente do centro para a
    borda, então existe transparência parcial em quase toda a silhueta. As
    duas coisas são exatamente o que o Pixel Exact não aceita (§21 e §25) — e
    é por isso que este é o caso mais informativo dos três.

    Tudo é calculado a partir das coordenadas: nenhum ``random``, nenhuma
    dependência de ordem, a mesma imagem em qualquer máquina.
    """
    axis = np.linspace(-1.0, 1.0, size, dtype=np.float64)
    horizontal, vertical = np.meshgrid(axis, axis)

    array = np.zeros((size, size, 4), dtype=np.uint8)
    array[:, :, 0] = np.clip((horizontal + 1.0) * 127.5, 0, 255).astype(np.uint8)
    array[:, :, 1] = np.clip((vertical + 1.0) * 127.5, 0, 255).astype(np.uint8)
    array[:, :, 2] = np.clip((2.0 - horizontal - vertical) * 63.75, 0, 255).astype(
        np.uint8
    )

    # Queda linear a partir do centro: o alpha passa por todos os valores entre
    # 255 e 0, que é a franja semitransparente que o AlphaNormalizer terá de
    # resolver. O raio 0.9 deixa a silhueta ocupando ~16% do canvas, dentro da
    # faixa saudável do §53 — o caso é sobre cor e alpha, não sobre ocupação.
    distance = np.sqrt(horizontal**2 + vertical**2)
    array[:, :, 3] = np.clip(255.0 * (1.0 - distance / 0.9), 0, 255).astype(np.uint8)

    return encode_png(to_image(array))


async def build_mock(container: AppContainer, seed: int, size: int = RENDER_SIZE) -> bytes:
    """Pede uma imagem à gaveta ``mock-image-v1`` pelo Kernel do AssetFlow.

    O pedido é por **capacidade** (``text_to_image.pixel``), como manda o
    plano §7; o ``engine_id`` só aparece no seletor porque este relatório
    precisa comparar sempre a mesma origem. ``allow_fallback=False`` garante
    que uma indisponibilidade vire erro visível em vez de trocar de motor no
    meio da comparação sem ninguém perceber.
    """
    request = ImageGenerationRequest(
        capability=Capability.parse("text_to_image.pixel"),
        prompt=PromptSpec(positive="young warrior with blue armor, side view, idle"),
        output=OutputSpec(width=size, height=size, variations=1, transparent=True),
        generation=GenerationParams(seed=seed),
        engine=EngineSelector(
            mode="manual", engine_id="mock-image-v1", allow_fallback=False
        ),
    )
    result = await container.kernel.execute(request, job_id="pixel-report")
    data = result.outputs[0].data
    if data is None:  # pragma: no cover - a gaveta mock sempre devolve bytes
        raise RuntimeError("a gaveta devolveu uma saída sem bytes")
    return bytes(data)


def build_sprite(spec: PixelOutputSpec, scale: int = SPRITE_SCALE) -> tuple[bytes, Image.Image]:
    """Desenha um sprite já pixel-perfect e o amplia por um fator inteiro.

    Devolve ``(bytes ampliados, sprite original)``. O original volta junto
    porque ele é o gabarito: depois do ``block_vote``, ``logical.png`` deveria
    ser idêntico a ele, e é essa igualdade que o relatório confere.

    O desenho é feito em blocos retangulares de tamanho proporcional ao lado
    do sprite — nada de coordenadas absolutas, para que o mesmo código sirva a
    um profile 64×64 e a um tile 16×16. Cada área é grande o bastante para não
    ser rara (§30): um detalhe de um pixel só seria candidato à limpeza
    conservadora, e o caso ficaria medindo o cleaner em vez do redutor.
    """
    width, height = spec.logical_size.as_tuple
    unit_x = max(1, width // 16)
    unit_y = max(1, height // 16)

    silhouette = np.zeros((height, width), dtype=bool)
    accent = np.zeros((height, width), dtype=bool)

    def fill(target: np.ndarray, left: int, top: int, right: int, bottom: int) -> None:
        """Marca um retângulo em unidades de 1/16 do sprite, recortado no canvas."""
        target[
            min(top * unit_y, height) : min(bottom * unit_y, height),
            min(left * unit_x, width) : min(right * unit_x, width),
        ] = True

    fill(silhouette, 5, 2, 11, 7)    # cabeça
    fill(silhouette, 4, 7, 12, 13)   # tronco
    fill(silhouette, 5, 13, 7, 15)   # perna esquerda
    fill(silhouette, 9, 13, 11, 15)  # perna direita
    fill(accent, 4, 10, 12, 11)      # cinto

    # Contorno: dilatação de 1 pixel da silhueta menos ela mesma. Feito com
    # deslocamentos de array porque é determinístico e não depende de biblioteca
    # de morfologia.
    dilated = silhouette.copy()
    for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
        dilated |= np.roll(silhouette, shift, axis=axis)
    outline = dilated & ~silhouette

    array = np.zeros((height, width, 4), dtype=np.uint8)
    array[silhouette] = (79, 121, 66, 255)   # corpo
    array[accent] = (201, 178, 124, 255)     # cinto
    array[outline] = (18, 21, 28, 255)       # contorno

    sprite = to_image(array)
    return encode_png(scale_nearest(sprite, scale)), sprite


# ---------------------------------------------------------------------------
# Execução de um caso
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Case:
    """Um caso de teste já resolvido, pronto para virar linhas de tabela."""

    id: str
    description: str
    spec: PixelOutputSpec
    raw: Image.Image
    outcome: PixelAssetOutcome
    out_dir: Path
    #: Observações específicas do caso (round-trip do sprite, por exemplo).
    notes: tuple[str, ...] = ()


def run_case(
    case_id: str,
    description: str,
    raw_data: bytes,
    spec: PixelOutputSpec,
    out_dir: Path,
    *,
    notes: tuple[str, ...] = (),
    reference: Image.Image | None = None,
) -> Case:
    """Roda o módulo Pixel inteiro em uma imagem bruta e grava os artefatos."""
    processor = PixelAssetProcessor()
    outcome = processor.run(raw_data, spec)

    if reference is not None:
        notes = (*notes, _roundtrip_note(reference, outcome.logical))

    write_artifacts(out_dir, outcome.artifacts)

    return Case(
        id=case_id,
        description=description,
        spec=spec,
        raw=decode(raw_data),
        outcome=outcome,
        out_dir=out_dir,
        notes=notes,
    )


def write_artifacts(out_dir: Path, artifacts: dict[str, bytes]) -> None:
    """Grava os arquivos do §70, limpando os da execução anterior.

    Nada de ``rmtree``: ``--out`` pode apontar para qualquer lugar, e apagar
    uma pasta inteira por causa de um caminho digitado errado é caro demais.
    Remover só os nomes que este script escreve resolve o problema real —
    ``preview.png`` de um profile antigo sobrevivendo a um profile que
    desligou o preview.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ARTIFACT_NAMES:
        stale = out_dir / name
        if stale.exists():
            stale.unlink()
    for name, data in artifacts.items():
        (out_dir / name).write_bytes(data)


def _roundtrip_note(reference: Image.Image, logical: Image.Image) -> str:
    """Diz se o asset final reproduz o sprite de origem, pixel visível a pixel visível.

    A comparação exige alpha idêntico em **todos** os pixels e RGB idêntico
    apenas nos **opacos**. Não é uma tolerância: o ``PaletteQuantizer`` mapeia
    a imagem inteira para a paleta, então um pixel de alpha 0 sai daqui com o
    RGB da cor de paleta mais próxima em vez do ``#000000`` com que entrou.
    Isso é invisível por definição e coerente com o plano §28, que não conta
    pixel transparente como cor do sprite — cobrar igualdade byte a byte no
    canal de cor de um pixel que ninguém vê acusaria como defeito justamente o
    comportamento correto do módulo.
    """
    expected = to_array(reference)
    produced = to_array(logical)
    if expected.shape != produced.shape:
        return (
            f"round-trip: dimensoes divergentes "
            f"({reference.width}x{reference.height} -> {logical.width}x{logical.height})"
        )

    visible = expected[:, :, 3] > 0
    alpha_diff = expected[:, :, 3] != produced[:, :, 3]
    color_diff = np.any(expected[:, :, :3] != produced[:, :, :3], axis=2) & visible
    different = int(np.count_nonzero(alpha_diff | color_diff))
    total = int(np.count_nonzero(visible))
    if not different:
        return (
            f"round-trip: logical.png reproduz os {total} pixels visiveis do sprite "
            "de origem, um a um"
        )
    return f"round-trip: {different} pixel(s) divergentes do sprite de origem"


# ---------------------------------------------------------------------------
# Medidas e tabela
# ---------------------------------------------------------------------------
def _format_alpha(values: tuple[int, ...]) -> str:
    """Resume o canal alpha: os valores em si, ou a faixa quando são muitos."""
    if not values:
        return "-"
    if len(values) <= 3:
        return "/".join(str(value) for value in values)
    return f"{values[0]}..{values[-1]} ({len(values)} valores)"


def _measure(image: Image.Image) -> tuple[str, str, str]:
    """``(dimensões, cores, alpha)`` de uma imagem.

    A contagem de cores ignora os pixels transparentes, que é o critério do
    plano §28 e o mesmo usado pelo check ``PX-COLOR-001`` — medir diferente
    aqui faria a tabela discordar do ``validation.json`` gravado ao lado.
    """
    array = to_array(image)
    return (
        f"{image.width}x{image.height}",
        str(count_colors(array)),
        _format_alpha(alpha_values(array)),
    )


def case_rows(case: Case) -> list[list[str]]:
    """As três linhas da tabela para um caso: RAW, LOGICAL e PREVIEW."""
    outcome = case.outcome
    rows: list[list[str]] = []

    dimensions, colors, alpha = _measure(case.raw)
    # RAW não recebe veredito: ele não é o asset, e carimbar "reprovado" na
    # imagem que o motor devolveu confundiria a origem com a entrega (§71).
    rows.append([case.id, "RAW", dimensions, colors, alpha, "-", "-", "-"])

    dimensions, colors, alpha = _measure(outcome.logical)
    rows.append(
        [
            case.id,
            "LOGICAL",
            dimensions,
            colors,
            alpha,
            "sim" if outcome.pixel_exact else "nao",
            str(outcome.quality_score),
            outcome.decision.status.value,
        ]
    )

    if outcome.preview is None:
        rows.append([case.id, "PREVIEW", "-", "-", "-", "-", "-", "desligado no profile"])
    else:
        dimensions, colors, alpha = _measure(outcome.preview)
        # A ampliação é vistoria, não asset: as colunas de veredito ficam
        # vazias de propósito (§35). O que importa aqui é que cores e alpha
        # sejam os mesmos do LOGICAL — se mudarem, alguém interpolou.
        rows.append(
            [
                case.id,
                "PREVIEW",
                dimensions,
                colors,
                alpha,
                "-",
                "-",
                f"ampliacao x{case.spec.preview.scale}",
            ]
        )
    return rows


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    """Tabela de largura fixa em ASCII puro, legível em qualquer console."""
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells))

    separator = "  ".join("-" * width for width in widths)
    return "\n".join([line(headers), separator, *(line(row) for row in rows)])


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------
def describe_spec(spec: PixelOutputSpec) -> str:
    width, height = spec.logical_size.as_tuple
    limit = spec.max_colors if spec.max_colors is not None else "sem limite"
    return (
        f"{spec.id} | {width}x{height} | <={limit} cores | "
        f"alpha {spec.alpha.mode} (limiar {spec.alpha.threshold}) | "
        f"canvas {spec.canvas.mode} | reducao {spec.logical_reduction.method}"
    )


def print_case(index: int, total: int, case: Case) -> None:
    """Detalhe de um caso: de onde veio, o que saiu e por quê."""
    outcome = case.outcome
    print(f"[{index}/{total}] {case.id}")
    print(f"  {case.description}")
    print(f"  spec       : {describe_spec(case.spec)}")
    print(f"  arquivos   : {case.out_dir}")
    print(f"               {', '.join(sorted(outcome.artifacts))}")
    print(f"  tentativas : {outcome.attempts} de {case.spec.attempts.max_processing_attempts}")

    palette = outcome.processing.palette
    if palette:
        mostra = ", ".join(palette[:8])
        resto = f" (+{len(palette) - 8})" if len(palette) > 8 else ""
        print(f"  paleta     : {len(palette)} cores: {mostra}{resto}")

    for note in case.notes:
        print(f"  {note}")
    for warning in outcome.processing.warnings:
        print(f"  aviso proc.: {warning}")
    for warning in outcome.validation.quality.warnings:
        print(f"  aviso qual.: {warning.code} - {warning.message}")
    for failure in outcome.validation.failures:
        print(f"  FALHA      : {failure.code} esperado {failure.expected}, obtido {failure.actual}")
    print()


async def build_cases(args: argparse.Namespace) -> list[Case]:
    """Monta e roda os casos pedidos, na ordem fixa de :data:`CASE_IDS`."""
    settings = load_settings()
    settings.worker.embedded = False  # o script não usa fila nem worker
    container = build_container(settings)

    # Sem GPU e sem rede: a gaveta pesada sai da estante antes de qualquer
    # resolução de capacidade. É a mesma trava da suíte (tests/conftest.py) —
    # aqui ela também evita um download de ~7GB por engano.
    for record in container.registry.list():
        if record.manifest.resources.gpu_required:
            container.registry.disable(record.id)

    out_root = Path(args.out)
    wanted = CASE_IDS if args.case == "all" else (args.case,)

    cases: list[Case] = []
    try:
        # Dentro do `try`: um profile inexistente também precisa passar pelo
        # `shutdown()`, senão a fila fica aberta quando o erro é justamente o
        # mais provável de acontecer (nome de profile digitado errado).
        spec = container.pixel_profiles.get(args.profile)

        if "gradiente" in wanted:
            cases.append(
                run_case(
                    "gradiente",
                    "falsa Pixel Art desenhada por codigo: gradiente continuo "
                    f"{RENDER_SIZE}x{RENDER_SIZE} com alpha esfumado.",
                    build_gradient(),
                    spec,
                    out_root / "gradiente",
                )
            )

        if "mock" in wanted:
            cases.append(
                run_case(
                    "mock",
                    f"saida real da gaveta mock-image-v1 pelo Kernel, seed {args.seed}.",
                    await build_mock(container, args.seed),
                    spec,
                    out_root / "mock",
                )
            )

        if "sprite" in wanted:
            # O único caso que troca uma linha do spec, e por um motivo: o
            # block_vote (§18) só faz sentido quando a origem já está em
            # blocos. Trocar o método aqui é o que torna o caso uma
            # demonstração dele, e não mais uma redução por média de área.
            block_spec = spec.model_copy(
                update={
                    "logical_reduction": spec.logical_reduction.model_copy(
                        update={"method": "block_vote"}
                    )
                }
            )
            raw_data, reference = build_sprite(block_spec)
            cases.append(
                run_case(
                    "sprite",
                    f"sprite pixel-perfect ampliado x{SPRITE_SCALE}; o spec do caso "
                    "troca a reducao para block_vote.",
                    raw_data,
                    block_spec,
                    out_root / "sprite",
                    reference=reference,
                )
            )
    finally:
        await container.shutdown()

    return cases


async def main() -> int:
    args = parse_args()

    try:
        cases = await build_cases(args)
    except KeyError as exc:
        # Profile inexistente: o registry já monta a lista dos disponíveis.
        print(f"!! {exc.args[0] if exc.args else exc}")
        return 1

    if not cases:
        print("nenhum caso executado.")
        return 1

    print()
    print(f"profile : {args.profile}")
    print(f"saida   : {Path(args.out)}")
    print(f"casos   : {', '.join(case.id for case in cases)}")
    print()

    for index, case in enumerate(cases, start=1):
        print_case(index, len(cases), case)

    headers = [
        "caso",
        "camada",
        "dimensoes",
        "cores",
        "alpha",
        "exato",
        "nota",
        "status",
    ]
    rows = [row for case in cases for row in case_rows(case)]
    print("RAW x LOGICAL x PREVIEW (plano Pixel §109)")
    print(render_table(headers, rows))
    print()
    print("cores  : tons unicos entre os pixels opacos (plano Pixel §28)")
    print("exato  : pixel_exact - so o LOGICAL e o asset; RAW e PREVIEW nao sao julgados")
    print("nota   : qualidade estrutural 0-100; nunca reprova sozinha (plano Pixel §47)")

    # O status reprovado é informação, não erro de execução: o caso rodou.
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
