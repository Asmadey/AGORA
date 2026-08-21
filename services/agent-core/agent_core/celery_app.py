"""Celery-приложение AGORA (Decision Log #3: Valkey + Celery + SSE).

LangGraph-пайплайн живёт ВНУТРИ Celery-задачи, а не рядом с ней: так задача
резюмируется через чекпоинтер, а прогресс узлов пишется в Valkey и уходит в SSE.
Сам пайплайн собран на задаче #13 в `agent_core.pipeline`.
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
    # Модуль задач перечисляется явно: без него воркер поднимется, очередь
    # разберёт, а на agora.run_pipeline ответит «Received unregistered task» —
    # то есть отказ будет выглядеть как проблема очереди, а не как незагруженный
    # модуль. Импорт здесь дешёвый: граф и langgraph подтягиваются внутри задачи.
    # Модули с задачами перечисляются явно: автообнаружение прошло бы по всему
    # пакету и импортировало бы тяжёлые зависимости там, где они не нужны.
    include=["agent_core.pipeline.tasks", "agent_core.persona.tasks"],
)

#: Жёсткий потолок на прогон, чтобы зависшая транскрипция не держала слот вечно.
TIME_LIMIT_SEC = int(os.environ.get("TASK_TIME_LIMIT", 3 * 60 * 60))
SOFT_TIME_LIMIT_SEC = int(os.environ.get("TASK_SOFT_TIME_LIMIT", 165 * 60))

#: Потолок невидимости сообщения — сколько брокер ждёт, прежде чем счесть
#: выданную задачу потерянной и выдать её снова.
#:
#: ─── Почему он обязан быть больше жёсткого лимита ────────────────────────
#: У Valkey/Redis нет подтверждений на уровне протокола: kombu эмулирует их
#: таймаутом невидимости, и умолчание — час. С `task_acks_late=True`
#: сообщение остаётся неподтверждённым всё время исполнения, поэтому любая
#: задача длиннее часа выдаётся второй раз, пока первая ещё работает.
#:
#: Прогон 0051 (19.08.2026, фильм 50 минут) на этом и сломался: трасса
#: разорвана на 09:36 и 10:35 — ровно час, — а в 10:41 ядро убило celery по
#: нехватке памяти. Два пайплайна с parakeet и pyannote в одну машину не
#: помещаются. Выглядело это как случайный OOM, а не как настройка очереди.
#:
#: Запас поверх лимита — на выгрузку моделей и запись отчёта после того, как
#: `task_time_limit` уже сработал: подтверждение приходит не в момент отсечки,
#: а после выхода из задачи.
VISIBILITY_TIMEOUT_SEC = TIME_LIMIT_SEC + 30 * 60

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
    task_time_limit=TIME_LIMIT_SEC,
    task_soft_time_limit=SOFT_TIME_LIMIT_SEC,
    broker_transport_options={"visibility_timeout": VISIBILITY_TIMEOUT_SEC},
)


@app.task(name="agora.ping")
def ping() -> str:
    """Smoke-задача: проверяет, что брокер жив и воркер разбирает очередь."""
    return "pong"
