"""Проверяет границу памяти родителя и текущих повторов задачи #30."""
from __future__ import annotations

from agent_core.pipeline.nodes import _merge_parent_answers, _new_questions_survey


def test_interrogation_keeps_only_questions_not_seen_by_parent() -> None:
    survey = {
        "questions": [
            {"id": "old", "label": "Старый вопрос", "type": "open"},
            {"id": "new", "label": "Новый вопрос", "type": "open"},
        ]
    }

    result = _new_questions_survey(survey, {"old"})

    assert [question["id"] for question in result["questions"]] == ["new"]
    assert [question["id"] for question in survey["questions"]] == ["old", "new"]


def test_clean_run_does_not_merge_parent_answers() -> None:
    current = [{"persona_id": "p1", "answer": {"new": "current"}}]

    assert _merge_parent_answers(current, None) == current


def test_interrogation_carries_old_values_without_overwriting_new_values() -> None:
    current = [{"persona_id": "p1", "answer": {"new": "current"}}]

    merged = _merge_parent_answers(
        current,
        {"p1": {"old": "parent", "new": "parent-copy"}},
    )

    assert merged[0]["answer"] == {"old": "parent", "new": "current"}
    assert current[0]["answer"] == {"new": "current"}
