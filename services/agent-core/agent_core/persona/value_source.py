"""Единый источник личных ценностей респондента."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

# Это заголовок ответа о собственных приоритетах респондента. В корпусе есть
# отдельный вопрос о замысле создателей, и его нельзя считать личной ценностью.
PERSONAL_VALUES_QUESTION = "Какие из перечисленных ценностей являются для Вас наиболее важными?"


def parse_value_answer(answer: Any) -> list[str]:
    """Возвращает ответ как одну выбранную опцию, не разрезая её по запятым.

    Варианты ответа сами могут содержать запятые. Каноническая проверка делается
    после этого шага, поэтому неканоническая опция остаётся одной строкой и не
    превращается в несколько фиктивных ценностей.
    """
    if not isinstance(answer, str):
        return []
    answer = answer.strip()
    return [answer] if answer else []


def personal_value_answer(record: Mapping[str, Any]) -> list[str]:
    """Извлекает ответ только из явно личного вопроса корпуса."""
    responses = record.get("all_survey_responses")
    if not isinstance(responses, Mapping):
        return []
    return parse_value_answer(responses.get(PERSONAL_VALUES_QUESTION))


def canonical_personal_values(
    record: Mapping[str, Any], canonical_values: Collection[str]
) -> list[str]:
    """Оставляет из личного ответа только опции канонического перечня."""
    allowed = set(canonical_values)
    return [value for value in personal_value_answer(record) if value in allowed]
