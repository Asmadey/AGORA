"""
Выгрузка в Excel повторяет форму полевого файла заказчика.

─── Откуда форма ────────────────────────────────────────────────────────────
Из его собственного файла `Тюремный_дневник_Заполненные_респондентами_анкеты.xlsx`
(28 респондентов, 183 колонки), разобранного 17.09.2026:

* шапка из ДВУХ строк — блок, затем формулировка вопроса, объединённые по
  своим колонкам;
* данные с третьей строки, строка — респондент;
* параметры аудитории слева, до вопросов;
* множественный выбор занимает столько соседних колонок, сколько разрешено
  ответов, и в ячейке лежит ТЕКСТ варианта, а не 0/1;
* шкалы — целым числом, закрытые вопросы — дословной подписью варианта,
  включая «Затрудняюсь ответить».

Это не оформление, а форма, в которой заказчик получает и читает данные. Две
выгрузки по разным исследованиям должны класться рядом колонка в колонку — на
этом держится сравнение волн.

─── Почему проверяется файл, а не вызовы ────────────────────────────────────
Проверять, что функция «позвала openpyxl», бессмысленно: расходится не вызов, а
результат. Тесты открывают собранную книгу и читают ячейки.
"""
from __future__ import annotations

import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
SURVEY = json.loads((REPO / "data" / "survey" / "customer_2026.json").read_text("utf-8"))

pytest.importorskip(
    "openpyxl", reason="openpyxl объявлена в зависимостях воркера; без неё выгрузку не собрать"
)

from agent_core.analytics.excel_export import (  # noqa: E402
    AUDIENCE_COLUMNS,
    build_workbook,
)


def persona(pid: str, name: str, age: int, city: str, gender: str = "жен") -> dict:
    return {
        "id": pid,
        "name": name,
        "dna": {
            "demographics": {
                "age": age, "gender": gender, "city": city,
                "geo": "центры субъектов", "children": "Нет детей",
            }
        },
    }


def answer(pid: str, fields: dict, replication: int = 0) -> dict:
    return {
        "persona_id": pid,
        "replication": replication,
        "answer": {"survey_answers": dict(fields)},
    }


THEMED = [q for q in SURVEY["questions"]]
PERSONAS = [persona("p0", "Анна", 30, "Пермь"), persona("p1", "Борис", 50, "Москва", "муж")]
ANSWERS = [
    answer("p0", {"q01-plot": 8, "q07-emotions": "e-3, e-5", "q10-importance": "i-1",
                  "t1-1": "m-1"}),
    answer("p1", {"q01-plot": 3, "q07-emotions": "e-s2", "q10-importance": "i-2",
                  "t1-1": "m-2"}),
]


BLOCKS = {b["id"]: b["label"] for b in SURVEY["blocks"]}


def sheet():
    return build_workbook(
        THEMED, ANSWERS, PERSONAS, meta={"number": "0052"}, blocks=BLOCKS,
    )["Ответы"]


def test_подписи_блоков_берутся_из_анкеты_целиком():
    """Документ анкеты несёт подписи блоков сам — передавать их отдельно не обязано."""
    ws = build_workbook(SURVEY, ANSWERS, PERSONAS, meta={})["Ответы"]
    assert ws.cell(row=1, column=len(AUDIENCE_COLUMNS) + 1).value == "Оценки проекта"


def row(n: int) -> list:
    return [c.value for c in sheet()[n]]


# ─── Шапка ───────────────────────────────────────────────────────────────────


def test_шапка_из_двух_строк_данные_с_третьей():
    ws = sheet()
    assert ws.max_row == 2 + len(PERSONAS)


def test_параметры_аудитории_стоят_слева_до_вопросов():
    """У заказчика они первые: населённый пункт, идентификатор, пол, возраст."""
    head = row(2)
    assert head[: len(AUDIENCE_COLUMNS)] == [c[0] for c in AUDIENCE_COLUMNS]
    assert head[0] == "Населенный пункт"


def _merge_span(ws, row_no: int, column: int) -> tuple[int, int] | None:
    """Границы объединения, в котором стоит ячейка. None — не объединена."""
    for rng in ws.merged_cells.ranges:
        if rng.min_row == row_no == rng.max_row and rng.min_col <= column <= rng.max_col:
            return rng.min_col, rng.max_col
    return None


def test_верхняя_строка_несёт_блок_а_нижняя_формулировку():
    """
    Значение объединённой ячейки лежит ТОЛЬКО в первой колонке диапазона — так
    же устроен файл заказчика. Поэтому блок ищется по началу объединения, а не
    в колонке вопроса.
    """
    ws = sheet()
    blocks = BLOCKS
    bottom = [c.value for c in ws[2]]
    plot = [q for q in THEMED if q["number"] == 1][0]
    column = bottom.index(plot["label"]) + 1
    span = _merge_span(ws, 1, column)
    start = span[0] if span else column
    assert ws.cell(row=1, column=start).value == blocks[plot["block"]]


