"""Регрессии, внесённые правкой повторов персон, — найдены третьим ревью."""

from agent_core.analytics.survey_stats import survey_tally
from agent_core.pipeline import nodes


def _persona(persona_id: str, age: int = 30) -> dict:
    return {"id": persona_id, "dna": {"demographics": {"age": age}}}


def _answer(persona_id: str, value, replication: int = 0) -> dict:
    return {
        "persona_id": persona_id,
        "replication": replication,
        "answer": {"survey_answers": {"q": value}},
        "scores": {"overall_impression": 8},
        "perception": {"retention_intent": "досмотреть до конца"},
        "verbatims": {"why_impression": "Смотрел из-за темы."},
        "grounding_refs": ["00:10 начало"],
    }


def test_qa_node_survives_unreadable_persona_registry(monkeypatch):
    """
    Нечитаемый реестр персон не имеет права ронять узел QA.

    Правка про повторы научила `_load_personas` бросать исключение вместо
    молчаливого пустого списка — и это верно для аналитики, где пустой список
    превращался в охват 0. Но узел QA зовёт ту же функцию БЕЗ обработки, а он
    стоит ПОСЛЕ оплаченных ответов персон: удалённая после старта персона или
    моргнувший Postgres обменивали бы расшифровку, разбор кадров и все ответы
    на исключение.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    state = {
        "task_id": "tally-round2-qa",
        "tenant_id": "tenant-tally-round2",
        "persona_ids": ["p0"],
        "persona_answers": [_answer("p0", 8)],
        "survey": {"questions": [{"id": "q", "number": 1, "type": "scale",
                                  "scaleMin": 0, "scaleMax": 10}]},
        "content_pack_compact": {"duration_sec": 100.0},
    }

    update = nodes.qa(state)

    assert any("персон" in message for message in update.get("degraded", [])), (
        f"отказ чтения реестра обязан попасть в degraded, а там: {update.get('degraded')}"
    )


def test_valid_replications_are_not_counted_as_excluded_by_qa():
    """
    Повтор — это не выбывший ответ.

    `excluded_by_qa` считается разностью «сколько пришло» и «сколько осталось»,
    а схлопывание повторов уменьшает второе число, ничего не исключая. На экране
    это читается как «из расчёта выбыло ответов по правилам проверки: 2» при
    полностью чистом прогоне — то есть продукт обвиняет себя в отбраковке,
    которой не было.
    """
    question = {"id": "q", "type": "single_choice",
                "options": [{"id": "yes", "label": "Да"}, {"id": "no", "label": "Нет"}]}
    personas = [_persona("p0"), _persona("p1")]
    answers = [
        _answer("p0", "yes", 0), _answer("p0", "yes", 1),
        _answer("p1", "yes", 0), _answer("p1", "yes", 1),
    ]

    tally = survey_tally([question], answers, personas, min_segment=1)

    assert tally["excluded_by_qa"] == 0, (
        f"выбывших по правилам {tally['excluded_by_qa']}, а QA не исключал ни одного"
    )


def test_mean_of_repeated_scores_does_not_round_into_top_box():
    """
    Округление среднего двигает верхнюю долю вверх само собой.

    Персона ответила 7 и 8. Среднее 7.5, порог верхней доли — 8. Округление до
    целого делает из неё 8, и человек попадает в долю «8–10», которой не
    заслужил. Ошибка систематическая и в одну сторону: именно её класс уже
    ловили в правиле QA, выбрасывавшем низкие оценки.
    """
    question = {"id": "q", "type": "scale", "scaleMin": 0, "scaleMax": 10}
    personas = [_persona("p0")]
    answers = [_answer("p0", 7, 0), _answer("p0", 8, 1)]

    stats = survey_tally([question], answers, personas, min_segment=1)["questions"]["q"]["total"]

    assert stats["top_box"] == 0.0, (
        f"верхняя доля {stats['top_box']}, а среднее ответов 7.5 в неё не входит"
    )
