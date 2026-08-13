"""
Покрытие анкеты считается по тому, что персона реально присылает.

─── Как это нашлось ─────────────────────────────────────────────────────────
Первый успешный сквозной прогон дал REPORT_READY за 930 секунд — и отчёт,
построенный на ТРЁХ ответах из одиннадцати. QA забраковал девять, и семь из
девяти с одной и той же причиной:

    анкета покрыта не полностью, нет ответов: base-1, base-2, base-3, base-4, base-5

Причина не в модели. Правило сравнивало идентификаторы вопросов анкеты с
ключами `answer["survey_answers"]`, а базовые критерии приезжают не там: промпт
респондента требует их в `scores`, и ключом служит `baseKey`
(`overall_impression`, `plot`, …), а не `id` вопроса (`base-1`, `base-2`, …).

Две стороны контракта написаны порознь и никогда не сверялись, потому что
правило было МЁРТВЫМ: анкета доезжала до воркера списком, разбиралась как
словарь, список вопросов получался пустым — и проверка молча пропускала всё.
Починка формы анкеты её оживила, и мёртвое правило сразу начало браковать
правильные ответы.

Отсюда мораль, ради которой написан этот файл: включение спавшей проверки —
это изменение поведения, а не восстановление. Её нужно проверять так же, как
новую.

─── Почему это дороже, чем кажется ──────────────────────────────────────────
Отчёт на трёх ответах из одиннадцати выглядит нормальным отчётом. NPS −100,
эмоциональный индекс 10, «100% испытали скепсис» — всё это честные числа по
трём ответам, и по ним принимают решение о материале.
"""

from __future__ import annotations

from agent_core.qa.checks import consistency_reasons

#: Анкета в форме, которую присылает веб: пять базовых критериев с baseKey и
#: один пользовательский вопрос без него.
SURVEY = [
    {"id": "base-1", "baseKey": "overall_impression", "label": "Общее впечатление",
     "type": "scale", "scaleMin": 1, "scaleMax": 10},
    {"id": "base-2", "baseKey": "plot", "label": "Сюжет", "type": "scale",
     "scaleMin": 1, "scaleMax": 10},
    {"id": "q-open", "label": "Что запомнилось", "type": "open"},
]


def _answer(**over):
    """Ответ персоны в той форме, в какой его возвращает respondent.user."""
    base = {
        "scores": {"overall_impression": 7, "plot": 6},
        "perception": {"retention_intent": "досмотрел бы", "recommendation_nps_1_to_10": 7},
        "verbatims": {"why_impression": "Понравился финал на 01:20"},
        "survey_answers": {"q-open": "запомнилась сцена в поезде"},
    }
    base.update(over)
    return base


def test_base_criteria_in_scores_count_as_answered():
    """
    Базовый критерий засчитан, когда балл есть в `scores`.

    Именно здесь правило браковало семь ответов из одиннадцати на первом
    успешном прогоне: искало base-1…base-5 в survey_answers, а они лежат в
    scores под своими baseKey.
    """
    reasons = consistency_reasons(_answer(), SURVEY)
    assert not any("анкета покрыта" in r for r in reasons), reasons


def test_missing_base_criterion_is_still_caught():
    """
    Правило не выключено, а исправлено.

    Пропущенный балл — настоящий дефект: среднее по критерию посчитается по
    меньшей выборке, а в отчёте это будет неотличимо от честного числа.
    """
    answer = _answer(scores={"overall_impression": 7})  # нет plot
    reasons = consistency_reasons(answer, SURVEY)
    assert any("анкета покрыта" in r for r in reasons), reasons
    assert any("plot" in r or "base-2" in r for r in reasons), reasons


def test_missing_custom_question_is_caught():
    """Пользовательский вопрос по-прежнему проверяется по survey_answers."""
    answer = _answer(survey_answers={})
    reasons = consistency_reasons(answer, SURVEY)
    assert any("анкета покрыта" in r for r in reasons), reasons
    assert any("q-open" in r for r in reasons), reasons


def test_no_survey_no_coverage_claim():
    """
    Без анкеты правило молчит.

    Прогон без анкеты законен: персоны отвечают по пяти базовым критериям.
    Требовать покрытия того, чего не спрашивали, значило бы браковать всё.
    """
    assert not any("анкета покрыта" in r for r in consistency_reasons(_answer(), None))