def test_каждая_персона_одна_строка():
    """
    Решение владельца 17.09.2026: строка — персона, не ответ. При перекрытии
    больше единицы числа усредняются по повторам.
    """
    ws = sheet()
    ids = [ws.cell(row=r, column=2).value for r in (3, 4)]
    assert ids == ["p0", "p1"]


# ─── Значения ────────────────────────────────────────────────────────────────


def _value(label: str, persona_row: int):
    ws = sheet()
    head = [c.value for c in ws[2]]
    return ws.cell(row=persona_row, column=head.index(label) + 1).value


def test_шкала_пишется_числом():
    plot = [q for q in THEMED if q["number"] == 1][0]
    assert _value(plot["label"], 3) == 8
    assert _value(plot["label"], 4) == 3


def test_закрытый_вопрос_пишется_подписью_варианта():
    q10 = [q for q in THEMED if q["number"] == 10][0]
    assert _value(q10["label"], 3) == "Скорее важные"
    assert _value(q10["label"], 4) == "Скорее не важные"


def test_мультивыбор_занимает_колонку_на_каждый_разрешённый_ответ():
    """
    У заказчика «Какие ценности являются наиболее важными» занимает пять
    соседних колонок с текстом вариантов — по колонке на разрешённый ответ.
    """
    ws = sheet()
    head = [c.value for c in ws[2]]
    q7 = [q for q in THEMED if q["number"] == 7][0]
    first = head.index(q7["label"]) + 1
    span = _merge_span(ws, 2, first)
    assert span is not None, "колонки одного вопроса объединены в шапке"
    assert span[1] - span[0] + 1 == q7["maxChoices"], (
        f"вопрос занимает {span[1] - span[0] + 1} колонок вместо {q7['maxChoices']}"
    )
    values = [ws.cell(row=3, column=first + k).value for k in range(q7["maxChoices"])]
    assert values == ["Гордость", "Надежда", None], "порядок называния сохраняется"


def test_служебный_вариант_пишется_дословно():
    ws = sheet()
    head = [c.value for c in ws[2]]
    q7 = [q for q in THEMED if q["number"] == 7][0]
    first = head.index(q7["label"])
    assert ws.cell(row=4, column=first + 1).value == "Затрудняюсь ответить"


def test_строка_матрицы_становится_своей_колонкой():
    row_label = [q for q in THEMED if q["number"] == 9][0]["rows"][0]["label"]
    assert _value(row_label, 3) == "Скорее эта тема поднималась"
    assert _value(row_label, 4) == "Скорее эта тема не поднималась"


def test_неотвеченное_поле_пустое_а_не_ноль():
    """
    Ноль — законный балл на шкале 0–10. Записать им пропуск значило бы утянуть
    среднее вниз на величину, которой никто не называл.
    """
    q2 = [q for q in THEMED if q["number"] == 2][0]
    assert _value(q2["label"], 3) is None


# ─── Второй лист ─────────────────────────────────────────────────────────────


def test_лист_о_прогоне_называет_состав_и_версию_анкеты():
    wb = build_workbook(THEMED, ANSWERS, PERSONAS, meta={"number": "0052"})
    assert "О прогоне" in wb.sheetnames
    text = "\n".join(
        str(c.value) for r in wb["О прогоне"].iter_rows() for c in r if c.value is not None
    )
    assert "0052" in text
    assert "персон" in text


# ─── Гейтинг QA ──────────────────────────────────────────────────────────────


def test_ответ_нарушивший_правило_в_свёртку_не_идёт():
    """
    Выгрузка «сырая», но не любая: балл вне шкалы 0–10 — это брак, а не мнение,
    и в усреднение по повторам он попадать не должен. Отбор тот же, что в
    отчёте (`aggregate.surviving`), иначе таблица и отчёт разойдутся молча.
    """
    answers = [
        answer("p0", {"q01-plot": 8}, replication=0),
        answer("p0", {"q01-plot": 2}, replication=1),
    ]
    flags = [{"persona_id": "p0", "replication": 1, "verdict": "regenerate", "source": "rule"}]
    ws = build_workbook(
        THEMED, answers, [PERSONAS[0]], meta={}, blocks=BLOCKS, qa_flags=flags,
    )["Ответы"]
    head = [c.value for c in ws[2]]
    plot = [q for q in THEMED if q["number"] == 1][0]
    assert ws.cell(row=3, column=head.index(plot["label"]) + 1).value == 8


def test_вердикт_судьи_из_выгрузки_не_выбрасывает():
    answers = [
        answer("p0", {"q01-plot": 8}, replication=0),
        answer("p0", {"q01-plot": 2}, replication=1),
    ]
    flags = [{"persona_id": "p0", "replication": 1, "verdict": "regenerate", "source": "judge"}]
    ws = build_workbook(
        THEMED, answers, [PERSONAS[0]], meta={}, blocks=BLOCKS, qa_flags=flags,
    )["Ответы"]
    head = [c.value for c in ws[2]]
    plot = [q for q in THEMED if q["number"] == 1][0]
    assert ws.cell(row=3, column=head.index(plot["label"]) + 1).value == 5, "среднее 8 и 2"
