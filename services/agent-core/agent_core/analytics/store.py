"""
Сохранение отчёта туда, откуда его прочитает веб — задача #21.

До этой задачи отчёт из процесса воркера не выходил: узел клал его в состояние
графа и писал `report.json` в локальный каталог, а Celery возвращал наружу
только статус. Экран `/runs/[id]` при этом выглядел готовым — он рендерился из
`lib/mock-data`. Дефект такого рода не виден на скриншоте: экран с моком и экран
с данными отличаются только тем, откуда взялись цифры.

─── Почему две коллекции, а не одна ──────────────────────────────────────────
Замерено на синтетическом наборе:

    100 персон × 1 повтор:  агрегат   1.2 КБ | с карточками персон  132 КБ
    500 персон × 1 повтор:  агрегат   1.2 КБ | с карточками персон  654 КБ
    500 персон × 3 повтора: агрегат 178.5 КБ | с карточками персон  2.1 МБ

Одним документом 2.1 МБ в Mongo поместились бы — лимит 16 МБ. Но тогда первый
экран тянул бы два мегабайта ради пяти чисел в шапке, а запас до лимита съедался
бы ростом аудитории и длиной вербатимов. Поэтому отчёт (сотни килобайт) читается
целиком, а карточки персон лежат отдельными документами и подтягиваются
постранично.

Postgres здесь не годится по другой причине: колонку с отчётом пришлось бы
завести в `tasks`, а эту таблицу сканирует список прогонов.

─── Изоляция арендаторов ─────────────────────────────────────────────────────
В Mongo нет RLS. Забыть фильтр в Postgres безопасно — поймает политика; забыть
его здесь значит отдать чужие данные. Поэтому каждый фильтр проходит через
`db.assert_tenant_filter`, и обойти его можно только сознательно.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..db import assert_tenant_filter

#: Имена коллекций. Константы, а не строки по месту: имя, набранное руками в
#: воркере и в вебе по отдельности, расходится при первой опечатке, и
#: расхождение выглядит как «отчёта нет», а не как «читаем не оттуда».
REPORTS = "reports"
REPORT_PERSONAS = "report_personas"


def save_report(
    db: Any,
    *,
    tenant_id: str,
    task_id: str,
    report: dict[str, Any],
    answers: list[dict[str, Any]],
    qa_flags: list[dict[str, Any]] | None = None,
) -> int:
    """
    Кладёт отчёт и карточки персон. Возвращает число сохранённых карточек.

    Идемпотентно: upsert по (tenant_id, task_id[, persona_id, replication]).
    Повторный прогон того же task_id — это дозапись поверх, а не второй отчёт;
    иначе перезапуск после сбоя оставлял бы в базе два отчёта на один прогон, и
    какой из них покажет экран, зависело бы от порядка выборки.
    """
    now = datetime.now(UTC)
    flags_by_answer = _flags_by_answer(qa_flags)

    db[REPORTS].update_one(
        assert_tenant_filter({"tenant_id": tenant_id, "task_id": task_id}),
        {"$set": {
            "report": report,
            "audience_size": len(answers),
            "updated_at": now,
        }},
        upsert=True,
    )

    for item in answers:
        persona_id = str(item.get("persona_id"))
        replication = int(item.get("replication") or 0)
        db[REPORT_PERSONAS].update_one(
            assert_tenant_filter({
                "tenant_id": tenant_id,
                "task_id": task_id,
                "persona_id": persona_id,
                "replication": replication,
            }),
            {"$set": {
                "persona_name": item.get("persona_name"),
                # Срез DNA лежит в карточке, а не берётся из персоны при чтении.
                # Персону могли отредактировать или удалить после прогона, а
                # отчёт обязан показывать ту аудиторию, на которой посчитан.
                "segment": item.get("segment") or {},
                "answer": item.get("answer") if isinstance(item.get("answer"), dict) else item,
                # Флаги кладутся рядом с карточкой, а не выводятся на экране из
                # общего списка: аккордеон грузится постранично, и искать флаги
                # персоны в списке, которого на странице нет, было бы нечем.
                "qa_flags": flags_by_answer.get((persona_id, replication), []),
                "updated_at": now,
            }},
            upsert=True,
        )
    return len(answers)


def _flags_by_answer(
    qa_flags: list[dict[str, Any]] | None,
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    out: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for flag in qa_flags or []:
        if not isinstance(flag, dict) or flag.get("persona_id") is None:
            # Вердикт по выборке целиком (diversity) не адресует карточку.
            continue
        key = (str(flag.get("persona_id")), int(flag.get("replication") or 0))
        out.setdefault(key, []).append(flag)
    return out
