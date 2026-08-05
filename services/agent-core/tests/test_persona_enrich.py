"""
Тесты обогащения персон моделью.

Все прогоняются без сети: клиент подменяется счётчиком. Проверяется не качество
текста — его нечем мерить в юнит-тесте, — а три свойства, на которых стоит
остальное: заземление не тронуто, кэш экономит вызовы, отказ модели не роняет
генерацию.
"""

from __future__ import annotations

import copy

import pytest

from agent_core.persona.enrich import (
    GROUNDED_FIELDS,
    MIN_NARRATIVE_LEN,
    EnrichResult,
    MemoryCache,
    cache_key,
    enrich_personas,
    render_prompt,
)

PROMPT = "Портрет для {{age}} лет, {{city}}. Не короче {{min_len}}. Факты: {{skeleton_json}}"

LONG_TEXT = (
    "Смотрит сериалы по вечерам, выбирает их по отзывам знакомых, а не по "
    "рекламе, и бросает на второй серии, если сюжет буксует. К новинкам "
    "относится с осторожностью и предпочитает то, что уже проверено другими."
)


def make_persona(age: int = 30, city: str = "Москва") -> dict:
    return {
        "demographics": {
            "gender": "мужской", "age": age, "age_group": "25-34",
            "geo": "город-миллионник", "city": city, "children": "Нет детей",
        },
        "big_five": {"openness": 4, "conscientiousness": 3, "extraversion": 2,
                     "agreeableness": 4, "neuroticism": 3},
        "values_and_beliefs": {"important_values": ["Семья", "Здоровье"],
                               "worldview": "прагматическая",
                               "political_orientation": "аполитичен",
                               "religious_attitude": "нерелигиозен"},
        "viewer_behavior": {"genres": ["драма"]},
        "communication_style": {"tone": "спокойный"},
        "decision_making": {"style": "взвешенный"},
        "technology_usage": {"devices": ["смартфон"]},
        "lifestyle_and_interests": {"hobbies": ["бег"], "work_status": "работает"},
        "narrative": (
            "Шаблонный портрет, собранный из полей персоны без участия модели. "
            "Длиннее ста символов — столько требует canonical JSON Schema (#4)."
        ),
        "seed": 42,
    }


class CountingClient:
    """Клиент-счётчик: считает вызовы и отдаёт заранее заданный текст."""

    def __init__(self, text: str = LONG_TEXT):
        self.text = text
        self.calls = 0
        self.prompts: list[str] = []

    def complete(self, *, prompt: str) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        return self.text


class FailingClient:
    def complete(self, *, prompt: str) -> str:
        raise RuntimeError("провайдер недоступен")


# ─── Заземление ──────────────────────────────────────────────────────────────


def test_grounded_fields_untouched():
    """Модель переписывает narrative и ничего кроме него.

    Это главный инвариант модуля: persona_grounding считается по этим полям, и
    если модель их правит, метрика начинает мерить смесь корпуса и модели.
    """
    persona = make_persona()
    before = copy.deepcopy(persona)

    result = enrich_personas([persona], client=CountingClient(), prompt=PROMPT)

    got = result.personas[0]
    for field in GROUNDED_FIELDS:
        assert got[field] == before[field], f"модель изменила заземлённое поле {field}"
    assert got["narrative"] == LONG_TEXT
    assert result.sources == ["model"]
    assert set(got) == set(before), "в DNA появился лишний ключ — схема закрыта"


def test_input_is_not_mutated():
    """Вход не портится: вызывающий вправе сравнить до и после."""
    persona = make_persona()
    before = copy.deepcopy(persona)
    enrich_personas([persona], client=CountingClient(), prompt=PROMPT)
    assert persona == before


# ─── Кэш ─────────────────────────────────────────────────────────────────────


def test_cache_prevents_second_call():
    """Повторный прогон тех же персон не платит второй раз (#30)."""
    cache = MemoryCache()
    client = CountingClient()

    first = enrich_personas([make_persona()], client=client, prompt=PROMPT, cache=cache)
    second = enrich_personas([make_persona()], client=client, prompt=PROMPT, cache=cache)

    assert first.calls_made == 1
    assert second.calls_made == 0
    assert second.cache_hits == 1
    assert first.personas[0]["narrative"] == second.personas[0]["narrative"]


