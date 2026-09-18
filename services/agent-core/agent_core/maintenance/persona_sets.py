"""Чистая арифметика для реапера зависших наборов персон.

Решение «набор жив?» намеренно не знает о Postgres. Время и поддельные строки
достаточны, поэтому порог проверяется обычным unit-тестом, а Celery-обвязка
занимается только чтением и записью.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

STALE_AFTER = timedelta(minutes=5)


def _utc(value: datetime) -> datetime:
    """Привести naive timestamp из старого драйвера к UTC без двусмысленности."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def stale_reason(*, progress_at: datetime, generated_count: int, now: datetime) -> str:
    age = max(timedelta(0), _utc(now) - _utc(progress_at))
    minutes = int(age.total_seconds() // 60)
    return (
        f"Генерация набора не двигалась {minutes} мин, что дольше порога 5 мин; "
        f"записано {generated_count} персон. Набор переведён в failed."
    )


def reap_stale(
    rows: Iterable[dict[str, Any]],
    *,
    now: datetime,
    stale_after: timedelta = STALE_AFTER,
) -> list[dict[str, Any]]:
    """Вернуть только просроченные `generating` строки с готовой причиной."""
    current = _utc(now)
    found: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "generating":
            continue
        progress_at = row.get("progress_at")
        if not isinstance(progress_at, datetime):
            continue
        age = current - _utc(progress_at)
        if age <= stale_after:
            continue
        found.append(
            {
                "id": str(row["id"]),
                "generated_count": int(row.get("generated_count") or 0),
                "progress_at": progress_at,
                "reason": stale_reason(
                    progress_at=progress_at,
                    generated_count=int(row.get("generated_count") or 0),
                    now=current,
                ),
            }
        )
    return found
