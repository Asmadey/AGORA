"""
Перенос заставок: ключ первого кадра из пакета в `tasks.poster_ref`.

─── Зачем ────────────────────────────────────────────────────────────────────
В списке исследований у всех прогонов стояла серая заглушка. Проверка на боевой
базе 19.08.2026: `poster_ref` пуст У ВСЕХ, при этом все 40 пакетов в Mongo ключи
кадров содержат. Код `_save_poster` пришёл коммитом от 18.08, а ни один прогон
после него до конца не дошёл — писать было некому.

`tasks.poster_ref` и первая ячейка таймлайна — буквально один и тот же ключ S3,
записанный на одном шаге `_publish_frames`. Поэтому это не новая работа, а
сопряжение: кадр уже выгружен, ключ уже сохранён, просто не в ту колонку.

─── Почему перенос, а не чтение Mongo при показе ─────────────────────────────
Список отдаёт до ста строк; запрос за пакетом на каждую — сто обращений к Mongo
ради картинки в углу. Ровно ради этого колонка и заводилась.

─── Запуск ───────────────────────────────────────────────────────────────────
    python3 -m agent_core.maintenance.backfill_posters --dry-run
    python3 -m agent_core.maintenance.backfill_posters

Идемпотентно: заполненные поля не трогаются, повторный запуск ничего не делает.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any


def poster_of(pack_doc: Any) -> str | None:
    """
    Ключ первого кадра пакета.

    Первый КАДР, а не первая сцена: сцена без кадра — законное состояние,
    разбор мог не дать панели. Битые записи пропускаются молча: перенос читает
    то, что воркер писал много раньше, и уронить его на одной записи значит не
    перенести и все остальные.
    """
    if not isinstance(pack_doc, dict):
        return None
    pack = pack_doc.get("pack")
    scenes = pack.get("scenes") if isinstance(pack, dict) else None
    if not isinstance(scenes, list):
        return None
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        key = scene.get("screenshot")
        if isinstance(key, str) and key.strip():
            return key
    return None


def plan_backfill(
    tasks: dict[str, str | None],
    packs: dict[str, Any],
) -> dict[str, str]:
    """
    Что именно записать: `{task_id: ключ}`.

    Отдельно от записи намеренно — план можно показать и проверить глазами до
    того, как он что-то изменит. Заполненное поле не трогается: у прогона мог
    быть свой кадр, а перенос обязан быть безопасным при повторе.
    """
    out: dict[str, str] = {}
    for task_id, existing in tasks.items():
        if existing:
            continue
        key = poster_of(packs.get(task_id))
        if key:
            out[task_id] = key
    return out


def _load(only_tenant: str | None) -> tuple[dict[str, str | None], dict[str, Any], dict[str, str]]:
    """
    Задачи, пакеты и владельцы задач.

    ─── Почему список арендаторов берётся из Mongo ───────────────────────────
    Первая редакция читала `SELECT … FROM tasks` без тенант-контекста, чтобы
    пройти по всем командам разом, и получила `permission denied for table
    tasks`. Это не помеха, а работающая защита: `agora_login` объявлен
    NOINHERIT ровно затем, чтобы забытый `SET LOCAL ROLE agora_app` падал с
    внятной ошибкой, а не тихо работал (CLAUDE.md §5).

    Поэтому арендаторы берутся оттуда, где они лежат без RLS, — из пакетов
    Mongo, — а каждое обращение к Postgres идёт под своим `tenant_scope`. Это и
    честнее: перенос трогает ровно те команды, у которых есть что переносить.
    """
    from ..mongo import mongo_db

    db = mongo_db()
    packs: dict[str, Any] = {}
    owners: dict[str, str] = {}
    for doc in db.content_packs.find(
        {}, {"task_id": 1, "tenant_id": 1, "pack.scenes.screenshot": 1}
    ):
        task_id = str(doc.get("task_id") or "")
        tenant = str(doc.get("tenant_id") or "")
        if not task_id or not tenant:
            continue
        if only_tenant and tenant != only_tenant:
            continue
        packs[task_id] = doc
        owners[task_id] = tenant

    tasks: dict[str, str | None] = {}
    if owners:
        import psycopg

        from ..db import tenant_scope

        by_tenant: dict[str, list[str]] = {}
        for task_id, tenant in owners.items():
            by_tenant.setdefault(tenant, []).append(task_id)

        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            for tenant, ids in by_tenant.items():
                with tenant_scope(conn, tenant) as cur:
                    cur.execute(
                        "SELECT id::text, poster_ref FROM tasks WHERE id = ANY(%s::uuid[])",
                        (ids,),
                    )
                    for task_id, poster in cur.fetchall():
                        tasks[task_id] = poster

    return tasks, packs, owners


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="показать план и выйти")
    parser.add_argument("--tenant", default=None, help="ограничить одним арендатором")
    args = parser.parse_args(argv)

    tasks, packs, owners = _load(args.tenant)
    plan = plan_backfill(tasks, packs)

    print(f"задач: {len(tasks)}, пакетов: {len(packs)}, к переносу: {len(plan)}")
    for task_id, key in sorted(plan.items()):
        print(f"  {task_id} → {key}")

    if args.dry_run or not plan:
        return 0

    import psycopg

    from ..db import tenant_scope

    written = 0
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for task_id, key in plan.items():
            with tenant_scope(conn, owners[task_id]) as cur:
                cur.execute(
                    "UPDATE tasks SET poster_ref = %s WHERE id = %s::uuid AND poster_ref IS NULL",
                    (key, task_id),
                )
                written += cur.rowcount or 0
        conn.commit()

    print(f"записано: {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
