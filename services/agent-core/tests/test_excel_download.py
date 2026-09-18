"""
Книга Excel доезжает до кнопки, а не остаётся вызовом из тестов.

─── Почему этот тест существует ─────────────────────────────────────────────
`analytics/excel_export.py` был написан целиком и покрыт `test_excel_export.py`,
но единственным, кто его звал, был сам этот тест. Проверка формы книги при этом
была зелёной: она собирала книгу в памяти и читала ячейки. Дефект «выгрузку
нельзя скачать» такой проверкой не ловится вовсе — она проверяет сборщик, а не
шов между сборщиком и интерфейсом.

Отсюда два уровня:

* **статический** — сборщик зовёт продуктовый код, а не только тесты; маршрут
  объявлен в приложении; чтения идут под арендатором;
* **поведенческий** — `render_workbook` отдаёт БАЙТЫ, которые открываются как
  xlsx и содержат оба листа с ожидаемой шапкой. Проверять «позвали openpyxl»
  бессмысленно: расходится не вызов, а файл.

Живой базы тут нет намеренно. Сборка книги (`analytics/excel_download.py`)
отделена от чтения (`api/routers/export.py`) именно затем, чтобы поведенческий
уровень шёл где угодно, а не уходил в SKIP на каждой машине без Mongo и без
FastAPI: маршрут проверяется чтением исходника, как в `test_chat_wiring.py`.
"""
from __future__ import annotations

import io
import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
CORE = REPO / "services" / "agent-core" / "agent_core"
SURVEY = json.loads((REPO / "data" / "survey" / "customer_2026.json").read_text("utf-8"))

pytest.importorskip(
    "openpyxl", reason="openpyxl объявлена в зависимостях воркера; без неё выгрузку не собрать"
)


# ─── Статический уровень ─────────────────────────────────────────────────────


def test_сборщик_книги_зовут_не_только_тесты() -> None:
    """
    Импорт `excel_export` есть в продуктовом коде воркера.

    Это и был исходный дефект: модуль существовал, тесты его звали, продукт —
    нет. Ищется именно СТРОКА ИМПОРТА, а не вхождение имени: упоминание в
    комментарии уже есть в `qa/checks.py`, и проверка «имя встречается» была бы
    зелёной при ровно том дефекте, ради которого написана.
    """
    callers = [
        path.relative_to(CORE).as_posix()
        for path in CORE.rglob("*.py")
        if path.name != "excel_export.py"
        and any(
            "excel_export" in line and line.lstrip().startswith(("import ", "from "))
            for line in path.read_text("utf-8").splitlines()
        )
    ]
    assert callers, (
        "ни один модуль agent_core не импортирует excel_export: книга собирается "
        "только в тестах, и скачать её неоткуда"
    )


def test_маршрут_выгрузки_объявлен_в_приложении() -> None:
    router = CORE / "api" / "routers" / "export.py"
    assert router.exists(), "нет agent_core/api/routers/export.py — выгрузку некому отдать"

    app_init = (CORE / "api" / "__init__.py").read_text("utf-8")
    assert "export" in app_init, (
        "роутер выгрузки не подключён в agent_core/api/__init__.py: маршрут есть "
        "в файле и отсутствует в приложении — отличить это можно только запросом"
    )


def test_чтения_выгрузки_идут_под_арендатором() -> None:
    """
    Mongo без RLS: фильтр обязан пройти `assert_tenant_filter`, Postgres —
    `tenant_scope`. Забытый фильтр здесь означает чужие ответы в чужом файле.
    """
    source = (CORE / "api" / "routers" / "export.py").read_text("utf-8")
    assert "assert_tenant_filter" in source, (
        "чтение report_personas без assert_tenant_filter: в Mongo нет RLS"
    )
    assert "tenant_scope" in source, (
        "чтение анкеты и персон из Postgres без tenant_scope: запрос пойдёт от "
        "владельца, а не от арендатора"
    )


# ─── Поведенческий уровень ───────────────────────────────────────────────────


def persona(pid: str, city: str, age: int) -> dict:
    return {
        "id": pid,
        "name": f"Персона {pid}",
        "dna": {
            "demographics": {
                "age": age, "gender": "жен", "city": city,
                "geo": "центры субъектов", "children": "Нет детей",
            }
        },
    }


def card(pid: str, answers: dict, replication: int = 0) -> dict:
    """Карточка в том виде, в каком её кладёт `analytics/store.save_report`."""
    return {
        "persona_id": pid,
        "replication": replication,
        "persona_name": f"Персона {pid}",
        "answer": {"survey_answers": answers},
        "qa_flags": [],
    }


def test_render_workbook_отдаёт_открываемый_xlsx() -> None:
    from openpyxl import load_workbook

    from agent_core.analytics.excel_download import render_workbook

    first = SURVEY["questions"][0]["id"]
    blob = render_workbook(
        survey=SURVEY,
        cards=[card("p1", {first: 7}), card("p2", {first: 9})],
        personas=[persona("p1", "Москва", 34), persona("p2", "Казань", 51)],
        meta={"run_id": "run-1", "exported_at": "2026-09-18"},
    )

    assert isinstance(blob, bytes) and blob[:2] == b"PK", (
        "выгрузка обязана быть готовыми байтами xlsx: объект книги нельзя ни "
        "отдать потоком, ни положить в ответ"
    )

    wb = load_workbook(io.BytesIO(blob))
    assert wb.sheetnames == ["Ответы", "О прогоне"]

    ws = wb["Ответы"]
    assert ws.cell(row=2, column=1).value == "Населенный пункт"
    assert ws.cell(row=3, column=1).value == "Москва"
    assert ws.cell(row=4, column=1).value == "Казань"
    # Шапка блока — подпись, а не идентификатор: заказчик читает верхнюю строку
    # глазами, и «b1» вместо «Оценки проекта» делает две выгрузки несравнимыми.
    assert ws.cell(row=1, column=len(_audience()) + 1).value == "Оценки проекта"


def test_флаги_qa_доезжают_из_карточек() -> None:
    """
    Выбывший по правилам ответ не попадает в книгу и назван на листе «О прогоне».

    Флаги лежат в карточках (`store.save_report`), а не отдельным списком, —
    значит собрать их обратно обязан сам маршрут. Не собрал бы — таблица
    посчиталась бы по другой выборке, чем отчёт, и разошлись бы они молча.
    """
    from openpyxl import load_workbook

    from agent_core.analytics.excel_download import render_workbook

    first = SURVEY["questions"][0]["id"]
    bad = card("p2", {first: 9})
    bad["qa_flags"] = [
        {"persona_id": "p2", "replication": 0, "verdict": "regenerate", "source": "rule"}
    ]

    wb = load_workbook(io.BytesIO(render_workbook(
        survey=SURVEY,
        cards=[card("p1", {first: 7}), bad],
        personas=[persona("p1", "Москва", 34), persona("p2", "Казань", 51)],
        meta={},
    )))
    about = {
        wb["О прогоне"].cell(row=r, column=1).value: wb["О прогоне"].cell(row=r, column=2).value
        for r in range(1, wb["О прогоне"].max_row + 1)
    }
    assert about["Выбыло по правилам QA"] == 1


def _audience() -> tuple:
    from agent_core.analytics.excel_export import AUDIENCE_COLUMNS

    return AUDIENCE_COLUMNS
