"""
Вопросы анкеты действительно уходят в модель — и это видно после прогона.

─── Чего не хватало ─────────────────────────────────────────────────────────
`test_survey_contract.py` проверяет `_render_questions`: список вопросов
превращается в текст, ни одна формулировка не теряется, пустая анкета названа
пустой. Это верно и недостаточно.

Между отрисовкой и моделью остаётся ещё один шаг — подстановка в шаблон
`prompts/respondent.user.md` по метке `{{survey_questions}}`. Подстановка
строкой: если метки в шаблоне нет (её убрали в Промпт-студии, или снимок
прогона старый, или файл в образе разошёлся с репозиторием), `str.replace`
ничего не делает и **не сообщает об этом**. Прогон идёт целиком, стоит полную
цену, персоны отвечают — по формату ответа из того же шаблона они обязаны
заполнить `survey_answers`, и они заполнят, придумав вопросы сами.

Отличить такой прогон от честного по отчёту нельзя: ответы есть, средние
посчитаны, разрез по сегментам построен. Именно поэтому «вопросы задаются»
нельзя оставлять на уровне «функция отрисовки работает».

Здесь проверяется то, что уходит в клиента: **каждый** промпт **каждой**
персоны на **каждой** репликации. И отдельно — что прогон отказывается
начинаться, когда метки в шаблоне нет: непотраченные деньги и внятная причина
лучше правдоподобного отчёта ни о чём.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_core.respondent.run import USER_PROMPT_PATH, run_survey

#: Анкета в точности той формы, в какой её кладёт в очередь POST /api/tasks:
#: список из колонки `surveys.questions`, поле формулировки — `label`.
WEB_SURVEY = [
    {"id": "base-1", "baseKey": "overall_impression", "label": "Общее впечатление",
     "type": "scale", "scaleMin": 1, "scaleMax": 10},
    {"id": "base-6", "label": "Какую часть ролика вы бы досмотрели",
     "type": "watched_share", "scaleMin": 0, "scaleMax": 100},
    {"id": "q-7", "label": "Что запомнилось больше всего", "type": "open"},
]

PACK = {"title": "Ролик", "scenes": [{"start": 0, "end": 5, "description": "заставка"}]}

ANSWER = json.dumps({
    "scores": {"overall_impression": 7, "plot": 6, "acting": 7, "music": 5,
               "cinematography": 6},
    "perception": {"interest_level": "скорее интересен", "emotions_evoked": ["интерес"],
                   "idea_comprehension": "понятно", "realism_perception": "реалистичные",
                   "retention_intent": "скорее досмотреть", "watched_share_pct": 60,
                   "recommendation_nps_1_to_10": 7},
    "survey_answers": {"base-1": 7, "base-6": 60, "q-7": "заставка"},
    "verbatims": {"why_impression": "цепляет", "memorable_elements": "заставка",
                  "character_opinions": "нет героев"},
    "grounding_refs": ["0:00–0:05"],
}, ensure_ascii=False)


class RecordingClient:
    """Запоминает всё, что ушло бы в модель. Ни одного сетевого вызова."""

    def __init__(self):
        self.prompts: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str) -> str:
        self.prompts.append((system, user))
        return ANSWER


def personas(n: int) -> list[dict]:
    return [
        {
            "id": f"p{i}",
            "name": f"Персона {i}",
            "dna": {
                "demographics": {"age_group": "25-34", "gender": "жен", "geo": "Москва"},
                "narrative": "смотрит сериалы вечерами",
            },
        }
        for i in range(n)
    ]


def _real_user_template() -> str:
    assert USER_PROMPT_PATH.exists(), f"шаблон не найден: {USER_PROMPT_PATH}"
    return USER_PROMPT_PATH.read_text("utf-8")


# ─── Метка в поставляемом шаблоне ────────────────────────────────────────────


def test_shipped_prompt_has_the_placeholder():
    """
    В `prompts/respondent.user.md` есть `{{survey_questions}}`.

    Проверка на файл, а не на подстановку: без метки подстановка тихо
    вырождается в копию шаблона, и все остальные проверки здесь проходят
    ровно потому, что анкета никуда не попала.
    """
    assert "{{survey_questions}}" in _real_user_template()


# ─── Каждый вопрос — в каждом промпте ────────────────────────────────────────


def test_every_question_reaches_every_prompt():
    """
    Три персоны, две репликации — шесть промптов, и в каждом вся анкета.

    Проверять один отрисованный кусок мало: срез собирается заново на каждый
    вызов, и потерять анкету можно, например, на персоне с пустой DNA.
    """
    client = RecordingClient()
    outcome = run_survey(
        personas=personas(3),
        pack=PACK,
        survey=WEB_SURVEY,
        client=client,
        replication_count=2,
        user_template=_real_user_template(),
        system_template="Ты — {{segment}}. {{persona_dna}}",
    )

    assert len(client.prompts) == 6, "не все персоны опрошены"
    assert outcome.failures == 0, outcome.failure_reasons

    for index, (_, user) in enumerate(client.prompts):
        assert "{{survey_questions}}" not in user, (
            f"промпт {index}: метка осталась неподставленной — анкета не доехала"
        )
        for question in WEB_SURVEY:
            assert question["label"] in user, (
                f"промпт {index}: вопрос {question['id']} «{question['label']}» "
                f"не попал в то, что уходит в модель"
            )


# ─── Отказ вместо правдоподобного прогона ────────────────────────────────────


def test_template_without_placeholder_fails_before_spending_money():
    """
    Шаблон без метки — отказ до первого обращения к модели.

    Раньше такой прогон проходил целиком: персоны заполняли `survey_answers`
    по формату ответа, придумав вопросы, а отчёт выглядел обычным.
    """
    client = RecordingClient()
    with pytest.raises(ValueError) as exc:
        run_survey(
            personas=personas(2),
            pack=PACK,
            survey=WEB_SURVEY,
            client=client,
            user_template="Посмотри {{content_title}} и ответь.\n{{video_understanding}}",
            system_template="Ты — зритель.",
        )

    assert "survey_questions" in str(exc.value), str(exc.value)
    assert client.prompts == [], "модель уже позвали — деньги потрачены зря"


def test_empty_survey_is_allowed():
    """
    Прогон без анкеты законен: пять базовых критериев в формате ответа.

    Иначе проверка выше запрещала бы то, что продукт разрешает.
    """
    client = RecordingClient()
    outcome = run_survey(
        personas=personas(1), pack=PACK, survey=[], client=client,
        user_template=_real_user_template(), system_template="Ты — зритель.",
    )
    assert len(client.prompts) == 1
    assert outcome.asked == []


# ─── След в артефакте ────────────────────────────────────────────────────────


def test_outcome_records_what_was_asked(tmp_path: Path):
    """
    Прогон оставляет список заданных вопросов рядом с ответами.

    Без него «вопросы задавались» проверяется только чтением кода — то есть
    доверием. Список едет в артефакт, оттуда в отчёт и на экран исследования:
    заказчик видит формулировки, которые получила персона, а не те, что лежат
    в анкете сейчас (её могли отредактировать после прогона).
    """
    artifact = tmp_path / "persona_answers.json"
    outcome = run_survey(
        personas=personas(1),
        pack=PACK,
        survey=WEB_SURVEY,
        client=RecordingClient(),
        artifact_path=artifact,
        user_template=_real_user_template(),
        system_template="Ты — зритель.",
    )

    assert [q["id"] for q in outcome.asked] == ["base-1", "base-6", "q-7"]
    assert [q["label"] for q in outcome.asked] == [q["label"] for q in WEB_SURVEY]

    saved = json.loads(artifact.read_text("utf-8"))
    assert saved["asked"] == outcome.asked, "артефакт не хранит заданные вопросы"


def test_asked_survives_total_model_failure(tmp_path: Path):
    """
    Список заданных вопросов есть и тогда, когда не ответил никто.

    Это единственный случай, когда он по-настоящему нужен: прогон без ответов
    надо уметь отличить от прогона без вопросов.
    """

    class Failing:
        def complete(self, *, system: str, user: str) -> str:
            raise TimeoutError("провайдер молчит")

    artifact = tmp_path / "persona_answers.json"
    outcome = run_survey(
        personas=personas(2), pack=PACK, survey=WEB_SURVEY, client=Failing(),
        artifact_path=artifact,
        user_template=_real_user_template(), system_template="Ты — зритель.",
    )

    assert outcome.answers == []
    assert outcome.failures == 2
    assert len(outcome.asked) == 3
    assert json.loads(artifact.read_text("utf-8"))["asked"]
