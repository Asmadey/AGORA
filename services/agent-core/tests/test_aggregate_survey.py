"""Интеграция расчётов анкеты в боевой агрегат."""

from agent_core.analytics.aggregate import aggregate


def _answer(persona_id: str, score: int) -> dict:
    return {
        "persona_id": persona_id,
        "replication": 0,
        "answer": {"survey_answers": {"q-score": score}},
    }


def _survey() -> dict:
    return {
        "questions": [
            {
                "id": "q-score",
                "number": 1,
                "type": "scale",
                "scaleMin": 0,
                "scaleMax": 10,
            }
        ]
    }


def test_aggregate_puts_survey_tally_on_surviving_answers():
    answers = [_answer("p0", 10), _answer("p1", 0)]
    personas = [{"id": "p0"}, {"id": "p1"}]
    flags = [
        {
            "persona_id": "p1",
            "replication": 0,
            "verdict": "regenerate",
            "source": "rule",
        }
    ]

    result = aggregate(answers, survey=_survey(), qa_flags=flags, personas=personas)

    assert result["survey"]["questions"]["q-score"]["total"]["n"] == 1
    assert result["survey"]["questions"]["q-score"]["total"]["mean"] == 10.0


def test_aggregate_without_survey_keeps_working():
    result = aggregate([_answer("p0", 10)], personas=[{"id": "p0"}])

    assert result["survey"] is None