def test_cache_key_ignores_narrative():
    """Ключ считается по скелету: шаблонный narrative на него не влияет.

    Иначе кэш не срабатывал бы никогда — шаблонный текст содержит имя, которое
    сэмплируется вместе с персоной.
    """
    a = make_persona()
    b = make_persona()
    b["narrative"] = (
        "Совершенно другой шаблонный текст, тоже длиннее ста символов — "
        "ровно столько требует canonical JSON Schema от поля narrative."
    )
    assert cache_key(
        {k: a[k] for k in GROUNDED_FIELDS}, PROMPT, "m",
    ) == cache_key({k: b[k] for k in GROUNDED_FIELDS}, PROMPT, "m")


def test_cache_key_changes_with_prompt_and_model():
    """Правка промпта в Студии (#26) и смена модели обесценивают кэш."""
    skel = {k: make_persona()[k] for k in GROUNDED_FIELDS}
    base = cache_key(skel, PROMPT, "qwen")
    assert cache_key(skel, PROMPT + " ещё требование", "qwen") != base
    assert cache_key(skel, PROMPT, "other-model") != base


def test_different_personas_do_not_share_cache():
    cache = MemoryCache()
    client = CountingClient()
    enrich_personas(
        [make_persona(age=30), make_persona(age=55)],
        client=client, prompt=PROMPT, cache=cache,
    )
    assert client.calls == 2


# ─── Деградация ──────────────────────────────────────────────────────────────


def test_provider_failure_keeps_personas():
    """Отказ провайдера не роняет генерацию и виден в результате."""
    result = enrich_personas([make_persona()], client=FailingClient(), prompt=PROMPT)

    assert len(result.personas) == 1
    assert result.sources == ["template"]
    assert result.enriched is False
    assert "провайдер недоступен" in (result.degraded_reason or "")


def test_short_answer_rejected():
    """Ответ короче схемного минимума не подменяет шаблонный портрет.

    canonical JSON Schema (#4) такую персону всё равно не примет; поймать это
    здесь дешевле, чем при сохранении в базу.
    """
    persona = make_persona()
    template = persona["narrative"]
    result = enrich_personas([persona], client=CountingClient("Коротко."), prompt=PROMPT)

    assert result.personas[0]["narrative"] == template
    assert result.sources == ["template"]
    assert len(template) >= MIN_NARRATIVE_LEN


def test_missing_prompt_degrades():
    result = enrich_personas([make_persona()], client=CountingClient(), prompt="")
    assert result.enriched is False
    assert result.personas[0]["narrative"] == make_persona()["narrative"]


def test_empty_input():
    result = enrich_personas([], client=CountingClient(), prompt=PROMPT)
    assert result.personas == []
    assert result.calls_made == 0


# ─── Промпт ──────────────────────────────────────────────────────────────────


def test_render_prompt_substitutes_facts():
    prompt = render_prompt(PROMPT, make_persona(age=41, city="Казань"))
    assert "41" in prompt
    assert "Казань" in prompt
    assert "{{" not in prompt, "остались неподставленные переменные"


def test_prompt_carries_no_narrative():
    """Шаблонный narrative в промпт не уходит: иначе модель его перескажет."""
    persona = make_persona()
    persona["narrative"] = "МАРКЕР-ШАБЛОНА"
    assert "МАРКЕР-ШАБЛОНА" not in render_prompt(PROMPT, persona)


@pytest.mark.parametrize("field", GROUNDED_FIELDS)
def test_prompt_survives_missing_field(field):
    """Персона без какого-то поля не роняет сборку промпта."""
    persona = make_persona()
    persona.pop(field, None)
    render_prompt(PROMPT, persona)


def test_result_defaults_are_not_shared():
    """Классический дефект dataclass: изменяемый дефолт на всех экземплярах."""
    a, b = EnrichResult(), EnrichResult()
    a.personas.append({"x": 1})
    assert b.personas == []
