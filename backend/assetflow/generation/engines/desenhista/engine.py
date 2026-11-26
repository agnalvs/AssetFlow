"""`desenhista-v1` — a gaveta que desenha a partir de uma receita.

Plano desenhista (``backend/docs/PLANO_DESENHISTA_MCP.md``), Fase 1. O desenho
não vem de um modelo carregado aqui: vem do Claude, pela conversa, como uma
receita curta de camadas (ver :mod:`.receita`). A gaveta transforma a receita
em sprite **na grade lógica** do pedido, e o resto do AssetFlow — Pixel Exact,
Pixel Optimizer, validação, storage — segue como para qualquer motor.

Três decisões que o manifesto declara e o código cumpre:

* **A saída é a grade lógica, 1:1** (``catalog.exact_resolution``). Ampliar
  até o tamanho de render só para o pós-processamento reduzir de volta não
  acrescentaria nada, e nem sempre fecharia: 512 não é múltiplo de 48.
* **Não há seed** (``supports.seed: false``). A receita é o desenho inteiro;
  a mesma receita dá sempre o mesmo sprite.
* **Uma variação por pedido** (``limits.max_variations: 1``). Mais de uma
  seriam cópias idênticas. O kernel recusa antes de dividir em lotes; a
  gaveta recusa também, para quem a chamar direto.

Sem receita, a gaveta falha dizendo como ela deve ser usada. É o que acontece
com o botão "Gerar" da tela, que não tem como mandar receita.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ....generation.kernel.contracts import (
    EngineExecutionContext,
    ImageGenerationEngine,
)
from ....generation.kernel.exceptions import (
    EngineExecutionError,
    InvalidGenerationRequest,
)
from ....generation.schemas import (
    Capability,
    EngineGenerationResult,
    EngineHealth,
    EngineHealthStatus,
    EngineManifest,
    EngineRef,
    EngineRuntimeConfig,
    ImageArtifact,
    ImageGenerationRequest,
    StageTimings,
)
from .rasterizador import desenhar, para_png
from .receita import ReceitaInvalida, ler_receita

__all__ = ["MENSAGEM_SEM_RECEITA", "DesenhistaEngine"]

_MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"

#: O que a pessoa (ou o Claude) lê quando o pedido chega sem receita.
MENSAGEM_SEM_RECEITA = (
    "o motor 'desenhista-v1' só desenha a partir de uma receita, que chega pelo "
    "servidor MCP do AssetFlow em engine_options['desenhista-v1']['receita']. "
    "Um pedido feito na tela vai para a fila, e o Claude o desenha pela conversa."
)


class DesenhistaEngine(ImageGenerationEngine):
    """Rasteriza a receita de desenho na grade lógica do pedido."""

    _manifest: EngineManifest | None = None

    def __init__(self) -> None:
        self._config: EngineRuntimeConfig | None = None
        self._ready = False
        self._active: set[str] = set()

    # -- Descoberta ------------------------------------------------------
    def manifest(self) -> EngineManifest:
        if type(self)._manifest is None:
            with _MANIFEST_PATH.open("r", encoding="utf-8") as handle:
                type(self)._manifest = EngineManifest.model_validate(json.load(handle))
        return type(self)._manifest  # type: ignore[return-value]

    def capabilities(self) -> tuple[Capability, ...]:
        return self.manifest().capabilities

    # -- Ciclo de vida ---------------------------------------------------
    async def initialize(self, config: EngineRuntimeConfig) -> None:
        # Não há modelo para carregar: a "inicialização" é só receber a
        # configuração.
        self._config = config
        self._ready = True

    async def unload(self) -> None:
        self._ready = False
        self._active.clear()

    async def health_check(self) -> EngineHealth:
        return EngineHealth(
            status=EngineHealthStatus.HEALTHY,
            model_loaded=self._ready,
            gpu_available=False,
            detail="desenha a partir de receitas; não carrega modelo",
            metrics={"active_jobs": len(self._active)},
        )

    async def cancel(self, job_id: str) -> bool:
        return job_id in self._active

    def engine_ref(self) -> EngineRef:
        manifest = self.manifest()
        return EngineRef(
            id=manifest.id,
            version=manifest.version,
            provider=manifest.provider,
            model_id="receita://desenhista",
            model_revision=manifest.version,
        )

    # -- Execução --------------------------------------------------------
    async def generate(
        self,
        request: ImageGenerationRequest,
        context: EngineExecutionContext,
    ) -> EngineGenerationResult:
        manifest = self.manifest()
        if not self._ready:
            raise EngineExecutionError(
                "gaveta usada antes de initialize()", engine_id=manifest.id
            )
        context.cancellation.raise_if_cancelled()

        bruta = request.options_for(manifest.id).get("receita")
        if bruta is None:
            raise InvalidGenerationRequest(MENSAGEM_SEM_RECEITA, engine_id=manifest.id)

        if request.output.variations > manifest.limits.max_variations:
            raise InvalidGenerationRequest(
                f"o motor '{manifest.id}' entrega uma imagem por receita, e o pedido "
                f"trouxe {request.output.variations} variações — peça uma variação",
                engine_id=manifest.id,
            )

        logical = request.output.logical_size
        if logical is None:
            raise InvalidGenerationRequest(
                f"o motor '{manifest.id}' desenha numa grade lógica, e este pedido "
                "não tem uma (é um pedido de Pixel Art?)",
                engine_id=manifest.id,
            )
        largura, altura = logical

        started = time.perf_counter()
        self._active.add(context.job_id)
        try:
            try:
                receita = ler_receita(bruta)
                desenho = desenhar(receita, largura, altura)
            except ReceitaInvalida as exc:
                raise InvalidGenerationRequest(
                    f"receita inválida: {exc}", engine_id=manifest.id
                ) from exc

            usadas = desenho.grade.chaves_usadas()
            limite = request.output.max_colors
            if limite is not None and len(usadas) > limite:
                raise InvalidGenerationRequest(
                    f"receita inválida: o desenho usa {len(usadas)} cores "
                    f"({', '.join(sorted(usadas))}) e o pedido permite {limite}",
                    engine_id=manifest.id,
                )

            data = para_png(desenho.grade, receita.paleta)
            context.report(1.0, "generating", engine_id=manifest.id)
        finally:
            self._active.discard(context.job_id)

        return EngineGenerationResult(
            engine=self.engine_ref(),
            artifacts=(
                ImageArtifact(
                    index=0,
                    data=data,
                    width=largura,
                    height=altura,
                    seed=None,
                    metadata={
                        "renderer": "receita",
                        "camadas": [camada.nome for camada in receita.camadas],
                        "cores_usadas": len(usadas),
                        "receita_sha256": _impressao(bruta),
                    },
                ),
            ),
            timings=StageTimings(inference_ms=(time.perf_counter() - started) * 1000.0),
            warnings=desenho.avisos,
            engine_metadata={
                "engine": manifest.id,
                "grade": [largura, altura],
                "camadas": len(receita.camadas),
                "device": "cpu",
                # Os avisos desta gaveta, separados dos que o kernel acrescenta
                # (recurso não suportado, fallback): é daqui que o laudo do
                # MCP lê o que a receita teve de recortado.
                "avisos_receita": list(desenho.avisos),
                # De qual camada é cada pixel (Fase B2): o olho do app mede
                # por ele o contraste de valor entre partes vizinhas.
                "mapa_de_camadas": {
                    "nomes": [camada.nome for camada in receita.camadas],
                    "linhas": list(desenho.mapa_de_camadas),
                },
            },
        )


def _impressao(bruta: Any) -> str:
    """Identidade da receita, estável à ordem das chaves.

    Permite dizer, no histórico, que dois assets saíram da mesma receita — e é
    o que ajuda o remendo do MCP (``base: <id>``) a conferir a
    receita de origem.
    """
    texto = json.dumps(bruta, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
