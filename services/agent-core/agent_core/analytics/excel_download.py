"""
Сборка книги Excel из сохранённых артефактов прогона — байтами, а не объектом.

─── Зачем отдельный модуль рядом с `excel_export` ───────────────────────────
`excel_export.build_workbook` собирает КНИГУ: форму, шапку, ячейки. Он ничего
не знает ни о Mongo, ни о том, в каком виде карточки ответов лежат в базе, — и
знать не должен, иначе проверять его форму пришлось бы с живой базой.

Здесь лежит вторая половина: перевод сохранённых карточек (`analytics/store.py`)
в то, чего ждёт сборщик, и сериализация книги в байты. Байты, а не объект
`Workbook`, потому что объект нельзя ни отдать потоком, ни положить в ответ —
и ровно на этом шве выгрузка год простояла без кнопки.

Модуль намеренно не импортирует FastAPI. Маршрут (`api/routers/export.py`) —
это чтение и HTTP; сборка обязана проверяться там, где ни базы, ни веб-сервера
нет, иначе поведенческий уровень уйдёт в SKIP на каждой машине разработчика.
"""

from __future__ import annotations

import io
from typing import Any

from ..paths import find_data_file
from .excel_export import block_labels, build_workbook

#: Анкета заказчика в репозитории. Из неё берутся подписи блоков и версия.
#:
#: В базе (`surveys.questions`) лежит ТОЛЬКО список вопросов — блоки веб хранит
#: у себя (`lib/customer-survey.ts`, `CUSTOMER_BLOCKS`). Без этого файла верхняя
#: строка шапки заполнилась бы идентификаторами `b1`…`b6`: книга осталась бы
#: верной, но перестала бы читаться глазами, а ради этого форма и повторяется.
CUSTOMER_SURVEY = "survey/customer_2026.json"

#: MIME-тип xlsx. Тот же, что у веба (`lib/excel-download.ts`): разойдясь, они
#: дали бы книгу, которую браузер показывает текстом вместо сохранения.
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _customer_file() -> dict[str, Any]:
    """Анкета заказчика или пустой словарь. Отсутствие файла — не отказ."""
    import json

    path = find_data_file(CUSTOMER_SURVEY)
    if path is None:
        return {}
    try:
        loaded = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def block_titles(survey: Any) -> dict[str, str]:
    """
    Подписи блоков: сперва из самой анкеты, недостающие — из файла заказчика.

    Порядок именно такой. Анкета прогона главнее: она описывает ТО
    исследование, а файл заказчика правится и мог уехать вперёд. Но в базе
    анкета хранится списком вопросов без блоков, и тогда без файла подписей
    не будет вовсе.
    """
    titles = dict(block_labels(survey))
    for block_id, label in block_labels(_customer_file()).items():
        titles.setdefault(block_id, label)
    return titles


def customer_survey_version() -> str | None:
    """Версия анкеты заказчика для листа «О прогоне». `None` — файла нет."""
    version = _customer_file().get("version")
    return str(version) if version else None


def cards_to_answers(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Карточки из Mongo в форму, которую читает сборщик.

    Карточка уже почти годится: `_answers_of` умеет разворачивать и вложенный
    `answer`, и плоскую форму. Приводится здесь только адрес ответа —
    `persona_id` и `replication`: по ним идут и группировка по персонам, и
    отсев по флагам QA, и оба обязаны видеть одни и те же ключи.
    """
    out: list[dict[str, Any]] = []
    for card in cards:
        out.append({
            "persona_id": str(card.get("persona_id") or ""),
            "replication": int(card.get("replication") or 0),
            "answer": card.get("answer") if isinstance(card.get("answer"), dict) else {},
        })
    return out


def flags_from_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Флаги QA обратно одним списком.

    `save_report` разложил их по карточкам — экран открывает карточки
    постранично, и общий список ему негде взять. Выгрузке нужен обратный ход:
    `aggregate.surviving` отсеивает по плоскому списку, и собрать его обязан
    тот, кто читает карточки. Не собрал бы — таблица посчиталась бы по другой
    выборке, чем отчёт, и разошлись бы они молча.
    """
    out: list[dict[str, Any]] = []
    for card in cards:
        for flag in card.get("qa_flags") or []:
            if not isinstance(flag, dict):
                continue
            # Адрес дописывается, если его нет: карточка знает его точно, а
            # флаг, сохранённый без persona_id, отсев бы пропустил.
            item = dict(flag)
            item.setdefault("persona_id", card.get("persona_id"))
            item.setdefault("replication", card.get("replication") or 0)
            out.append(item)
    return out


def personas_in_order(
    cards: list[dict[str, Any]],
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Строки книги: по одной на персону, в порядке появления в карточках.

    ─── Почему список строится по карточкам, а не по реестру ────────────────
    Персону могли удалить или отредактировать после прогона. Идти от реестра
    значило бы потерять строку вместе с её ответами — то есть молча выкинуть из
    выгрузки часть выборки, по которой посчитан отчёт.

    Демография берётся из реестра, когда персона там есть. Когда её нет,
    остаётся срез, записанный в карточку в момент прогона (`segment`): в нём
    только пол и тип населённого пункта, и остальные колонки останутся
    ПУСТЫМИ. Пустая ячейка честна, а подставленное значение — нет: отличить
    придуманный возраст от настоящего в готовом файле уже нечем.
    """
    seen: dict[str, dict[str, Any]] = {}
    for card in cards:
        pid = str(card.get("persona_id") or "")
        if not pid or pid in seen:
            continue
        known = registry.get(pid)
        if known:
            seen[pid] = known
            continue
        segment = card.get("segment") if isinstance(card.get("segment"), dict) else {}
        seen[pid] = {
            "id": pid,
            "name": card.get("persona_name"),
            "dna": {"demographics": {
                key: value for key, value in segment.items() if key in ("gender", "geo")
            }},
        }
    return list(seen.values())


def render_workbook(
    *,
    survey: Any,
    cards: list[dict[str, Any]],
    personas: list[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
) -> bytes:
    """
    Готовые байты xlsx.

    `personas` — реестр персон; чего в нём нет, достраивается по карточкам
    (см. `personas_in_order`). `cards` — документы `report_personas` как есть.
    """
    registry = {
        str(p.get("id")): p for p in (personas or []) if p.get("id") is not None
    }
    info = dict(meta or {})
    info.setdefault("survey_version", customer_survey_version())

    wb = build_workbook(
        survey,
        cards_to_answers(cards),
        personas_in_order(cards, registry),
        meta=info,
        blocks=block_titles(survey),
        qa_flags=flags_from_cards(cards),
    )

    # `save` в буфер, а не во временный файл: файл пришлось бы удалять, и
    # отказ по дороге оставил бы мусор в контейнере, который никто не чистит.
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
