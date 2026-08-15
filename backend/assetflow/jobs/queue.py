"""Fila de jobs (planos §32, §33 e §34).

O AssetFlow precisa poder rodar assim:

    Browser -> API -> Broker -> GPU Worker -> Engine

O broker em memória existe para desenvolvimento e testes. Trocá-lo por
Redis/Celery é implementar :class:`JobQueue` — nenhuma outra camada muda.

Filas por capacidade já são suportadas desde agora (``generation.pixel``,
``generation.high_memory``, ...), mesmo que só uma seja usada no início.
"""

from __future__ import annotations

import asyncio
import itertools
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Sequence

from ..generation.schemas import Capability

__all__ = [
    "DEFAULT_QUEUE",
    "QueuedJob",
    "JobQueue",
    "InMemoryJobQueue",
    "QueueRouter",
]

DEFAULT_QUEUE = "generation.default"


@dataclass(order=True, slots=True)
class QueuedJob:
    """Item da fila. Ordenação: prioridade desc, depois FIFO."""

    sort_key: tuple[int, int] = field(init=False, repr=False)
    priority: int = 0
    sequence: int = 0
    job_id: str = field(default="", compare=False)
    queue: str = field(default=DEFAULT_QUEUE, compare=False)

    def __post_init__(self) -> None:
        self.sort_key = (-self.priority, self.sequence)


class JobQueue(ABC):
    """Broker abstrato de jobs."""

    @abstractmethod
    async def enqueue(
        self, job_id: str, *, queue: str = DEFAULT_QUEUE, priority: int = 0
    ) -> None:
        ...

    @abstractmethod
    async def dequeue(
        self, queues: Sequence[str], *, timeout: float | None = None
    ) -> QueuedJob | None:
        """Retira o próximo job das filas informadas, ou `None` no timeout."""

    @abstractmethod
    async def size(self, queue: str = DEFAULT_QUEUE) -> int:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class InMemoryJobQueue(JobQueue):
    """Broker in-process baseado em ``asyncio``.

    Suficiente para desenvolvimento, testes e execução single-node. Não
    sobrevive a reinício — por isso a interface existe.
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[QueuedJob]] = {}
        self._counter = itertools.count()
        self._condition = asyncio.Condition()
        self._closed = False

    async def enqueue(
        self, job_id: str, *, queue: str = DEFAULT_QUEUE, priority: int = 0
    ) -> None:
        item = QueuedJob(
            priority=priority, sequence=next(self._counter), job_id=job_id, queue=queue
        )
        async with self._condition:
            bucket = self._queues.setdefault(queue, [])
            bucket.append(item)
            bucket.sort()
            self._condition.notify_all()

    async def dequeue(
        self, queues: Sequence[str], *, timeout: float | None = None
    ) -> QueuedJob | None:
        names = tuple(queues) or (DEFAULT_QUEUE,)

        async with self._condition:
            item = self._pop(names)
            if item is not None:
                return item
            if self._closed:
                return None
            try:
                await asyncio.wait_for(
                    self._condition.wait_for(
                        lambda: self._closed or self._has_any(names)
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                return None
            return self._pop(names)

    def _has_any(self, names: Sequence[str]) -> bool:
        return any(self._queues.get(name) for name in names)

    def _pop(self, names: Sequence[str]) -> QueuedJob | None:
        for name in names:
            bucket = self._queues.get(name)
            if bucket:
                return bucket.pop(0)
        return None

    async def size(self, queue: str = DEFAULT_QUEUE) -> int:
        return len(self._queues.get(queue, ()))

    async def close(self) -> None:
        async with self._condition:
            self._closed = True
            self._condition.notify_all()


class QueueRouter:
    """Escolhe a fila de destino a partir da capacidade (plano §33).

    Configurável; por padrão tudo cai em ``generation.default``.
    """

    def __init__(
        self,
        routes: dict[str, str] | None = None,
        *,
        default: str = DEFAULT_QUEUE,
    ) -> None:
        self._routes = {
            str(Capability.parse(key)): value for key, value in (routes or {}).items()
        }
        self._default = default

    @property
    def default(self) -> str:
        return self._default

    def queues(self) -> tuple[str, ...]:
        """Todas as filas conhecidas, com a padrão em primeiro lugar."""
        names = [self._default]
        names.extend(name for name in self._routes.values() if name not in names)
        return tuple(names)

    def route(self, capability: Capability | str) -> str:
        return self._routes.get(str(Capability.parse(capability)), self._default)
