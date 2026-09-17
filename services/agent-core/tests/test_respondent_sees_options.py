"""
Промпт персоны несёт варианты закрытого вопроса, а не одну формулировку.

─── Почему проверка стоит на стыке, а не на рендере ─────────────────────────
Рендер уже проверен отдельно (`test_survey_render.py`). Здесь проверяется, что
его результат ДОЕЗЖАЕТ до промпта через `build_slice`, — то есть ровно тот
стык, на котором этот проект ошибался четыре раза подряд:

* `verbatim_pool` объявлен в промпте судьи и не передавался из продового вызова —
  раздел рендерился пустым, а критерий отбраковки на него ссылался;
* `question_label` читался воркером из поля `text`, которого в контракте нет, —
  персоны получали пустые формулировки;
* шапка `Переменные: …` не срезалась, и данные дублировались в промпте до пяти раз;
* `qaFlags` писались одним именем поля, читались другим.

Общее у всех четырёх: прогон проходит целиком, стоит полную цену и возвращает
правдоподобный результат. Отличить его от честного по содержимому нельзя —
только проверкой на стыке.

Закрытый вопрос без вариантов ведёт себя точно так же. Персона назовёт эмоцию
своими словами, ответ разберётся, отчёт соберётся — и не сойдётся с закрытым
списком заказчика, в котором тринадцать строк и ни одной свободной.
"""
from __future__ import annotations

import json
import pathlib

from agent_core.respondent.run import build_slice

REPO = pathlib.Path(__file__).resolve().parents[3]
SURVEY = json.loads((REPO / "data" / "survey" / "customer_2026.json").read_text("utf-8"))

PERSONA = {
    "dna": {
        "demographics": {"age_group": "25-34", "gender": "жен", "city": "Пермь"},
        "narrative": "Смотрит сериалы по вечерам.",
    }
}
PACK = {"title": "Тестовый материал", "scenes": []}
USER_TEMPLATE = "Материал: {{video_understanding}}\n\nАнкета:\n{{survey_questions}}\n"


def _user_prompt() -> str:
    _, user = build_slice(
        PERSONA, PACK, SURVEY["questions"],
        system_template="{{persona_dna}}",
        user_template=USER_TEMPLATE,
    )
    return user


def test_все_тринадцать_эмоций_в_промпте():
    user = _user_prompt()
    emotions = [
        o["label"]
        for q in SURVEY["questions"] if q["number"] == 7
        for o in q["options"] if not o.get("service")
    ]
    assert len(emotions) == 13
    missing = [e for e in emotions if e not in user]
    assert not missing, f"до персоны не доехали эмоции: {missing}"


def test_все_семнадцать_ценностей_в_промпте():
    user = _user_prompt()
    values = [
        o["label"]
        for q in SURVEY["questions"] if q["number"] == 8
        for o in q["options"] if not o.get("service")
    ]
    assert len(values) == 17
    missing = [v for v in values if v not in user]
    assert not missing, f"до персоны не доехали ценности: {missing}"


def test_все_сорок_три_подтемы_в_промпте():
    user = _user_prompt()
    rows = [r["label"] for q in SURVEY["questions"] if q["number"] == 9 for r in q["rows"]]
    assert len(rows) == 43
    missing = [r for r in rows if r not in user]
    assert not missing, f"до персоны не доехали подтемы: {missing}"


def test_все_одиннадцать_вопросов_воздействия_в_промпте():
    user = _user_prompt()
    rows = [r["label"] for q in SURVEY["questions"] if q["number"] == 11 for r in q["rows"]]
    assert len(rows) == 11
    missing = [r for r in rows if r not in user]
    assert not missing, f"до персоны не доехали вопросы воздействия: {missing}"


def test_потолок_выбора_доехал():
    assert "не более 3" in _user_prompt(), (
        "без потолка персона выберет столько эмоций, сколько захочет, "
        "и доли по вопросу 7 перестанут сходиться с долями заказчика"
    )


def test_старая_анкета_по_прежнему_рендерится():
    """
    В базе лежат прогоны со старой плоской анкетой. Рендер обязан принимать её
    так же: смена формы не должна ломать чтение того, что уже записано.
    """
    old = [
        {"id": "base-1", "label": "Общее впечатление", "type": "scale",
         "scaleMin": 1, "scaleMax": 10},
        {"id": "custom-1", "label": "Что запомнилось", "type": "open",
         "scaleMin": 0, "scaleMax": 0},
    ]
    _, user = build_slice(
        PERSONA, PACK, old,
        system_template="{{persona_dna}}", user_template=USER_TEMPLATE,
    )
    assert "Общее впечатление" in user
    assert "Что запомнилось" in user
