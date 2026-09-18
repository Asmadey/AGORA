"""Регрессия источника личных ценностей корпуса."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from agent_core.persona.generator import CorpusDistribution
from agent_core.persona.value_source import parse_value_answer, personal_value_answer

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "data" / "grounding" / "unified_respondent_sessions.json"
CANON = json.loads(
    (ROOT / "data" / "values" / "traditional_values.json").read_text("utf-8")
)["values"]
PERSONAL_QUESTION = "Какие из перечисленных ценностей являются для Вас наиболее важными?"
CREATOR_QUESTION = (
    "Какие из перечисленных ценностей, по Вашему мнению, пытались донести "
    "создатели сериала?"
)


EXPECTED_COUNTS = {
    "Жизнь": 3,
    "Достоинство": 1,
    "Права и свободы человека": 2,
    "Патриотизм": 1,
    "Гражданственность": 1,
    "Служение Отечеству и ответственность за его судьбу": 0,
    "Высокие нравственные идеалы": 1,
    "Крепкая семья": 5,
    "Созидательный труд": 0,
    "Приоритет духовного над материальным": 1,
    "Гуманизм": 1,
    "Милосердие": 1,
    "Справедливость": 1,
    "Коллективизм": 0,
    "Взаимопомощь и взаимоуважение": 1,
    "Историческая память и преемственность поколений": 2,
    "Единство народов России": 0,
}


def _records() -> list[dict]:
    return json.loads(CORPUS.read_text("utf-8"))


def test_personal_answer_counts() -> None:
    distribution = CorpusDistribution.from_corpus(_records())

    assert distribution.value_counts == EXPECTED_COUNTS
    assert sum(distribution.value_counts.values()) == 21
    assert list(distribution.value_counts) == [value for value in CANON if value in EXPECTED_COUNTS]


def test_personal_answer_source() -> None:
    record = copy.deepcopy(_records()[0])
    record["psychographics_and_values"]["important_values"] = ["Крепкая семья"]
    record["all_survey_responses"] = {
        CREATOR_QUESTION: "Крепкая семья",
    }

    distribution = CorpusDistribution.from_corpus([record])
    zero_counts = {value: 0 for value in CANON}
    assert distribution.value_counts == zero_counts

    record["all_survey_responses"] = {
        PERSONAL_QUESTION: "Стремление к новым знаниям, открытиям, трендам",
    }
    distribution = CorpusDistribution.from_corpus([record])
    assert distribution.value_counts == zero_counts
    assert all(
        value in CANON for value in distribution.value_counts
    ), distribution.value_counts
    assert parse_value_answer("Стремление к новым знаниям, открытиям, трендам") == [
        "Стремление к новым знаниям, открытиям, трендам"
    ]
    assert personal_value_answer(record) == [
        "Стремление к новым знаниям, открытиям, трендам"
    ]


def test_personal_answer_source_readers() -> None:
    """Корпусные читатели используют общий личный источник, а не DNA-поле."""
    from agent_core.matching import finder
    from agent_core.persona import generator
    from agent_core.portraits import distill

    source = generator.PERSONAL_VALUES_QUESTION
    assert source == PERSONAL_QUESTION

    record = copy.deepcopy(_records()[0])
    record["psychographics_and_values"]["important_values"] = ["Крепкая семья"]
    record["all_survey_responses"] = {PERSONAL_QUESTION: "Жизнь"}
    assert finder._values_overlap(
        {"values_and_beliefs": {"important_values": ["Жизнь"]}}, record
    ) == 1.0
    assert distill._collect_values([record]) == {"Жизнь": 1}
