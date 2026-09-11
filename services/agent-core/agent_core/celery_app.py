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
from celery.signals import worker_ready

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

#: Как часто пересчитывать мусор в хранилищах. См. `maintenance/orphan_storage.py`.
#:
#: Раз в сутки: проход листает бакет целиком, а копится мусор днями. Своим
#: интервалом, а не общим с уборками выше, — он на два порядка дороже их.
SWEEP_INTERVAL_SEC = int(os.environ.get("SWEEP_INTERVAL_SEC", 24 * 60 * 60))

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
        # Тем же расписанием, а не своим: обе уборки дешёвые, а второй интервал
        # означал бы вторую настройку, которую однажды поправят только в одном
        # месте. Разбор /proc стоит меньше миллисекунды на процесс.
        "reap-zombies": {
            "task": "agora.reap_zombies",
            "schedule": REAP_INTERVAL_SEC,
        },
        # Раз в сутки, а не раз в четверть часа: проход обходит бакет целиком
        # постраничным листингом, а мусор копится днями, не минутами. И в
        # отличие от двух соседей выше, этот НИЧЕГО НЕ УДАЛЯЕТ — он называет
        # найденное в логе. Почему так, написано у самой задачи.
        "sweep-storage": {
            "task": "agora.sweep_storage",
            "schedule": SWEEP_INTERVAL_SEC,
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


@app.task(name="agora.reap_zombies")
def reap_zombies() -> dict[str, Any]:
    """
    Подталкивает родителей зомби-процессов и докладывает о зависших.

    Задача намеренно тонкая — по тому же доводу, что и `reap_orphans`: разбор
    `/proc` проверяется на поддельном каталоге, а не на живой системе, поэтому
    вся логика лежит в `maintenance.zombies`.

    Смотрит внутрь СВОЕГО контейнера: пространство PID у воркера своё, и те два
    зомби от 08.09.2026 были детьми главного процесса celery, то есть видны
    отсюда. Хостовые процессы этой задаче не видны и не её забота.
    """
    from .maintenance.zombies import sweep

    result = sweep(apply=True)

    for z in result["stale"]:
        logger.warning(
            "Зомби-процесс %s (%s) висит %s мин; родителю %s послан SIGCHLD",
            z["pid"], z["comm"], z["minutes"], z["ppid"],
        )

    return {"zombies": result["total"], "stale": len(result["stale"])}


@app.task(name="agora.sweep_storage")
def sweep_storage() -> dict[str, Any]:
    """
    Пересчитывает мусор в S3, Mongo и слепках корпуса — и НЕ удаляет его.

    ─── Почему по расписанию только счёт ────────────────────────────────────
    Уборка при удалении исследования уже есть и делает своё дело. Этот проход
    закрывает то, чего она закрыть не может: её отказ не повторяется, потому
    что строка, хранившая адреса объектов, к тому моменту удалена.

    Но сам проход отвечает на вопрос сравнением ТРЁХ хранилищ, и цена его
    ошибки несимметрична. Ошибся в сторону молчания — заняты гигабайты. Ошибся
    в обратную — удалены кадры и отчёты живых исследований, и восстановить их
    неоткуда. Автоматическое удаление по такому сравнению стоит дороже мусора,
    который оно убирает.

    Поэтому расписание превращает невидимое в названное: в логе появляется
    строка «столько-то объектов на столько-то мегабайт никому не принадлежат».
    Раньше заметить это было неоткуда — экран чист, место занято, а счёт за
    хранилище приходит раз в месяц и не объясняет, чем.

    Удаление — отдельное решение человека:
    `python -m agent_core.maintenance.orphan_storage --apply`.

    ─── Что бывает вместо прохода ───────────────────────────────────────────
    Отказ. Под политикой миграции 41 владелец схемы видит только RUNNING, и
    пустой ответ означал бы «всё осиротело». `assert_full_task_visibility`
    останавливает проход до первого чтения; пока миграция 42 не применена,
    задача пишет в лог причину и возвращает пустой результат, а не догадку.
    """
    from .maintenance.orphan_storage import sweep as sweep_impl

    try:
        import os

        import psycopg

        from .mongo import mongo_db
        from .storage import Boto3S3

        dsn = os.environ.get("POSTGRES_ADMIN_URL")
        if not dsn:
            logger.warning("Уборка хранилищ пропущена: POSTGRES_ADMIN_URL не задан")
            return {"skipped": "POSTGRES_ADMIN_URL"}

        s3 = Boto3S3()
        with psycopg.connect(dsn) as conn:
            result = sweep_impl(
                apply=False,
                conn=conn,
                s3=s3.client,
                bucket=s3.bucket,
                mongo=mongo_db(),
            )
    except Exception as exc:  # noqa: BLE001 — уборка не вправе ронять воркер
        logger.warning("Уборка хранилищ не выполнена: %s", exc)
        return {"skipped": str(exc)}

    s3r = result.get("s3", {})
    mongo_total = sum(result.get("mongo", {}).values())
    snapshots = result.get("слепки", 0)
    if s3r.get("байт") or mongo_total or snapshots:
        logger.warning(
            "Мусор в хранилищах: S3 %s объектов (%.1f МБ), Mongo %s документов, "
            "слепков корпуса %s. Удаление: "
            "python -m agent_core.maintenance.orphan_storage --apply",
            s3r.get("кадров прогонов", 0) + s3r.get("загрузок", 0),
            s3r.get("байт", 0) / 1024 / 1024,
            mongo_total,
            snapshots,
        )

    return result


@worker_ready.connect
def _report_memory_budget(**_: object) -> None:
    """
    Печатает бюджет памяти при старте воркера.

    Не отказ, а число в журнале. Отказ на старте означал бы, что ошибка в
    чтении памяти кладёт продукт целиком, а падающей проверкой здесь работает
    метрика `worker_memory_budget` в `evals/check.py`: она не может уронить
    боевой сервер и при этом краснеет, пока нарушение живо.

    Здесь — то, что видит человек, когда воркер уже умер и он ищет причину.
    `WorkerLostError: signal 9` про память не говорит ничего.

    ─── Почему именно этот сигнал ──────────────────────────────────────────
    Сначала отчёт висел на первом сигнале celery. 11.09.2026 на боевом он
    отработал БЕЗ ЕДИНОЙ ОШИБКИ и не оставил в журнале ничего: логирование к
    тому моменту ещё не настроено, и запись теряется молча.

    Отчёт, которого не видно, ничем не отличается от отсутствующего — а
    молчащая проверка хуже отсутствующей, потому что на неё рассчитывают.
    Здесь сигнал приходит, когда воркер уже готов принимать задачи, то есть
    после настройки логирования.
    """
    import sys

    from .maintenance.memory_budget import (
        budget,
        max_concurrency,
        parse_concurrency,
        read_total_gb,
    )

    command = " ".join(sys.argv)
    concurrency = parse_concurrency(command)
    total_gb = read_total_gb()

    if total_gb is None:
        logger.warning("Бюджет памяти не проверен: не удалось прочитать объём памяти")
        return

    if concurrency is None:
        # Без флага celery берёт число ядер — на машине по спецификации это
        # восемь процессов по 5,4 ГБ.
        logger.warning(
            "Число процессов не задано флагом: celery возьмёт число ядер. "
            "На %.1f ГБ помещается %d — задайте --concurrency явно",
            total_gb,
            max_concurrency(total_gb),
        )
        return

    verdict = budget(concurrency=concurrency, total_gb=total_gb)
    (logger.info if verdict.fits else logger.error)("Бюджет памяти: %s", verdict.reason)
