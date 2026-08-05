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
from .state import STATUS_FAILED, STATUS_REPORT_READY, STATUS_RUNNING


def _valkey():
    import redis

    return redis.Redis.from_url(os.environ.get("VALKEY_URL", "redis://localhost:6379/0"))


def _set_task_status(task_id: str, tenant_id: str, status: str, error: str | None = None) -> None:
    """Статус прогона в Postgres. Отсутствие DSN — не повод ронять прогон."""
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return

    import psycopg

    from ..db import tenant_scope

    with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
        cur.execute(
            "UPDATE tasks SET status = %s, error = %s, "
            "finished_at = CASE WHEN %s IN ('REPORT_READY','FAILED') THEN now() ELSE NULL END "
            "WHERE id = %s::uuid",
            (status, error, status, task_id),
        )


@app.task(name="agora.run_pipeline", bind=True)
def run_pipeline(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Прогон исследования.

    `payload` — параметры запуска из #11: task_id, tenant_id, mode, video_ref,
    persona_ids, survey, replication_count, prompts_snapshot.

    Повторный вызов с тем же task_id НЕ начинает заново: граф поднимает
    чекпоинт по thread_id и продолжает с места отказа. Ради этого в
    `graph.invoke` передаётся None вместо состояния, когда чекпоинт уже есть, —
    иначе начальное состояние затёрло бы накопленное.
    """
    from .checkpoint import ValkeyCheckpointSaver
    from .graph import build_graph
    from .progress import ProgressWriter
    from .state import new_state

    task_id = str(payload["task_id"])
    tenant_id = str(payload["tenant_id"])

    valkey = _valkey()
    progress = ProgressWriter(valkey, task_id)
    checkpointer = ValkeyCheckpointSaver(valkey)
    graph = build_graph(checkpointer=checkpointer, progress=progress)
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
    )

    _set_task_status(task_id, tenant_id, STATUS_RUNNING)
    progress.emit("pipeline", STATUS_RUNNING, detail="возобновление" if resuming else "запуск")

    try:
        final = graph.invoke(initial, config)
    except Exception as e:  # noqa: BLE001 — статус и причина обязаны дойти до пользователя
        reason = f"{type(e).__name__}: {e}"
        _set_task_status(task_id, tenant_id, STATUS_FAILED, reason)
        # Узел уже записал свой FAILED с точным местом; здесь фиксируется итог
        # прогона, чтобы экран не остался на RUNNING после смерти воркера.
        progress.fail("pipeline", reason)
        raise

    _set_task_status(task_id, tenant_id, STATUS_REPORT_READY)
    progress.emit("pipeline", STATUS_REPORT_READY, degraded=final.get("degraded") or [])
    return {
        "task_id": task_id,
        "status": STATUS_REPORT_READY,
        "degraded": final.get("degraded") or [],
    }
