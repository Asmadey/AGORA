"""
Анкета доезжает до персоны в той форме, в какой её присылает веб.

Написан после третьего сквозного прогона, упавшего на
`AttributeError: 'list' object has no attribute 'get'` в `_render_questions`.
Между вебом и воркером разошлись сразу две вещи, и обе — молча:

1. **Форма.** `POST /api/tasks` кладёт в очередь `survey` — то, что лежит в
   колонке `surveys.questions`, то есть СПИСОК вопросов. Воркер ждал словарь и
   звал у списка `.get("questions")`.

2. **Имя поля.** Вопрос в продукте — это `{id, label, type, scaleMin, scaleMax}`
   (`apps/web/lib/agora-types.ts`, JSON Schema анкеты, конструктор). Воркер
   читал `text`, которого там нет. Даже с исправленной формой персона получила
   бы список из пустых строк — и это хуже отказа: прогон прошёл бы целиком,
   стоил бы полную цену и дал бы ответы на вопросы, которых персона не видела.

─── Почему это не поймали существующие тесты ────────────────────────────────
`test_respondent.py` и CDD #18 строят анкету сами — в той форме, которую ждёт
воркер. Тест, который сам себе готовит вход, проверяет согласованность кода с
самим собой, а не с тем, кто его вызывает. Поэтому здесь вход собран ровно так,
как его собирает `apps/web/app/api/tasks/route.ts`, и менять его нельзя без
правки маршрута.
"""

from __future__ import annotations

import pytest

from agent_core.respondent.run import _render_questions

#: Анкета в точности как из базы: колонка `surveys.questions` — JSON-массив.
#: Поля те же, что в agora-types.ts и в JSON Schema, включая `label`.
WEB_SURVEY = [
    {"id": "base-1", "baseKey": "overall_impression", "label": "Общее впечатление",
     "type": "scale", "scaleMin": 1, "scaleMax": 10},
    {"id": "base-6", "label": "Какую часть ролика вы бы досмотрели",
     "type": "watched_share", "scaleMin": 0, "scaleMax": 100},
    {"id": "q-7", "label": "Что запомнилось больше всего", "type": "open"},
]


def test_survey_as_list_renders():
    """Форма из очереди — список. Раньше здесь падал AttributeError."""
    out = _render_questions(WEB_SURVEY)
    assert "Общее впечатление" in out, out


def test_every_question_reaches_the_persona():
    """
    Ни один вопрос не теряется.

    Потерянный вопрос не виден нигде: персона просто не отвечает на него, а
    аналитика считает среднее по тем, кто ответил. Пустая секция в отчёте
    читается как «никто не высказался», а не как «вопрос не задали».
    """
    out = _render_questions(WEB_SURVEY)
    for q in WEB_SURVEY:
        assert q["label"] in out, f"вопрос {q['id']} не доехал:\n{out}"


def test_question_text_is_not_empty():
    """
    Формулировка не подменяется пустотой.

    Воркер читал поле `text`, которого в контракте нет. Список из «- [q-7] ()»
    отправился бы в модель как настоящая анкета: прогон прошёл бы целиком и
    стоил бы полную цену.
    """
    out = _render_questions(WEB_SURVEY)
    for line in out.splitlines():
        payload = line.split(")", 1)[-1].strip()
        assert payload, f"строка без формулировки: {line!r}"


def test_legacy_dict_form_still_works():
    """
    Прежняя форма `{"questions": [...]}` не сломана.

    На неё опираются фикстуры CDD #18 и ручные прогоны. Совместимость здесь
    дешевле правки четырёх тестов, а расхождения не создаёт: обе формы ведут к
    одному списку.
    """
    out = _render_questions({"questions": WEB_SURVEY})
    assert "Общее впечатление" in out


@pytest.mark.parametrize("empty", [None, [], {}, {"questions": []}])
def test_empty_survey_says_so(empty):
    """Пустая анкета названа пустой, а не отрисована пустой строкой."""
    assert _render_questions(empty) == "(анкета пуста)"
