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

from agent_core.qa.checks import consistency_reasons, coverage_reasons

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
    reasons = coverage_reasons(_answer(), SURVEY)
    assert not any("анкета покрыта" in r for r in reasons), reasons


def test_missing_base_criterion_is_still_caught():
    """
    Правило не выключено, а исправлено.

    Пропущенный балл — настоящий дефект: среднее по критерию посчитается по
    меньшей выборке, а в отчёте это будет неотличимо от честного числа.
    """
    answer = _answer(scores={"overall_impression": 7})  # нет plot
    reasons = coverage_reasons(answer, SURVEY)
    assert any("анкета покрыта" in r for r in reasons), reasons
    assert any("plot" in r or "base-2" in r for r in reasons), reasons


def test_missing_custom_question_is_caught():
    """Пользовательский вопрос по-прежнему проверяется по survey_answers."""
    answer = _answer(survey_answers={})
    reasons = coverage_reasons(answer, SURVEY)
    assert any("анкета покрыта" in r for r in reasons), reasons
    assert any("q-open" in r for r in reasons), reasons


def test_no_survey_no_coverage_claim():
    """
    Без анкеты правило молчит.

    Прогон без анкеты законен: персоны отвечают по пяти базовым критериям.
    Требовать покрытия того, чего не спрашивали, значило бы браковать всё.
    """
    assert not any("анкета покрыта" in r for r in coverage_reasons(_answer(), None))


# ─── Матрица: ответ лежит по строке, а не по вопросу ─────────────────────────
#
# Третий случай одного и того же расхождения. Сперва правило искало базовые
# критерии в `survey_answers`, а они в `scores`. Потом — вопрос о доле
# просмотра там же, а он в `perception`. Теперь — матрица: `render_questions`
# печатает её ПОСТРОЧНО, промпт просит ответ на каждую строку, и все читатели
# (`survey_stats`, `excel_export`, проба нагрузки) адресуют ответ
# идентификатором СТРОКИ. Правило же по-прежнему ищет идентификатор ВОПРОСА.
#
# Цена та же, что и в прошлые два раза, только больше: анкета заказчика стоит
# на двух матрицах из пятнадцати вопросов, и ни один ответ не прошёл бы
# покрытие — `surviving()` выбросила бы выборку целиком, а отчёт на пустой
# выборке выглядит как отчёт.

MATRIX_SURVEY = [
    {"id": "base-1", "baseKey": "overall_impression", "label": "Общее впечатление",
     "type": "scale", "scaleMin": 0, "scaleMax": 10},
    {
        "id": "q-themes",
        "label": "Поднимались ли темы",
        "type": "matrix_single",
        "options": [
            {"id": "m-1", "label": "Скорее поднималась"},
            {"id": "m-2", "label": "Скорее не поднималась"},
        ],
        "rows": [
            {"id": "t1-1", "themeId": "t1", "label": "Семья"},
            {"id": "t1-2", "themeId": "t1", "label": "Дружба"},
        ],
    },
]


def test_матрица_закрыта_ответами_по_строкам():
    answer = {
        "scores": {"overall_impression": 8},
        "survey_answers": {"t1-1": "m-1", "t1-2": "m-2"},
    }
    reasons = coverage_reasons(answer, MATRIX_SURVEY)
    assert not any("анкета покрыта" in r for r in reasons), reasons


def test_пропущенная_строка_матрицы_названа_поимённо():
    """
    Обратная сторона: правило не должно закрывать матрицу целиком по одной
    строке — иначе персона, ответившая на первую подтему из сорока трёх,
    считалась бы заполнившей анкету.
    """
    answer = {
        "scores": {"overall_impression": 8},
        "survey_answers": {"t1-1": "m-1"},
    }
    reasons = coverage_reasons(answer, MATRIX_SURVEY)
    assert reasons, "пропущенная строка обязана быть замечена"
    assert "t1-2" in " ".join(reasons)
    assert "t1-1" not in " ".join(reasons), "отвеченная строка в пропуски не попадает"


# ─── Шкала базовых критериев берётся из анкеты, а не из памяти ──────────────
#
# Решение владельца 17.09.2026: базовые критерии живут на шкале 0–10. Правило
# согласованности при этом продолжало требовать 1–10 и браковало каждый ответ,
# где персона поставила ноль:
#
#     балл overall_impression=0 вне шкалы 1–10
#
# Ноль на шкале 0–10 — законная и самая информативная оценка: «совсем не
# понравилось». Забракованный по этой причине ответ выбывает из агрегата
# правилом (`source: "rule"`), то есть самые низкие оценки уходили бы из
# отчёта СИСТЕМАТИЧЕСКИ, а средний балл поднимался бы сам собой.

ZERO_TEN = [
    {"id": "base-1", "baseKey": "overall_impression", "label": "Общее впечатление",
     "type": "scale", "scaleMin": 0, "scaleMax": 10},
]


def _zero_answer(score: int) -> dict:
    return {
        "scores": {"overall_impression": score},
        "survey_answers": {},
        "verbatims": {"why_impression": "Скучно с самого начала на 00:10"},
        "perception": {},
    }


def test_ноль_на_шкале_ноль_десять_законен():
    reasons = consistency_reasons(_zero_answer(0), ZERO_TEN)
    assert not any("вне шкалы" in r for r in reasons), reasons


def test_балл_выше_границы_анкеты_всё_ещё_брак():
    reasons = consistency_reasons(_zero_answer(11), ZERO_TEN)
    assert any("вне шкалы" in r for r in reasons), reasons


# ─── Покрытие — отдельный вид претензии ──────────────────────────────────────
#
# Решение владельца 17.09.2026: неполный ответ есть ошибка, и закрывают её три
# меры в связке — грамматика ответа, правило QA и переспрос.
#
# Переспрос выбирает подсказку ПО ВИДУ претензии (`requestion.kinds_for`).
# Пока покрытие лежало внутри `consistency`, персона получала подсказку про
# «ответ разошёлся сам с собой» — то есть про другое. Подсказка не по адресу
# хуже её отсутствия: она тратит переспрос, который стоит как полный вызов.


def test_покрытие_называет_себя_отдельным_видом():
    from agent_core.qa.checks import coverage_reasons

    answer = {"scores": {"overall_impression": 8}, "survey_answers": {"t1-1": "m-1"}}
    assert any("покрыта не полностью" in r for r in coverage_reasons(answer, MATRIX_SURVEY))
    assert coverage_reasons(
        {"scores": {"overall_impression": 8},
         "survey_answers": {"t1-1": "m-1", "t1-2": "m-2"}},
        MATRIX_SURVEY,
    ) == []


def test_согласованность_про_покрытие_больше_не_говорит():
    """
    Две проверки — два вида. Иначе персона, ответившая полно, но противоречиво,
    и персона, ответившая непротиворечиво, но неполно, получали бы одну и ту же
    подсказку.
    """
    answer = {"scores": {"overall_impression": 8}, "survey_answers": {"t1-1": "m-1"}}
    assert not any(
        "покрыта не полностью" in r for r in consistency_reasons(answer, MATRIX_SURVEY)
    )


def test_переспрос_знает_подсказку_для_покрытия():
    from agent_core.respondent.requestion import hint_for

    hint = hint_for({"coverage"})
    assert hint, "подсказки по покрытию нет — переспрос уйдёт впустую"
    assert "каждой строке" in hint or "каждый" in hint
