"""
Celery-задача, внутри которой крутится граф (PRD §8, Decision Log #3).

─── Почему граф внутри задачи, а не рядом ───────────────────────────────────
Celery отвечает за очередь и за то, что упавший воркер вернёт задачу в неё
(`task_acks_late`). LangGraph отвечает за то, что вернувшаяся задача продолжится
с последнего узла, а не с начала. Одно без другого бесполезно: очередь без
чекпоинта повторяет пятнадцатиминутную транскрипцию, чекпоинт без очереди
некому подхватить.

─── thread_id = task_id ─────────────────────────────────────────────────────
LangGraph различает прогоны по `thread_id`. Здесь это идентификатор задачи из
Postgres, и совпадение не для красоты: ретрай Celery приходит с тем же task_id,
находит свой чекпоинт и продолжает. Сгенерируй мы thread_id заново — каждый
ретрай начинал бы чистый прогон, а внешне это неотличимо от медленной системы.

─── Статус в базе, а не только в Valkey ─────────────────────────────────────
Прогресс в Valkey живёт сутки и нужен экрану (#12). Итоговый статус пишется в
`tasks.status`, потому что список исследований переживает перезапуск Valkey, а
прогон, потерявший статус, выглядит вечно выполняющимся.
"""

from __future__ import annotations

import os
from typing import Any

from ..celery_app import app
from .state import STATUS_CANCELLED, STATUS_FAILED, STATUS_REPORT_READY, STATUS_RUNNING


def _valkey():
    import redis

    return redis.Redis.from_url(os.environ.get("VALKEY_URL", "redis://localhost:6379/0"))


def _set_task_status(task_id: str, tenant_id: str, status: str, error: str | None = None) -> None:
    """
    Статус прогона в Postgres. Отсутствие DSN — не повод ронять прогон.

    `started_at` ставится один раз, при первом переходе в RUNNING: возобновление
    с чекпоинта не должно обнулять отсчёт, иначе «время обработки» покажет
    длительность последней попытки вместо всего прогона.
    """
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return

    import psycopg

    from ..db import tenant_scope

    with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
        cur.execute(
            "UPDATE tasks SET status = %s, error = %s, "
            "started_at = CASE WHEN %s = 'RUNNING' THEN COALESCE(started_at, now()) "
            "                  ELSE started_at END, "
            "finished_at = CASE WHEN %s IN ('REPORT_READY','FAILED','CANCELLED') "
            "                   THEN now() ELSE NULL END "
            "WHERE id = %s::uuid",
            (status, error, status, status, task_id),
        )


def _save_timings(task_id: str, tenant_id: str, timings: list[dict[str, Any]]) -> None:
    """
    Складывает замеры этапов в `tasks.progress`.

    Колонка заведена в схеме с первого дня и не писалась никем. Снимок прогресса
    живёт в Valkey с TTL и перезаписывается на каждое событие — то есть разбивка
    «сколько занял какой этап» существовала только пока прогон идёт, да и то в
    виде текущего узла. Экран исследования показывает «Время обработки», и на
    вопрос «за что заплачено» отвечать было нечем.

    Отказ записи не роняет прогон и не меняет статус: замеры — служебная
    информация, а отчёт к этому моменту уже посчитан и сохранён.
    """
    dsn = os.environ.get("DATABASE_URL")
    if not dsn or not timings:
        return

    import json as _json

    import psycopg

    from ..db import tenant_scope

    try:
        with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
            cur.execute(
                "UPDATE tasks SET progress = %s WHERE id = %s::uuid",
                (_json.dumps({"timings": timings}, ensure_ascii=False), task_id),
            )
    except Exception:  # noqa: BLE001 — см. докстринг
        pass


