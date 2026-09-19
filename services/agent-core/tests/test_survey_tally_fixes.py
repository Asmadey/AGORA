"""Регрессии расчёта анкеты, найденные ревью отчёта."""

from agent_core.analytics.survey_stats import survey_tally
from agent_core.pipeline import nodes


def _persona(persona_id: str, age: int = 30) -> dict:
    return {"id": persona_id, "dna": {"demographics": {"age": age}}}


def _answer(persona_id: str, value, replication: int = 0) -> dict:
    return {
        "persona_id": persona_id,
        "replication": replication,
        "answer": {"survey_answers": {"q": value}},
    }


def test_repeated_persona_is_one_respondent_in_survey_tally():
    question = {
        "id": "q",
        "type": "single_choice",
        "options": [{"id": "yes", "label": "Да"}, {"id": "no", "label": "Нет"}],
    }
    personas = [_persona("p0"), _persona("p1")]
    answers = [
        _answer("p0", "yes", 0),
        _answer("p0", "yes", 1),
        _answer("p1", "yes", 0),
        _answer("p1", "yes", 1),
    ]

    stats = survey_tally([question], answers, personas, min_segment=1)["questions"]["q"]["total"]

    assert stats["n"] == 2
    assert stats["base"] == 2
    assert stats["shares"]["yes"] == 1.0


def test_missing_persona_registry_is_reported_by_analytics(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    state = {
        "task_id": "survey-tally-fixes",
        "tenant_id": "tenant-survey-tally-fixes",
        "persona_ids": ["p0"],
        "persona_answers": [_answer("p0", 8)],
        "survey": {
            "questions": [
                {"id": "q", "number": 1, "type": "scale", "scaleMin": 0, "scaleMax": 10}
            ]
        },
    }

    update = nodes.analytics(state)

    assert any(message.startswith("analytics: персоны не прочитаны (")
               for message in update["degraded"])


def test_suppressed_slice_keeps_answered_count_separate_from_base():
    question = {"id": "q", "type": "scale", "scaleMin": 0, "scaleMax": 10}
    personas = [_persona(f"p{i}", age=20) for i in range(5)]
    answers = [_answer("p0", 8)]

    stats = survey_tally([question], answers, personas, min_segment=20)["questions"]["q"]["target"]

    assert stats["n"] == 1
    assert stats["base"] == 5
    assert stats["mean"] is None
    assert stats["below_threshold"] is True
