"""Celery-приложение AGORA (Decision Log #3: Valkey + Celery + SSE).

LangGraph-пайплайн живёт ВНУТРИ Celery-задачи, а не рядом с ней: так задача
резюмируется через чекпоинтер, а прогресс узлов пишется в Valkey и уходит в SSE.
Сам пайплайн собран на задаче #13 в `agent_core.pipeline`.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from celery import Celery

logger = logging.getLogger(__name__)

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

#: Как часто искать осиротевшие прогоны. См. `maintenance/reaper.py`.
REAP_INTERVAL_SEC = int(os.environ.get("REAP_INTERVAL_SEC", 15 * 60))

#: Как держится соединение с брокером на длинном узле.
#:
#: ─── Что чинится ──────────────────────────────────────────────────────────
#: Прогон 0052 (21.08.2026) упал через 61 минуту с
#: «ConnectionError: Error 32 while writing to socket. Broken pipe», причём в
#: логе это помечено как `Exception raised outside body` — отказ пришёл не из
#: пайплайна, а из обращения Celery к брокеру: подтвердить задачу и записать
#: результат.
#:
#: Пока идёт длинный узел (распознавание пятидесятиминутного фильма — больше
#: часа), по соединению не передаётся ничего. Простаивающее соединение закрывает
#: либо сам Valkey по своему `timeout`, либо промежуточное оборудование. Клиент
#: об этом не знает: сокет выглядит открытым, и о разрыве он узнаёт в момент
#: записи — то есть когда работа уже сделана и оплачена.
#:
#: ─── Почему три настройки, а не одна ──────────────────────────────────────
#: `socket_keepalive` держит соединение живым через оборудование, но не спасает
#: от закрытия сервером по таймауту. `health_check_interval` переоткрывает
#: мёртвое соединение до записи, но между проверкой и записью есть окно.
#: Повтор при разрыве (`retry_on_timeout` и политика повторов клиента) закрывает
#: это окно.
BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": VISIBILITY_TIMEOUT_SEC,
    "socket_keepalive": True,
    "health_check_interval": 30,
    "retry_on_timeout": True,
}

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
    broker_transport_options=BROKER_TRANSPORT_OPTIONS,
    # Результаты идут в тот же Valkey и по ОТДЕЛЬНОМУ соединению: настроить одно
    # и забыть второе значит починить половину отказов.
    result_backend_transport_options=BROKER_TRANSPORT_OPTIONS,
    # ─── Сборщик осиротевших прогонов ───────────────────────────────────────
    #
    # Прогон, чей воркер убит извне (SIGKILL по нехватке памяти), остаётся
    # RUNNING навсегда: статус ставит сам конвейер из блока except, а SIGKILL
    # исключения не возбуждает. Такую строку не переведёт в FAILED никто —
    # ни Celery, ни веб, ни следующий прогон.
    #
    # Расписание, а не проверка на чтении списка: сирота мешает не только
    # тому, кто смотрит. Пока он RUNNING, его нельзя удалить (DELETE отвечает
    # 202 «отмена запрошена» и ждёт остановки, которой не будет).
    #
    # Раз в пятнадцать минут: сборщик читает `teams` и по строке на арендатора,
    # это дешевле любого прогона на три порядка, а задержка обнаружения и так
    # определяется отсрочкой молчания в 45 минут.
    beat_schedule={
        "reap-orphans": {
            "task": "agora.reap_orphans",
            "schedule": REAP_INTERVAL_SEC,
        },
    },
)


@app.task(name="agora.ping")
def ping() -> str:
    """Smoke-задача: проверяет, что брокер жив и воркер разбирает очередь."""
    return "pong"


@app.task(name="agora.reap_orphans")
def reap_orphans() -> dict[str, Any]:
    """
    Переводит в FAILED прогоны, чей воркер умер, не успев обновить статус.

    Задача намеренно тонкая: вся логика — в `maintenance.reaper`, потому что
    решение «жив ли прогон» проверяется арифметикой, а не живой базой. Здесь
    только расписание и журнал.
    """
    from .maintenance.reaper import sweep

    found = sweep(apply=True)
    orphans = [f for f in found if "error" not in f]
    problems = [f for f in found if "error" in f]

    for o in orphans:
        logger.warning(
            "Осиротевший прогон %s переведён в FAILED: %s", o["task_id"][:8], o["reason"]
        )
    for p in problems:
        logger.error("Сборщик не обошёл арендатора %s: %s", p["tenant_id"][:8], p["error"])

    return {"orphans": len(orphans), "problems": len(problems)}
