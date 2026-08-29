"""
Что видит собеседник: срез данных для аналитика и для персоны.

─── Изоляция здесь механизм, а не проверка ──────────────────────────────────
Персона не «просит не подглядывать» — ей нечего показать. В срез попадают её
профиль, материал, анкета и ЕЁ прежние ответы; чужие ответы в структуру не
кладутся вовсе. Тот же приём, что в `respondent.run.build_slice`, и та же
причина: проверка вывода зелена ровно до первого совпадения формулировок.

─── Почему персона не знает об отчёте ───────────────────────────────────────
Она зритель, а не участник исследования. Агрегат, темы и чужие оценки ей знать
неоткуда, а знание превратило бы ответ в подстройку под уже посчитанный итог —
то есть в то самое соглашательство, против которого написан весь промпт.

─── Про объём ───────────────────────────────────────────────────────────────
Аналитик получает ВСЕ ответы этого исследования, без выборок. Размер продукта
это допускает: потолок аудитории — 100 персон (`AUDIENCE_SIZE_BOUNDS`), самый
большой боевой набор дал 231 КБ ответов. Урезать то, что влезает, значит
отвечать по части данных и не иметь способа об этом сказать.
"""

from __future__ import annotations

import copy
from typing import Any


def _own_answers(answers: list[dict[str, Any]], persona_id: str) -> list[dict[str, Any]]:
    """Ответы одной персоны. Копия: срез не вправе менять то, из чего собран."""
    return [
        copy.deepcopy(a)
        for a in answers
        if str(a.get("persona_id") or a.get("personaId") or "") == str(persona_id)
    ]


def persona_context(
    *,
    persona: dict[str, Any],
    pack: dict[str, Any],
    survey: Any,
    answers: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Срез для допроса персоны. Чужих ответов здесь нет как данных."""
    return {
        "persona_dna": copy.deepcopy(persona.get("dna") or {}),
        "video_understanding": copy.deepcopy(pack),
        "survey": copy.deepcopy(survey),
        "my_previous_answers": _own_answers(answers, str(persona.get("id") or "")),
        "chat_history": copy.deepcopy(history),
    }


def analyst_context(
    *,
    report: dict[str, Any],
    pack: dict[str, Any],
    survey: Any,
    answers: list[dict[str, Any]],
    qa_flags: list[dict[str, Any]] | None,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Срез для аналитика: отчёт и все ответы этого исследования."""
    return {
        "report": copy.deepcopy(report),
        "all_persona_answers": copy.deepcopy(answers),
        "video_understanding": copy.deepcopy(pack),
        "survey": copy.deepcopy(survey),
        "qa_flags": copy.deepcopy(qa_flags or []),
        "chat_history": copy.deepcopy(history),
    }
