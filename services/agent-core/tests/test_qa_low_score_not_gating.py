"""Низкая, но осознанная оценка информирует, а не исключает ответ."""

from __future__ import annotations

import json

from agent_core.analytics.aggregate import surviving
from agent_core.qa.run import run_qa


def _answer(*, score: int, retention: str) -> dict:
    return {
        "persona_id": "p-low",
        "replication": 0,
        "scores": {
            "overall_impression": score,
            "plot": score,
            "acting": score,
            "music": score,
            "cinematography": score,
        },
        "perception": {
            "retention_intent": retention,
            "recommendation_nps_1_to_10": score if 1 <= score <= 10 else 10,
        },
        "verbatims": {"why_impression": "Тема удерживает внимание, хотя исполнение слабое."},
        "grounding_refs": ["00:10 начало"],
    }


def _run(answer: dict) -> tuple[list[dict], list[dict]]:
    outcome = run_qa(answers=[answer], pack={"duration_sec": 100.0})
    return outcome.flagged, surviving([answer], outcome.flagged)


def test_low_score_flag_is_visible_but_answer_survives_aggregate():
    flagged, kept = _run(_answer(score=3, retention="досмотреть до конца"))

    consistency_flags = [flag for flag in flagged if flag["kind"] == "consistency"]
    assert consistency_flags, "оператор должен видеть информирующий флаг низкой оценки"
    assert any("намерении досмотреть" in reason for reason in consistency_flags[0]["reasons"])
    assert len(kept) == 1, f"ответов в агрегате {len(kept)}, ожидалось 1"
    assert consistency_flags[0]["source"] == "rule_informative"


def test_score_out_of_scale_still_removes_answer_from_aggregate():
    flagged, kept = _run(_answer(score=11, retention="досмотреть до конца"))

    consistency_flags = [flag for flag in flagged if flag["kind"] == "consistency"]
    assert consistency_flags
    assert consistency_flags[0]["source"] == "rule"
    assert any("вне шкалы" in reason for reason in consistency_flags[0]["reasons"])
    assert kept == []


def test_high_score_with_intent_to_stop_is_informative_too():
    flagged, kept = _run(_answer(score=8, retention="скорее выключить"))

    consistency_flags = [flag for flag in flagged if flag["kind"] == "consistency"]
    assert consistency_flags
    assert consistency_flags[0]["source"] == "rule_informative"
    assert any("намерении прекратить" in reason for reason in consistency_flags[0]["reasons"])
    assert len(kept) == 1


class _Judge:
    def complete(self, *, system: str, user: str, schema_key: str) -> str:
        return json.dumps({"verdict": "regenerate", "confidence": 0.9, "reasons": ["judge"]})


def test_informing_rule_flag_survives_judge_replacement():
    answer = _answer(score=3, retention="досмотреть до конца")
    outcome = run_qa(
        answers=[answer],
        pack={"duration_sec": 100.0},
        judge=_Judge(),
        templates={"qa.consistency": "{{persona_answer}}", "qa.grounding": "{{persona_answer}}"},
    )

    consistency_flags = [flag for flag in outcome.flagged if flag["kind"] == "consistency"]
    assert {flag["source"] for flag in consistency_flags} == {"rule_informative", "judge"}
    assert len(surviving([answer], outcome.flagged)) == 1