def _cancel_requested(task_id: str, tenant_id: str) -> bool:
    """
    Просили ли отменить этот прогон.

    Читается из Postgres, а не из Valkey, намеренно: отмену запрашивает веб, и
    единственное место, где это состояние переживёт перезапуск чего угодно, —
    строка задачи. Valkey держит прогресс с суточным TTL и чекпоинты; класть
    туда решение пользователя значило бы, что отмена может истечь.

    Отказ базы не считается отменой. Иначе потеря связи с Postgres на секунду
    останавливала бы прогон, за который уже заплачено, и выглядело бы это как
    самопроизвольная отмена.
    """
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return False

    import psycopg

    from ..db import tenant_scope

    try:
        with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
            cur.execute(
                "SELECT cancel_requested_at IS NOT NULL FROM tasks WHERE id = %s::uuid",
                (task_id,),
            )
            row = cur.fetchone()
            return bool(row and row[0])
    except Exception:  # noqa: BLE001 — см. докстринг: отказ базы не отмена
        return False


@app.task(name="agora.run_pipeline", bind=True)
def run_pipeline(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Прогон исследования.

    `payload` — параметры запуска из #11: task_id, tenant_id, mode, video_ref,
    persona_ids, survey, replication_count, prompts_snapshot, settings_snapshot.

    Повторный вызов с тем же task_id НЕ начинает заново: граф поднимает
    чекпоинт по thread_id и продолжает с места отказа. Ради этого в
    `graph.invoke` передаётся None вместо состояния, когда чекпоинт уже есть, —
    иначе начальное состояние затёрло бы накопленное.
    """
    from .checkpoint import ValkeyCheckpointSaver
    from .graph import RunCancelled, build_graph
    from .progress import ProgressWriter
    from .state import new_state

    task_id = str(payload["task_id"])
    tenant_id = str(payload["tenant_id"])

    valkey = _valkey()
    progress = ProgressWriter(valkey, task_id)
    checkpointer = ValkeyCheckpointSaver(valkey)
    graph = build_graph(
        checkpointer=checkpointer,
        progress=progress,
        is_cancelled=lambda: _cancel_requested(task_id, tenant_id),
    )
    config = {"configurable": {"thread_id": task_id}}

    resuming = checkpointer.get_tuple(config) is not None
    initial = None if resuming else new_state(
        task_id=task_id,
        tenant_id=tenant_id,
        mode=payload.get("mode", "short"),
        video_ref=payload.get("video_ref"),
        persona_ids=payload.get("persona_ids") or [],
        survey=payload.get("survey"),
        replication_count=int(payload.get("replication_count") or 1),
        prompts_snapshot=payload.get("prompts_snapshot") or {},
        settings_snapshot=payload.get("settings_snapshot") or {},
    )

    _set_task_status(task_id, tenant_id, STATUS_RUNNING)
    progress.emit("pipeline", STATUS_RUNNING, detail="возобновление" if resuming else "запуск")

    try:
        final = graph.invoke(initial, config)
    except RunCancelled as e:
        # Отмена — не отказ. Отдельный статус, чтобы в списке было видно, что
        # прогон остановили, а не что он сломался.
        _set_task_status(task_id, tenant_id, STATUS_CANCELLED, str(e))
        progress.emit("pipeline", STATUS_CANCELLED, detail=str(e))
        return {"task_id": task_id, "status": STATUS_CANCELLED, "degraded": []}
    except Exception as e:  # noqa: BLE001 — статус и причина обязаны дойти до пользователя
        reason = f"{type(e).__name__}: {e}"
        _set_task_status(task_id, tenant_id, STATUS_FAILED, reason)
        # Узел уже записал свой FAILED с точным местом; здесь фиксируется итог
        # прогона, чтобы экран не остался на RUNNING после смерти воркера.
        progress.fail("pipeline", reason)
        raise

    _set_task_status(task_id, tenant_id, STATUS_REPORT_READY)
    snapshot = progress.emit(
        "pipeline", STATUS_REPORT_READY, degraded=final.get("degraded") or []
    )
    _save_timings(task_id, tenant_id, snapshot.get("timings") or [])
    return {
        "task_id": task_id,
        "status": STATUS_REPORT_READY,
        "degraded": final.get("degraded") or [],
    }
