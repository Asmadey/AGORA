"""
Сборщик осиротевших прогонов.

─── Что чинится ─────────────────────────────────────────────────────────────
Статус прогона ставит сам конвейер: `_set_task_status` в `pipeline/tasks.py`,
из блока `except`. Питоновское исключение туда доходит, а SIGKILL — нет:
процесс исчезает, и выполнить обновление некому.

28.08.2026 четыре конвейера пошли разом, воркера убило по памяти
(`WorkerLostError: signal 9`), и три строки `tasks` остались RUNNING навсегда.
Навсегда буквально: Celery считает задачу потерянной, веб только читает,
следующий прогон о чужих строках не знает.

Пользователю это видно так: экран показывает «идёт», `DELETE` отвечает 202
«отмена запрошена» и не удаляет — удалить можно только остановленный. Прогон
нельзя ни доиграть, ни убрать.

─── Два признака, а не один ─────────────────────────────────────────────────
**Жёсткий потолок.** Celery убивает задачу на `task_time_limit`. Прогон старше
этого потолка не идёт ни при каких обстоятельствах — что бы ни лежало в снимке
прогресса. Признак надёжный, но медленный: ждать три с половиной часа.

**Молчание.** Каждый узел пишет событие в снимок прогресса. Отсутствие событий
дольше отсрочки означает, что писать их некому. Признак быстрый, но требует
запаса: распознавание речи и разбор кадров молчат подолгу.

Порознь каждый неполон, вместе — покрывают и быструю смерть, и зависание.

─── Чего сборщик не делает ──────────────────────────────────────────────────
Не перезапускает. Прогон, чей воркер убит по памяти, при перезапуске будет убит
снова — и так до исчерпания бюджета, потому что каждый круг выглядит осмысленной
работой. Решение о повторе принимает человек, увидев причину.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Any

#: Потолок задачи Celery — тот же, что в `celery_app.TIME_LIMIT_SEC`.
#:
#: Читается из окружения напрямую, а не импортом: сборщик — арифметика над
#: тремя числами, и тянуть ради неё брокерную библиотеку значит сделать
#: проверяемое непроверяемым там, где celery не установлен. Совпадение
#: значений держит `test_reaper.py::test_потолок_согласован_с_celery`.
TIME_LIMIT_SEC = int(os.environ.get("TASK_TIME_LIMIT", 3 * 60 * 60))

#: Насколько сборщик отстаёт от потолка Celery.
#:
#: Не ноль: между «Celery снял задачу» и «строка обновилась» есть промежуток, и
#: сборщик, срабатывающий ровно на потолке, объявил бы осиротевшим прогон,
#: который в этот момент штатно записывает свой отказ.
HARD_LIMIT_MARGIN_SEC = 30 * 60

#: Жёсткий потолок: старше — точно не идёт.
HARD_LIMIT_SEC = TIME_LIMIT_SEC + HARD_LIMIT_MARGIN_SEC

#: Сколько прогон вправе молчать между событиями.
#:
#: Считается по самому долгому узлу. На боевом материале это распознавание речи
#: и разбор кадров: полный фильм — около 150 секунд у GigaAM и до десятков минут
#: у зрения на длинном режиме. Сорок пять минут — запас втрое к худшему
#: замеренному, и он намеренно щедрый: ошибка в эту сторону стоит ожидания,
#: ошибка в обратную — убитого живого прогона.
HEARTBEAT_GRACE_SEC = 45 * 60


@dataclass(frozen=True)
class OrphanVerdict:
    """Осиротел ли прогон и почему. Причина уезжает в `tasks.error`."""

    orphaned: bool
    reason: str


def _minutes(seconds: float) -> int:
    return int(seconds // 60)


def is_orphan(
    *,
    status: str,
    started_at: float | None,
    last_event_at: float | None,
    now: float,
) -> OrphanVerdict:
    """
    Осиротел ли прогон.

    `last_event_at` — время последнего события в снимке прогресса, `None`, если
    снимка нет вовсе. `started_at` — момент перехода в RUNNING.

    Разбирается ТОЛЬКО статус RUNNING. QUEUED ждёт свободного воркера, и это
    ожидание ничем не ограничено: очередь может стоять сутки, если идёт длинный
    прогон. Объявить осиротевшим ждущего значит терять поставленную работу.
    """
    if status != "RUNNING":
        return OrphanVerdict(False, "")

    if started_at is None:
        # RUNNING без `started_at` — рассогласование, которого быть не должно:
        # оба поля пишет один UPDATE. Разбирать его догадкой опаснее, чем
        # оставить человеку.
        return OrphanVerdict(False, "")

    age = now - started_at

    if age > HARD_LIMIT_SEC:
        return OrphanVerdict(
            True,
            f"Прогон идёт {_minutes(age)} мин — дольше жёсткого потолка задачи "
            f"({_minutes(HARD_LIMIT_SEC)} мин). Celery снимает задачу на "
            f"{_minutes(TIME_LIMIT_SEC)} мин, значит выполнять её уже некому: "
            f"воркер убит извне (обычно по нехватке памяти) и статус обновить "
            f"не успел.",
        )

    # Отсутствие снимка считается молчанием от старта: снимок живёт сутки, и
    # его отсутствие у идущего прогона означает, что событий не было вовсе.
    silence = age if last_event_at is None else now - last_event_at

    if silence > HEARTBEAT_GRACE_SEC:
        what = "снимок прогресса не создан" if last_event_at is None else "последнее событие"
        return OrphanVerdict(
            True,
            f"Прогон не подавал признаков жизни {_minutes(silence)} мин "
            f"({what}), при отсрочке {_minutes(HEARTBEAT_GRACE_SEC)} мин. "
            f"Узлы пишут событие на входе и выходе, значит писать их некому: "
            f"воркер убит извне и статус обновить не успел.",
        )

    return OrphanVerdict(False, "")


# ─── Обход базы ──────────────────────────────────────────────────────────────
#
# Сканирование идёт ПО АРЕНДАТОРАМ, а не одним запросом по всей таблице.
#
# Причина в RLS: на `tasks` включён FORCE, и политика `tasks_tenant_isolation`
# выдана роли `agora_app` с фильтром по `app.current_tenant()`. Владелец схемы
# политики на `tasks` не имеет вовсе, а «нет политики» при FORCE значит
# «запретить» — запрос владельца вернул бы ноль строк и выглядел бы как «сирот
# нет». Заводить владельцу сквозную политику ради уборки значит открыть все
# прогоны всех арендаторов навсегда, чтобы раз в час прочитать три строки.
#
# Поэтому перечень арендаторов читается из `teams` (владельцу это разрешено
# миграцией 06), а сами прогоны — под `tenant_scope`, тем же путём, что ходит
# конвейер.


def _snapshot_last_event(client: Any, task_id: str) -> float | None:
    """Время последнего события прогона из снимка в Valkey. `None` — снимка нет."""
    from ..pipeline.progress import progress_key

    try:
        raw = client.get(progress_key(task_id))
    except Exception:  # noqa: BLE001 — недоступный Valkey не должен ронять уборку
        return None
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        at = json.loads(raw).get("at")
    except (json.JSONDecodeError, AttributeError):
        return None
    return float(at) if isinstance(at, (int, float)) else None


def sweep(*, apply: bool = False) -> list[dict[str, Any]]:
    """
    Находит осиротевшие прогоны и — при `apply` — переводит их в FAILED.

    Возвращает список найденного, чтобы вызывающий мог его напечатать или
    посчитать. Пустой список означает «сирот нет», и это нормальный исход.

    Отказ на одном арендаторе не прекращает обход: у остальных прогоны тоже
    зависли, и уборка, падающая на первом же неудобном случае, не уберёт
    ничего.
    """
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL не задан — сборщику нечего обходить")

    import psycopg

    from ..db import tenant_scope

    try:
        from ..pipeline.tasks import _valkey

        valkey = _valkey()
    except Exception:  # noqa: BLE001
        # Без Valkey остаётся жёсткий потолок: он медленнее, но работает.
        valkey = None

    now = time.time()
    found: list[dict[str, Any]] = []

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM teams")
            tenants = [str(row[0]) for row in cur.fetchall()]

        for tenant_id in tenants:
            try:
                with tenant_scope(conn, tenant_id) as cur:
                    # `started_at` берётся как есть и переводится в секунды
                    # питоном. EXTRACT(EPOCH FROM …) здесь был бы короче, но
                    # `test_schema_contract` разбирает SQL наивно и читает
                    # `FROM started_at` как обращение к таблице. Спорить с
                    # проверкой ради одной функции дороже, чем обойтись без неё.
                    cur.execute(
                        "SELECT id, seq_no, started_at FROM tasks WHERE status = 'RUNNING'"
                    )
                    rows = cur.fetchall()
            except Exception as exc:  # noqa: BLE001
                found.append({"tenant_id": tenant_id, "error": f"{type(exc).__name__}: {exc}"})
                continue

            for task_id, seq_no, started in rows:
                verdict = is_orphan(
                    status="RUNNING",
                    started_at=started.timestamp() if started is not None else None,
                    last_event_at=_snapshot_last_event(valkey, str(task_id)) if valkey else None,
                    now=now,
                )
                if not verdict.orphaned:
                    continue

                found.append({
                    "task_id": str(task_id),
                    "seq_no": seq_no,
                    "tenant_id": tenant_id,
                    "reason": verdict.reason,
                })
                if apply:
                    with tenant_scope(conn, tenant_id) as cur:
                        cur.execute(
                            "UPDATE tasks SET status = 'FAILED', error = %s, "
                            "finished_at = now() "
                            " WHERE id = %s::uuid AND status = 'RUNNING'",
                            (verdict.reason, str(task_id)),
                        )
        if apply:
            conn.commit()

    return found


def main() -> int:
    """CLI: `python3 -m agent_core.maintenance.reaper --dry-run|--apply`."""
    parser = argparse.ArgumentParser(description="Сборщик осиротевших прогонов")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="только показать")
    group.add_argument("--apply", action="store_true", help="перевести в FAILED")
    args = parser.parse_args()

    found = sweep(apply=args.apply)
    problems = [f for f in found if "error" in f]
    orphans = [f for f in found if "error" not in f]

    for p in problems:
        print(f"  ОШИБКА обхода арендатора {p['tenant_id'][:8]}: {p['error']}")
    for o in orphans:
        num = f"№{o['seq_no']:04d}" if o.get("seq_no") is not None else o["task_id"][:8]
        print(f"  {num}: {o['reason']}")

    if not orphans:
        print("Осиротевших прогонов нет.")
    else:
        print(
            f"\nНайдено: {len(orphans)}. "
            + ("Переведены в FAILED." if args.apply else "Ничего не изменено (--dry-run).")
        )
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
