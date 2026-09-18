"""
Портрет пишется про ту персону, которую потом так и назовут.

─── Что было ────────────────────────────────────────────────────────────────
Персона «Наталья», seed 272743267, а в её портрете: «Анна, 41-летняя жительница
Санкт-Петербурга…». Замер по набору 170c318c:

    персон в наборе                                    20
    портретов, содержащих собственное имя персоны       0
    портретов с ЧУЖИМ именем                            5

Пятнадцать выкрутились безымянно («Ей 30 лет…», «Жительница Москвы, 39 лет…»),
пять назвали — и все пять назвали чужое имя. Своё не назвал никто, и это не
невезение: имени у модели не было.

`generate_named` возвращает пары «имя, DNA», но дальше по конвейеру едет только
DNA. Имена лежат отдельным списком и соединяются с персонами лишь при записи в
базу — `zip(names, personas)`. Портрет пишется без имени, судья проверяет
портрет тоже без имени, и сверить их не с чем.

Докстринг `generate_named` описывает, где это разошлось: раньше имя
«подставлялось в narrative и выбрасывалось», потом его сохранили в колонку — а
до генератора портрета оно так и не доехало.

Решение владельца 18.09.2026: передавать имя в промпт `persona.enrich`, а не
приклеивать в конце.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.persona.enrich import (  # noqa: E402
    MIN_NARRATIVE_LEN,
    cache_key,
    enrich_personas,
    foreign_name,
    render_prompt,
)

SKELETON = {
    "demographics": {"age": 41, "gender": "жен", "city": "Санкт-Петербург",
                     "geo": "столицы", "children": "нет"},
    "values_and_beliefs": {"important_values": ["Крепкая семья"], "worldview": "консервативная",
                           "political_orientation": "аполитичен", "religious_attitude": "атеист"},
    "lifestyle_and_interests": {"hobbies": ["рукоделие"], "work_status": "работает"},
    "viewer_behavior": {"attention_span": "средний"},
    "communication_style": {"directness": "окольный"},
    "decision_making": {"impulsivity": 2},
    "technology_usage": {"tech_savviness": 3},
    "big_five": {"openness": 4},
    "narrative": "",
    "seed": 272743267,
}

TEMPLATE = (
    "# persona.enrich (narrative)\n"
    "Переменные: {{skeleton_json}}, {{name}}, {{age}}.\n"
    "---\n"
    "Персону зовут {{name}}. Ей {{age}} лет.\n"
    "{{skeleton_json}}\n"
)


class _Client:
    """Отдаёт портрет, который ей продиктовали, и запоминает промпт."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: list[str] = []

    def complete(self, *, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.text


def _long(text: str) -> str:
    return text + " " + "и так далее, " * 40


def test_name_reaches_the_prompt() -> None:
    rendered = render_prompt(TEMPLATE, SKELETON, name="Наталья")
    assert "Персону зовут Наталья" in rendered
    assert "{{name}}" not in rendered, "незаполненный плейсхолдер уедет в модель буквально"


def test_enrichment_passes_each_name_to_its_persona() -> None:
    client = _Client(_long("Наталья, 41 год, живёт в Санкт-Петербурге."))
    enrich_personas(
        [SKELETON, SKELETON],
        names=["Наталья", "Ирина"],
        client=client,
        prompt=TEMPLATE,
        model="test",
    )
    assert len(client.prompts) == 2
    assert "Персону зовут Наталья" in client.prompts[0]
    assert "Персону зовут Ирина" in client.prompts[1], (
        "вторая персона получила чужое имя — ровно то расхождение, что чинится"
    )


def test_cache_does_not_hand_over_someone_elses_name() -> None:
    """
    Имя входит в ключ кэша.

    Скелет у двух персон может совпасть до последнего поля — различаются они
    именем. Ключ без имени отдал бы второй персоне портрет первой, где стоит
    первое имя, и выглядел бы такой портрет совершенно нормально. Тот же довод,
    по которому в ключ уже входит портрет сегмента.
    """
    a = cache_key(SKELETON, TEMPLATE, "test", name="Наталья")
    b = cache_key(SKELETON, TEMPLATE, "test", name="Ирина")
    assert a != b


def test_portrait_with_a_foreign_name_is_not_kept() -> None:
    """
    Чужое имя в портрете — тот же класс отказа, что и слишком короткий текст:
    портрет не годится, персона остаётся с шаблонным narrative.

    Гейтит детерминированное правило, а не судья: имя либо совпадает, либо нет,
    и мнение здесь ни при чём (политика владельца 17.09.2026).
    """
    client = _Client(_long("Анна, 41-летняя жительница Санкт-Петербурга."))
    result = enrich_personas(
        [SKELETON], names=["Наталья"], client=client, prompt=TEMPLATE, model="test"
    )
    assert result.sources == ["template"]
    assert "Анна" not in (result.personas[0].get("narrative") or "")


def test_portrait_without_any_name_is_fine() -> None:
    """Безымянный портрет ничему не противоречит и остаётся как есть."""
    text = _long("Ей 41 год, она живёт в Санкт-Петербурге и работает.")
    client = _Client(text)
    result = enrich_personas(
        [SKELETON], names=["Наталья"], client=client, prompt=TEMPLATE, model="test"
    )
    assert result.sources == ["model"]
    assert result.personas[0]["narrative"] == text


def test_foreign_name_rule_is_about_the_pool_not_any_capital_word() -> None:
    """
    Правило смотрит на пул имён генератора, а не на любое слово с заглавной.

    «Санкт-Петербург» и «Smart-TV» — не имена, и портрет, где они есть, годный.
    Своё имя тоже не чужое, сколько бы раз оно ни встретилось.
    """
    assert foreign_name("Наталья", "Анна, 41-летняя жительница Санкт-Петербурга") == "Анна"
    assert foreign_name("Наталья", "Наталья живёт в Санкт-Петербурге") is None
    assert foreign_name("Наталья", "Ей 41 год, смотрит Smart-TV") is None
    assert foreign_name("Дмитрий", "Алексей, 39 лет, живёт в Москве") == "Алексей"


def test_min_length_still_gates() -> None:
    """Правка не отменяет прежнюю проверку длины."""
    client = _Client("Наталья.")
    result = enrich_personas(
        [SKELETON], names=["Наталья"], client=client, prompt=TEMPLATE, model="test"
    )
    assert len(client.prompts) == 1
    assert result.sources == ["template"]
    assert MIN_NARRATIVE_LEN > len("Наталья.")
