"""
POST /api/export/excel — выгрузка ответов прогона книгой Excel.

─── Почему собирает воркер, а не веб ────────────────────────────────────────
§6 запрещает нативные npm-модули в `apps/web`, и сборка xlsx на Node — ровно
тот случай: либо нативный пакет, либо тяжёлый чистый JS в бандле. В образе
воркера `openpyxl` уже стоит, форма книги описана и покрыта тестами
(`analytics/excel_export.py`), и вторая её реализация на TypeScript разошлась
бы с первой — этот класс дефекта в проекте повторялся трижды.

─── Почему потоком, а не ссылкой в хранилище ────────────────────────────────
Второй разумный путь — задача Celery, кладущая книгу в S3, и подписанная
ссылка в меню. Он дороже ровно на то, чего здесь нет: отдельный жизненный цикл
объекта (кто и когда его удалит), состояние «книга готовится» в интерфейсе и
вопрос, что показывать, пока она не готова.

Книга на пятистах персонах — сотни килобайт и доли секунды сборки; это
запрос-ответ, а не фоновая работа. И собирается она из УЖЕ сохранённых
артефактов, то есть воспроизводима в любой момент: хранить результат незачем,
а хранимая копия разошлась бы с отчётом при первом же пересчёте.

Маршрут повторяет модель доверия чата (#28): служба наружу не опубликована,
доступ проверяет веб, сюда приезжает уже проверенный `tenant_id`. Данные при
этом читаются под арендатором — с подделанным `task_id` чужой прогон не
отдастся.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ...analytics.excel_download import XLSX_MEDIA_TYPE, render_workbook

router = APIRouter(prefix="/api/export", tags=["export"])


class ExcelRequest(BaseModel):
    """Тело запроса. Доступ уже проверен вебом — здесь только адрес прогона."""

    tenant_id: str
    task_id: str


def _cards(tenant_id: str, task_id: str) -> list[dict[str, Any]]:
    """
    Карточки ответов прогона. Порядок устойчивый — иначе строки книги ездят.

    Две выгрузки одного прогона обязаны совпадать построчно: заказчик кладёт
    их рядом и сравнивает колонка в колонку. Без сортировки Mongo не обещает
    одного порядка между запросами, и расхождение выглядело бы как другие
    данные, а не как другой порядок.
    """
    from ...analytics.store import REPORT_PERSONAS
    from ...db import assert_tenant_filter
    from ...mongo import mongo_db

    scope = assert_tenant_filter({"tenant_id": tenant_id, "task_id": task_id})
    cursor = mongo_db()[REPORT_PERSONAS].find(scope, {"_id": 0}).sort(
        [("persona_id", 1), ("replication", 1)]
    )
    return list(cursor)


def _survey_and_personas(
    tenant_id: str, task_id: str, persona_ids: list[str]
) -> tuple[Any, list[dict[str, Any]]]:
    """
    Анкета прогона и персоны аудитории из Postgres — под арендатором.

    Анкета берётся по `tasks.survey_id`, а не из отчёта: в отчёте лежит СВОДКА
    ответов (`survey_tally`), в которой нет ни типов вопросов, ни вариантов, ни
    числа разрешённых ответов. Развернуть анкету в колонки по сводке нечем.

    Отсутствие DSN — не отказ: прогон без анкеты законен (пять базовых
    критериев), и книга тогда соберётся из одних параметров аудитории.
    """
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return None, []

    import psycopg

    from ...db import tenant_scope

    with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
        cur.execute(
            "SELECT s.questions FROM tasks t "
            "LEFT JOIN surveys s ON s.id = t.survey_id WHERE t.id = %s::uuid",
            (task_id,),
        )
        row = cur.fetchone()
        survey = row[0] if row else None

        personas: list[dict[str, Any]] = []
        if persona_ids:
            # Идентификаторы приехали из карточек, а не от вызывающего, и всё
            # равно читаются под арендатором: политика — единственное, что
            # держит изоляцию, когда идентификатор откуда-то угадан.
            cur.execute(
                "SELECT id::text, name, dna FROM personas WHERE id = ANY(%s::uuid[])",
                (list(persona_ids),),
            )
            personas = [{"id": r[0], "name": r[1], "dna": r[2] or {}} for r in cur.fetchall()]

    return survey, personas


def _meta(tenant_id: str, task_id: str) -> dict[str, Any]:
    """
    Лист «О прогоне». Отказ чтения отчёта не отменяет выгрузку.

    Числа выборки книга считает сама по карточкам; из отчёта приезжают только
    подписи — какими моделями считано и сколько ответов сняла проверка. Ронять
    из-за них готовую таблицу незачем, но и молчать нельзя: прочерк в ячейке
    виден, а придуманное значение — нет.
    """
    meta: dict[str, Any] = {
        "run_id": task_id,
        "exported_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    }
    try:
        from ...analytics.store import REPORTS
        from ...db import assert_tenant_filter
        from ...mongo import mongo_db

        scope = assert_tenant_filter({"tenant_id": tenant_id, "task_id": task_id})
        report = (mongo_db()[REPORTS].find_one(scope) or {}).get("report") or {}
    except Exception:  # noqa: BLE001
        return meta

    models = report.get("models_used")
    if isinstance(models, dict) and models:
        meta["models"] = ", ".join(f"{role}: {name}" for role, name in sorted(models.items()))
    if report.get("excluded_by_qa") is not None:
        meta["excluded_by_qa"] = report["excluded_by_qa"]
    return meta


@router.post("/excel")
def excel(req: ExcelRequest) -> Response:
    """Книга Excel по сохранённым артефактам прогона."""
    try:
        cards = _cards(req.tenant_id, req.task_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"артефакты прогона недоступны: {exc}") from exc

    if not cards:
        # 404, а не пустая книга: файл с одной шапкой выглядит как прогон, в
        # котором никто не ответил, и отправляет искать причину в анкете.
        raise HTTPException(
            404,
            "у прогона нет сохранённых ответов: он не завершён, отчёт не записан "
            "или прогон принадлежит другому арендатору",
        )

    persona_ids = sorted({str(c.get("persona_id")) for c in cards if c.get("persona_id")})
    try:
        survey, personas = _survey_and_personas(req.tenant_id, req.task_id, persona_ids)
    except Exception as exc:  # noqa: BLE001
        # Без реестра персон книга собирается, но параметры аудитории в ней
        # останутся пустыми — молчать об этом нельзя.
        raise HTTPException(503, f"анкета и персоны не прочитаны: {exc}") from exc

    blob = render_workbook(
        survey=survey,
        cards=cards,
        personas=personas,
        meta=_meta(req.tenant_id, req.task_id),
    )
    # Имя файла ставит веб: он знает, под каким именем его ждёт оператор, и
    # ставит тот же заголовок расшифровке и отчёту. Два места, назначающих имя,
    # разошлись бы при первой правке.
    return Response(content=blob, media_type=XLSX_MEDIA_TYPE)
