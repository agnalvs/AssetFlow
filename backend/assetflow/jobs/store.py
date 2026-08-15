"""Persistência de jobs.

A interface é abstrata de propósito: a implementação em memória serve para
desenvolvimento e testes, e uma implementação em banco relacional entra
depois sem tocar em worker, kernel ou API.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from ..generation.kernel.exceptions import JobNotFound
from ..generation.schemas import Job, JobStatus

__all__ = ["JobStore", "InMemoryJobStore"]


class JobStore(ABC):
    """Contrato de armazenamento de jobs."""

    @abstractmethod
    async def create(self, job: Job) -> Job:
        ...

    @abstractmethod
    async def get(self, job_id: str) -> Job:
        """Raises: JobNotFound."""

    @abstractmethod
    async def find(self, job_id: str) -> Job | None:
        ...

    @abstractmethod
    async def update(self, job: Job) -> Job:
        ...

    @abstractmethod
    async def list(
        self,
        *,
        project_id: str | None = None,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        ...

    @abstractmethod
    async def count(self, *, project_id: str | None = None) -> int:
        ...

    def peek(self, job_id: str) -> Job | None:
        """Acesso **síncrono** ao job, usado apenas para reportar progresso.

        Implementações remotas devem devolver ``None`` (o padrão): nesse
        caso o progresso passa a ser publicado em cada transição de status,
        e não a cada passo do motor.
        """
        return None


class InMemoryJobStore(JobStore):
    """Store em memória.

    Guarda a instância viva do :class:`Job` — o worker e o JobManager
    trabalham sobre o mesmo objeto, o que torna o progresso visível na API
    sem round-trip. Uma implementação em banco deve, obviamente, persistir
    de verdade em cada transição.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = asyncio.Lock()

    async def create(self, job: Job) -> Job:
        async with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        return job

    async def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFound(f"job '{job_id}' não encontrado", detail={"job_id": job_id})
        return job

    async def find(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def update(self, job: Job) -> Job:
        async with self._lock:
            if job.id not in self._jobs:
                raise JobNotFound(f"job '{job.id}' não encontrado")
            self._jobs[job.id] = job
        return job

    async def list(
        self,
        *,
        project_id: str | None = None,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        jobs = [self._jobs[job_id] for job_id in reversed(self._order) if job_id in self._jobs]
        if project_id is not None:
            jobs = [job for job in jobs if job.project_id == project_id]
        if status is not None:
            jobs = [job for job in jobs if job.status is status]
        return jobs[offset : offset + limit]

    async def count(self, *, project_id: str | None = None) -> int:
        if project_id is None:
            return len(self._jobs)
        return sum(1 for job in self._jobs.values() if job.project_id == project_id)

    def peek(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)
