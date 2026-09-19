"""Знаменатель долей анкеты - размер охвата, а не число ответов."""

from agent_core.analytics.aggregate import aggregate
from agent_core.analytics.survey_stats import survey_tally


def _persona(persona_id: str, age: int = 30) -> dict:
    return {"id": persona_id, "dna": {"demographics": {"age": age}}}


def _answer(persona_id: str, value) -> dict:
    return {
        "persona_id": persona_id,
        "replication": 0,
        "answer": {"survey_answers": {"q": value}},
    }


def _personas(count: int = 20) -> list[dict]:
    return [_persona(f"p{i}") for i in range(count)]


def test_choice_share_uses_scope_size():
    question = {
        "id": "q",
        "type": "single_choice",
        "options": [{"id": "yes", "label": "Да"}, {"id": "no", "label": "Нет"}],
    }
    answers = [_answer(f"p{i}", "yes") for i in range(8)]
    answers.extend(_answer(f"p{i}", "no") for i in range(8, 11))

    stats = survey_tally([question], answers, _personas())["questions"]["q"]["total"]

    assert stats["n"] == 11
    assert stats["base"] == 20
    assert stats["shares"]["yes"] == 0.4


def test_scale_shares_use_scope_size():
    question = {"id": "q", "type": "scale", "scaleMin": 0, "scaleMax": 10}
    values = [9] * 8 + [7] * 3
    answers = [_answer(f"p{i}", value) for i, value in enumerate(values)]

    stats = survey_tally([question], answers, _personas())["questions"]["q"]["total"]

    assert stats["top_box"] == 0.4
    assert stats["groups"] == {"9-10": 0.4, "7-8": 0.15, "0-6": 0.0}


def test_scale_mean_counts_only_answered():
    question = {"id": "q", "type": "scale", "scaleMin": 0, "scaleMax": 10}
    values = [10, 0] + [5] * 9
    answers = [_answer(f"p{i}", value) for i, value in enumerate(values)]

    stats = survey_tally([question], answers, _personas())["questions"]["q"]["total"]

    assert stats["n"] == 11
    assert stats["base"] == 20
    assert stats["mean"] == 5.0


def test_empty_scope_gives_null_not_zero():
    questions = [
        {
            "id": "choice",
            "type": "single_choice",
            "options": [{"id": "yes", "label": "Да"}],
        },
        {"id": "scale", "type": "scale", "scaleMin": 0, "scaleMax": 10},
    ]

    out = survey_tally(questions, [], [])
    choice = out["questions"]["choice"]["total"]
    scale = out["questions"]["scale"]["total"]

    assert choice["base"] == 0
    assert choice["shares"] is None
    assert scale["base"] == 0
    assert scale["top_box"] is None
    assert scale["groups"] is None


def test_survey_block_reports_real_excluded_count():
    question = {"id": "q", "type": "scale", "scaleMin": 0, "scaleMax": 10}
    answers = [_answer(f"p{i}", 5) for i in range(20)]
    flags = [
        {
            "persona_id": f"p{i}",
            "replication": 0,
            "verdict": "regenerate",
            "source": "rule",
        }
        for i in range(9)
    ]

    result = aggregate(
        answers,
        survey={"questions": [question]},
        qa_flags=flags,
        personas=_personas(),
    )

    assert result["survey"]["excluded_by_qa"] == 9
    assert result["survey"]["questions"]["q"]["total"]["n"] == 11
