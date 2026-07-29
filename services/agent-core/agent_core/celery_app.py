"""Celery-приложение AGORA (Decision Log #3: Valkey + Celery + SSE).

LangGraph-пайплайн живёт ВНУТРИ Celery-задачи, а не рядом с ней: так задача
резюмируется через чекпоинтер, а прогресс узлов пишется в Valkey и уходит в SSE.
Сам пайплайн собирается на задаче #13 — здесь только приложение и очередь.
"""
from __future__ import annotations

import os

from celery import Celery

_broker = os.environ.get("VALKEY_URL", "redis://localhost:6379/0")

app = Celery(
    "agora",
    broker=_broker,
    # Результаты держим в том же Valkey: отчёт всё равно уезжает в Postgres/Mongo,
    # а здесь нужен только статус выполнения для SSE-прогресса.
    backend=_broker,
    include=[],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Видео-пайплайн долгий: подтверждаем задачу только после выполнения, чтобы
    # падение воркера возвращало её в очередь, а не теряло прогон.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Жёсткий потолок на прогон, чтобы зависшая транскрипция не держала слот вечно.
    task_time_limit=int(os.environ.get("TASK_TIME_LIMIT", 3 * 60 * 60)),
    task_soft_time_limit=int(os.environ.get("TASK_SOFT_TIME_LIMIT", 165 * 60)),
)


@app.task(name="agora.ping")
def ping() -> str:
    """Smoke-задача: проверяет, что брокер жив и воркер разбирает очередь."""
    return "pong"
