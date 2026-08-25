"""Engine Contract — a interface única de toda gaveta (plano §8).

Este é o arquivo mais importante da arquitetura. Ele define o **único** ponto
de contato entre o AssetFlow e qualquer tecnologia de geração de imagem.

Regras de ouro (plano §73 e §74):

1. Nenhuma camada acima pode instanciar um pipeline de biblioteca de IA.
2. Nenhuma classe fora de ``generation/engines/<gaveta>/`` pode conhecer
   ``StableDiffusionXLPipeline``, ``FluxPipeline``, SDKs de fornecedores etc.
3. Se amanhã o modelo desaparecer, deve ser possível substituí-lo trocando
   apenas o conteúdo de uma pasta de engine e uma linha de configuração.

O teste ``tests/test_architecture_boundaries.py`` transforma essas regras em
falha de build.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from ..schemas import (
    Capability,
    EngineGenerationResult,
    EngineHealth,
    EngineManifest,
    EngineRef,
    EngineRuntimeConfig,
    ImageGenerationRequest,
)
from .exceptions import GenerationCancelled

__all__ = [
    "CancellationToken",
    "ProgressReporter",
    "NullProgressReporter",
    "EngineExecutionContext",
    "ImageGenerationEngine",
    "BaseImageGenerationEngine",
    "SemanticPromptAdapter",
    "EngineFactory",
]


class CancellationToken:
    """Sinal cooperativo de cancelamento (plano §46).

    O worker marca o token; o motor consulta entre etapas e para assim que
    for seguro. Ninguém mata processo de GPU no meio de uma inferência.
    """

    __slots__ = ("_event", "_reason")

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._reason: str | None = None

    def cancel(self, reason: str = "cancelamento solicitado") -> None:
        self._reason = reason
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        return self._reason

    def raise_if_cancelled(self) -> None:
        """Interrompe a execução se o cancelamento já foi pedido."""
        if self.is_cancelled:
            raise GenerationCancelled(self._reason or "cancelamento solicitado")

    async def wait(self) -> None:  # pragma: no cover - utilitário
        await self._event.wait()


@runtime_checkable
class ProgressReporter(Protocol):
    """Callback de progresso. Motores que não sabem reportar simplesmente
    não chamam — o contrato não obriga."""

    def __call__(self, progress: float, stage: str = "", **extra: Any) -> None:
        ...


class NullProgressReporter:
    """Implementação neutra usada quando ninguém está ouvindo."""

    def __call__(self, progress: float, stage: str = "", **extra: Any) -> None:
        return None


@dataclass(slots=True)
class EngineExecutionContext:
    """Tudo que a gaveta recebe além do request.

    Note o que **não** está aqui: projeto, usuário, storage, banco, fila.
    A gaveta não conhece o AssetFlow.
    """

    job_id: str
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    progress: ProgressReporter = field(default_factory=NullProgressReporter)
    workspace: Path | None = None
    deadline_s: float | None = None
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("assetflow.generation.engine")
    )

    def report(self, progress: float, stage: str = "", **extra: Any) -> None:
        """Reporta progresso ignorando qualquer erro do consumidor."""
        try:
            self.progress(max(0.0, min(1.0, progress)), stage, **extra)
        except Exception:  # pragma: no cover - observabilidade nunca quebra job
            self.logger.debug("progress reporter falhou", exc_info=True)


class ImageGenerationEngine(ABC):
    """Contrato obrigatório de toda gaveta de geração de imagem.

    Uma implementação recebe :class:`ImageGenerationRequest` (universal) e
    devolve :class:`EngineGenerationResult` (normalizado). O que acontece no
    meio é problema exclusivo da gaveta.
    """

    # -- Ciclo de vida ---------------------------------------------------
    @abstractmethod
    async def initialize(self, config: EngineRuntimeConfig) -> None:
        """Prepara a gaveta para uso (carregar modelo, abrir sessão, etc.).

        Deve ser idempotente: o lifecycle pode chamar mais de uma vez após
        um ``unload()``. Falhas devem virar
        :class:`~.exceptions.EngineInitializationError`.
        """

    @abstractmethod
    async def unload(self) -> None:
        """Libera memória/VRAM e recursos. Deve tolerar ser chamado duas vezes."""

    # -- Descoberta ------------------------------------------------------
    @abstractmethod
    def manifest(self) -> EngineManifest:
        """Manifesto da gaveta (plano §9). Deve funcionar sem inicialização."""

    @abstractmethod
    def capabilities(self) -> tuple[Capability, ...]:
        """Capacidades atendidas. Normalmente derivadas do manifesto."""

    @abstractmethod
    async def health_check(self) -> EngineHealth:
        """Diagnóstico rápido (plano §43). Não deve levantar exceção."""

    # -- Execução --------------------------------------------------------
    @abstractmethod
    async def generate(
        self,
        request: ImageGenerationRequest,
        context: EngineExecutionContext,
    ) -> EngineGenerationResult:
        """Gera imagens e devolve o resultado **já normalizado**.

        A conversão da saída nativa para o formato do AssetFlow é feita pelo
        Result Mapper interno da própria gaveta (plano §22).
        """

    @abstractmethod
    async def cancel(self, job_id: str) -> bool:
        """Pede o cancelamento de um job em andamento.

        Retorna ``True`` se a gaveta reconheceu o job. O cancelamento
        cooperativo via :class:`CancellationToken` continua sendo o caminho
        principal; este método existe para motores remotos que precisam
        avisar o outro lado.
        """

    # -- Opcional --------------------------------------------------------
    #
    # Sobre ``edit()`` (plano de motores §7)
    # -------------------------------------
    # O plano de motores desenha o contrato com três métodos: ``generate``,
    # ``edit`` e ``healthcheck``, e diz que "o contrato deve prever evolução".
    # Dois existem; ``edit`` **não foi criado**, e é uma decisão, não um
    # esquecimento.
    #
    # Um método abstrato novo quebraria toda gaveta existente de uma vez. Um
    # método opcional que levanta "não suportado" precisaria de um
    # ``AssetEditSpec`` que ninguém produz, de um caminho no Kernel que
    # ninguém chama e de um endpoint que não existe — código especulativo em
    # cima de um contrato que é a peça mais estável do sistema.
    #
    # O que o plano pede de fato é que acrescentá-lo depois **não** seja uma
    # mudança destrutiva, e isso já é verdade: um hook opcional com padrão,
    # exatamente como ``prompt_adapter()`` abaixo, entra a qualquer momento
    # sem tocar em nenhuma gaveta. A intenção, enquanto isso, já viaja no
    # manifesto — ``supports.inpainting`` e ``catalog.image_editing`` —, que é
    # o que permite ao catálogo anunciar o recurso antes de ele existir.
    def prompt_adapter(self) -> "SemanticPromptAdapter | None":
        """Adapter de prompt específico da gaveta (plano §27).

        Devolver ``None`` significa "use o texto neutro que já vem no
        request", produzido pelo adapter genérico do AssetFlow.

        Importante: **quem aplica o adapter é o Kernel**, antes de chamar
        :meth:`generate`. A gaveta recebe ``request.prompt`` já no seu
        próprio dialeto e não deve adaptar de novo.
        """
        return None

    def engine_ref(self) -> EngineRef:
        """Referência de rastreabilidade usada em resultados e metadados."""
        manifest = self.manifest()
        return EngineRef(
            id=manifest.id,
            version=manifest.version,
            provider=manifest.provider,
        )


@runtime_checkable
class SemanticPromptAdapter(Protocol):
    """Traduz a representação semântica para o formato ideal de um motor."""

    def adapt(self, request: ImageGenerationRequest) -> tuple[str, str | None]:
        """Devolve ``(positive, negative)`` para este motor específico."""
        ...


#: Como o registry cria instâncias da gaveta (sem argumentos).
EngineFactory = Callable[[], ImageGenerationEngine]


class BaseImageGenerationEngine(ImageGenerationEngine):
    """Base opcional que remove boilerplate de quem escreve uma gaveta.

    Fornece:

    - carregamento do ``manifest.json`` que vive ao lado do módulo;
    - ``capabilities()`` derivado do manifesto;
    - controle de jobs ativos para cancelamento;
    - ``health_check()`` genérico baseado no estado de inicialização.

    Herdar daqui é conveniência, não obrigação: qualquer classe que cumpra
    :class:`ImageGenerationEngine` é uma gaveta válida.
    """

    #: Caminho do manifesto relativo ao arquivo do módulo concreto.
    manifest_filename: str = "manifest.json"

    def __init__(self) -> None:
        self._config: EngineRuntimeConfig | None = None
        self._initialized = False
        self._active_jobs: set[str] = set()
        self._logger = logging.getLogger(f"assetflow.engine.{type(self).__name__}")

    # -- Manifesto -------------------------------------------------------
    @classmethod
    def manifest_path(cls) -> Path:
        import inspect

        module_file = inspect.getfile(cls)
        return Path(module_file).resolve().parent / cls.manifest_filename

    @classmethod
    def load_manifest(cls) -> EngineManifest:
        """Lê e valida o ``manifest.json`` do pacote da gaveta."""
        path = cls.manifest_path()
        with path.open("r", encoding="utf-8") as handle:
            return EngineManifest.model_validate(json.load(handle))

    def manifest(self) -> EngineManifest:
        cached = getattr(type(self), "_manifest_cache", None)
        if cached is None:
            cached = self.load_manifest()
            setattr(type(self), "_manifest_cache", cached)
        return cached

    def capabilities(self) -> tuple[Capability, ...]:
        return self.manifest().capabilities

    # -- Ciclo de vida ---------------------------------------------------
    async def initialize(self, config: EngineRuntimeConfig) -> None:
        self._config = config
        await self.on_initialize(config)
        self._initialized = True

    async def on_initialize(self, config: EngineRuntimeConfig) -> None:
        """Hook para subclasses. Padrão: nada a fazer."""
        return None

    async def unload(self) -> None:
        await self.on_unload()
        self._initialized = False
        self._active_jobs.clear()

    async def on_unload(self) -> None:
        """Hook para subclasses. Padrão: nada a fazer."""
        return None

    @property
    def config(self) -> EngineRuntimeConfig:
        if self._config is None:
            raise RuntimeError("engine usado antes de initialize()")
        return self._config

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # -- Saúde -----------------------------------------------------------
    async def health_check(self) -> EngineHealth:
        from ..schemas import EngineHealthStatus

        return EngineHealth(
            status=EngineHealthStatus.HEALTHY,
            model_loaded=self._initialized,
            gpu_available=False,
            detail=None,
            metrics={"active_jobs": len(self._active_jobs)},
        )

    # -- Cancelamento ----------------------------------------------------
    async def cancel(self, job_id: str) -> bool:
        return job_id in self._active_jobs

    def _track(self, job_id: str) -> None:
        self._active_jobs.add(job_id)

    def _untrack(self, job_id: str) -> None:
        self._active_jobs.discard(job_id)

    def engine_ref(self) -> EngineRef:
        manifest = self.manifest()
        model = self._config.model if self._config else None
        return EngineRef(
            id=manifest.id,
            version=manifest.version,
            provider=manifest.provider,
            model_id=model.id if model else None,
            model_revision=model.revision if model else None,
        )
