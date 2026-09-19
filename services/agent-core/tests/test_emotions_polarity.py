"""Показатели «только положительные» и «только отрицательные» для вопроса 7."""
from __future__ import annotations

import json
import pathlib

from agent_core.analytics.survey_stats import survey_tally

REPO = pathlib.Path(__file__).resolve().parents[3]
SURVEY = json.loads(
    (REPO / "data" / "survey" / "customer_2026.json").read_text("utf-8")
)


def persona(pid: str, age: int) -> dict:
    return {
        "id": pid,
        "dna": {"demographics": {"age": age, "gender": "жен", "city": "Пермь"}},
    }


def answer(pid: str, value: str) -> dict:
    return {
        "persona_id": pid,
        "answer": {"survey_answers": {"q07-emotions": value}},
    }


def test_q07_reports_exclusive_emotion_polarity_from_survey_tally():
    """Только одна полярность считается от охвата, а не от ответивших."""
    answers = [
        answer("positive", "e-1, e-4"),
        answer("negative", "e-8, e-12"),
        answer("mixed", "e-2, e-9"),
        answer("service", "e-s1"),
        # У missing нет поля q07-emotions вовсе.
    ]
    personas = [
        persona("positive", 30),
        persona("negative", 30),
        persona("mixed", 40),
        persona("service", 40),
        persona("missing", 30),
    ]

    tally = survey_tally(SURVEY, answers, personas, min_segment=1)
    question = tally["questions"]["q07-emotions"]
    total = question["total"]
    target = question["target"]

    # Новые метрики живут рядом с долями вариантов, которые уже считает _choice.
    assert total["only_positive"] == 0.2
    assert total["only_negative"] == 0.2
    assert total["shares"]["e-1"] == 0.2
    assert total["shares"]["e-8"] == 0.2
    assert total["shares"]["e-s1"] == 0.2

    # В срез попали positive, negative и missing: пропуск остаётся в base.
    assert target["base"] == 3
    assert target["only_positive"] == round(1 / 3, 4)
    assert target["only_negative"] == round(1 / 3, 4)
    assert target["n"] == 2
