"""Наблюдаемые ворота лестницы проверки персоны.

Тесты смотрят на аргументы обратных вызовов и на итоговую персону. Сам факт
вызова внутренней функции не доказывает, что скелет и текст действительно
разошлись так, как ожидает пользователь.
"""

from __future__ import annotations

import json

from agent_core.persona.enrich import MemoryCache, enrich_personas
from agent_core.persona.validate import MAX_ATTEMPTS, validate_set
from agent_core.schemas.responses import PERSONA_VALIDATION, assert_strict

TEMPLATE = "{{skeleton_json}} {{narrative}} {{verbatim_pool}}"
SKELETON = {
    "demographics": {"age_group": "25-34", "geo": "Москва"},
    "viewer_behavior": {"watch_frequency": "ежедневно"},
    "narrative": "Исходный портрет.",
    "seed": 17,
}


def _answer(issues: list[dict[str, str]], *, confidence: float = 0.95) -> str:
    return json.dumps(
        {"consistent": not issues, "issues": issues, "confidence": confidence},
        ensure_ascii=False,
    )


def _issue(kind: str, severity: str = "hard") -> dict[str, str]:
    return {"kind": kind, "severity": severity, "message": f"{kind}: исправить"}


class Judge:
    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def complete(self, *, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0)


def test_hard_text_issue_reenriches_before_regeneration() -> None:
    judge = Judge(
        _answer([_issue("contradiction")]),
        _answer([], confidence=0.95),
    )
    reenrich_calls: list[tuple[int, list[dict[str, str]]]] = []
    regenerate_calls: list[tuple[int, int]] = []

    def reenrich(index: int, issues: list[dict[str, str]]) -> dict:
        reenrich_calls.append((index, issues))
        return {**SKELETON, "narrative": "Исправленный портрет."}

    outcome = validate_set(
        [dict(SKELETON)],
        client=judge,
        reenrich=reenrich,
        regenerate=lambda index, attempt: regenerate_calls.append((index, attempt)) or None,
        template=TEMPLATE,
    )

    assert reenrich_calls == [(0, [_issue("contradiction")])]
    assert regenerate_calls == []
    assert outcome.personas[0]["narrative"] == "Исправленный портрет."
    assert outcome.personas[0]["seed"] == SKELETON["seed"]
    assert outcome.personas[0]["demographics"] == SKELETON["demographics"]
    assert outcome.reenriched == 1


def test_attribute_conflict_is_recorded_without_either_recovery() -> None:
    judge = Judge(_answer([_issue("attribute_conflict")]))
    reenrich_calls: list[object] = []
    regenerate_calls: list[object] = []

    outcome = validate_set(
        [dict(SKELETON)],
        client=judge,
        reenrich=lambda index, issues: reenrich_calls.append((index, issues)) or None,
        regenerate=lambda index, attempt: regenerate_calls.append((index, attempt)) or None,
        template=TEMPLATE,
    )

    assert reenrich_calls == []
    assert regenerate_calls == []
    assert outcome.personas == [SKELETON]
    assert outcome.attribute_conflicts == 1
    assert outcome.failed == 0
    assert outcome.verdicts[0].issues[0]["kind"] == "attribute_conflict"


def test_soft_text_issue_is_accepted() -> None:
    judge = Judge(_answer([_issue("impersonal", "soft")]))
    calls: list[object] = []

    outcome = validate_set(
        [dict(SKELETON)],
        client=judge,
        reenrich=lambda index, issues: calls.append((index, issues)) or None,
        regenerate=lambda index, attempt: calls.append((index, attempt)) or None,
        template=TEMPLATE,
    )

    assert calls == []
    assert outcome.failed == 0
    assert outcome.personas == [SKELETON]


def test_new_seed_is_last_resort_after_reenrichment_attempts() -> None:
    hard = _answer([_issue("invented")])
    judge = Judge(*([hard] * (MAX_ATTEMPTS + 1) + [_answer([], confidence=0.95)]))
    reenrich_calls: list[tuple[int, int]] = []
    regenerate_calls: list[tuple[int, int]] = []

    def reenrich(index: int, issues: list[dict[str, str]]) -> dict:
        reenrich_calls.append((index, len(issues)))
        return {**SKELETON, "narrative": f"Переписан {len(reenrich_calls)}."}

    def regenerate(index: int, attempt: int) -> dict:
        regenerate_calls.append((index, attempt))
        return {**SKELETON, "seed": 999, "narrative": "Новый seed."}

    outcome = validate_set(
        [dict(SKELETON)],
        client=judge,
        reenrich=reenrich,
        regenerate=regenerate,
        template=TEMPLATE,
        max_attempts=MAX_ATTEMPTS,
    )

    assert len(reenrich_calls) == MAX_ATTEMPTS
    assert regenerate_calls == [(0, 1)]
    assert outcome.personas[0]["seed"] == 999


def test_revision_enrichment_bypasses_stale_cache_and_keeps_skeleton() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls = 0
            self.prompts: list[str] = []

        def complete(self, *, prompt: str) -> str:
            self.calls += 1
            self.prompts.append(prompt)
            return f"Портрет редакции {self.calls}. " + ("Текст. " * 20)

    client = Client()
    cache = MemoryCache()
    issues = [_issue("contradiction")]
    original = enrich_personas(
        [dict(SKELETON)],
        client=client,
        prompt="Опиши {{skeleton_json}}",
        cache=cache,
        model="test",
        names=["Наталья"],
    )
    first = enrich_personas(
        [dict(SKELETON)],
        client=client,
        prompt="Опиши {{skeleton_json}}",
        cache=cache,
        model="test",
        names=["Наталья"],
        revision_issues=issues,
    )
    second = enrich_personas(
        [dict(SKELETON)],
        client=client,
        prompt="Опиши {{skeleton_json}}",
        cache=cache,
        model="test",
        names=["Наталья"],
        revision_issues=issues,
    )

    assert client.calls == 3
    assert all("Что исправить в текущем портрете" in prompt for prompt in client.prompts[1:])
    assert all("contradiction" in prompt for prompt in client.prompts[1:])
    assert original.personas[0]["narrative"] != first.personas[0]["narrative"]
    assert first.personas[0]["narrative"] != second.personas[0]["narrative"]
    assert first.personas[0]["seed"] == second.personas[0]["seed"] == SKELETON["seed"]
    assert first.personas[0]["demographics"] == second.personas[0]["demographics"]


def test_validation_schema_is_strict_and_typed() -> None:
    assert_strict(PERSONA_VALIDATION)
    issue = PERSONA_VALIDATION["properties"]["issues"]["items"]
    assert set(issue["properties"]) >= {"kind", "severity"}
    assert issue["properties"]["kind"]["enum"] == [
        "contradiction",
        "invented",
        "impersonal",
        "attribute_conflict",
    ]
    assert issue["properties"]["severity"]["enum"] == ["hard", "soft"]
