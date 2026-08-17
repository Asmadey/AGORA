"""
Покрытие анкеты считается по тому, что промпт разрешает персоне писать.

─── Как это нашлось ─────────────────────────────────────────────────────────
Прогон после починки таймкодов: отбраковки по `grounding` упали с восьми до
одной — и на их место встали восемь по `consistency`, все с одной причиной:

    анкета покрыта не полностью, нет ответов: base-6, q-1786730705947

Разбор показал два расхождения, и оба — между правилом и промптом, а не между
ответом и материалом.

**Первое: ключ ответа.** Промпт респондента прямо разрешает
`"survey_answers": { "<id или текст вопроса>": … }`. Персона, написавшая
формулировку вместо идентификатора, выполнила инструкцию буквально — и была
забракована правилом, которое ищет только по `id`.

**Второе: типовой вопрос.** `base-6` — «Какую часть ролика вы бы досмотрели»,
тип `watched_share`. Ответ на него промпт требует класть в
`perception.watched_share_pct`, а не в `survey_answers`. Правило искало его в
`survey_answers` и не находило никогда.

Это тот же дефект, что был с пятью базовыми баллами: они лежат в `scores` под
`baseKey`, а правило сравнивало с ключами `survey_answers`. Его починили, а
соседний случай остался — заплатка не уменьшает число таких мест.

─── Почему правило подстраивается под промпт, а не наоборот ─────────────────
Промпт — это то, что видит модель, и он описывает формат ответа целиком. Правило
— читатель этого формата. Читатель, требующий строже, чем сказано автору,
браковать будет исправные ответы, а выглядеть это будет как плохое качество
модели: доля выживших падает, объяснение звучит правдоподобно, и никто не
проверит, кто именно неправ.
"""

from __future__ import annotations

from agent_core.qa.checks import consistency_reasons

SURVEY = [
    {"id": "base-1", "baseKey": "overall_impression", "label": "Общее впечатление",
     "type": "scale"},
    {"id": "base-6", "label": "Какую часть ролика вы бы досмотрели",
     "type": "watched_share"},
    {"id": "q-77", "label": "Что запомнилось больше всего", "type": "open"},
]


def _answer(**over: object) -> dict:
    base = {
        "scores": {"overall_impression": 7, "plot": 6, "acting": 7, "music": 5,
                   "cinematography": 6},
        "perception": {
            "interest_level": "скорее интересен",
            "emotions_evoked": ["интерес"],
            "idea_comprehension": "понятно",
            "realism_perception": "реалистичные",
            "retention_intent": "скорее досмотреть",
            "watched_share_pct": 60,
            "recommendation_nps_1_to_10": 7,
        },
        "survey_answers": {"q-77": "заставка"},
        "verbatims": {"why_impression": "цепляет"},
        "grounding_refs": ["0:44–0:48"],
    }
    base.update(over)  # type: ignore[arg-type]
    return base


def _coverage_complaint(reasons: list[str]) -> str | None:
    return next((r for r in reasons if "покрыта не полностью" in r), None)


def test_typed_question_is_answered_by_the_structured_block():
    """
    `watched_share` отвечается полем `perception.watched_share_pct`.

    Так требует промпт. Искать этот ответ в `survey_answers` значит не находить
    его никогда — и браковать каждого респондента, чья анкета содержит вопрос о
    доле просмотра.
    """
    assert _coverage_complaint(consistency_reasons(_answer(), SURVEY)) is None


def test_answer_keyed_by_label_counts():
    """
    Промпт разрешает ключ «id ИЛИ текст вопроса». Персона, написавшая текст,
    выполнила инструкцию — правило обязано это принять.
    """
    answer = _answer(survey_answers={"Что запомнилось больше всего": "заставка"})

    assert _coverage_complaint(consistency_reasons(answer, SURVEY)) is None


def test_answer_keyed_by_the_prompt_line_counts():
    """
    Третий случай той же семьи — и самый дорогой из трёх.

    Промпт печатает вопрос строкой ``- [q-77] (open) Что запомнилось больше
    всего`` (`respondent/run.py:228`), а формат ответа разрешает ключ «id или
    текст вопроса». Модель берёт строку целиком — она видит именно её, и это
    буквальное исполнение инструкции, а не отсебятина.

    Правило искало точное совпадение с `id` либо с `label` и не находило ни
    того, ни другого. Цена измерена на golden-сете 17.08.2026: из восьми-девяти
    отбраковок в прогоне три-шесть приходились на один и тот же вопрос
    `q-1786730705947` («как дела?»), отвеченный ключом
    ``[q-1786730705947] (scale) как дела?``. Ни один из трёх прогонов не
    добрал 2/3 выживших; без этих отбраковок все три добирают.
    """
    answer = _answer(
        survey_answers={"[q-77] (open) Что запомнилось больше всего": "заставка"}
    )

    assert _coverage_complaint(consistency_reasons(answer, SURVEY)) is None


def test_prompt_line_of_another_question_does_not_count():
    """
    Послабление узкое: строка чужого вопроса не закрывает наш.

    Иначе правило начало бы засчитывать любой ключ в квадратных скобках, и
    пропуск вопроса перестал бы отличаться от ответа на него.
    """
    answer = _answer(survey_answers={"[q-99] (open) Совсем другой вопрос": "нечто"})
    complaint = _coverage_complaint(consistency_reasons(answer, SURVEY))

    assert complaint is not None and "q-77" in complaint


def test_genuinely_missing_answer_is_still_caught():
    """
    Послабление не должно превратить правило в декорацию: вопрос, на который не
    ответили ни идентификатором, ни текстом, ни структурным полем, обязан быть
    назван. Иначе отчёт покажет пустую секцию как «никто не высказался».
    """
    answer = _answer(survey_answers={})
    complaint = _coverage_complaint(consistency_reasons(answer, SURVEY))

    assert complaint is not None
    assert "q-77" in complaint
    # base-6 при этом отвечен структурным полем и в жалобе быть не должен.
    assert "base-6" not in complaint


def test_missing_watched_share_is_caught():
    """Если вопрос о доле просмотра есть, а поля нет — это пропуск."""
    answer = _answer()
    answer["perception"] = {k: v for k, v in answer["perception"].items()  # type: ignore[union-attr]
                            if k != "watched_share_pct"}
    complaint = _coverage_complaint(consistency_reasons(answer, SURVEY))

    assert complaint is not None and "base-6" in complaint
