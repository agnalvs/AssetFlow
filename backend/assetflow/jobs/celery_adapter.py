"""Ponte para Celery/Redis (plano §32 e §34) — ainda não ativada.

Este arquivo documenta, em código, **como** trocar o broker in-process por um
sistema de filas distribuído sem tocar em nenhuma outra camada. Ele não
importa Celery: a dependência só entra quando o adapter for ativado.

Passos da migração (nenhum deles altera kernel, pipelines ou API):

1. Implementar :class:`~assetflow.jobs.queue.JobQueue` publicando em Celery::

       class CeleryJobQueue(JobQueue):
           def __init__(self, app, task_name="assetflow.run_job"): ...
           async def enqueue(self, job_id, *, queue=DEFAULT_QUEUE, priority=0):
               self._app.send_task(self._task_name, args=[job_id], queue=queue)
           async def dequeue(self, queues, *, timeout=None):
               raise NotImplementedError("quem consome é o worker Celery")

2. Implementar um :class:`~assetflow.jobs.store.JobStore` compartilhado
   (Postgres/Redis) — o store em memória não atravessa processos.

3. Registrar a task Celery que chama o worker existente::

       @app.task(name="assetflow.run_job")
       def run_job(job_id: str) -> None:
           asyncio.run(container.worker._execute(job_id))

4. Rotear filas por capacidade em ``QueueRouter`` (``generation.pixel``,
   ``generation.high_memory``) e subir workers dedicados por GPU.

O ponto arquitetural: o Job System conversa com o Kernel por interfaces, e o
Kernel conversa com os motores por contrato. Trocar o broker é uma decisão de
infraestrutura, não de produto.
"""

from __future__ import annotations

__all__: list[str] = []
