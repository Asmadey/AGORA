"""
Портрет сегмента подмешивается в narrative персоны.

─── Что было ─────────────────────────────────────────────────────────────────
Раздел «Портреты» был отключён от продукта целиком. `grep portrait` по
`agent_core/pipeline/` давал ноль попаданий. Тот `portrait_md`, что объявлен
переменной промпта `persona.generate`, собирается генератором на лету и никуда
не уходит, потому что `build_prompt_context` и `render_prompt` генератора не
вызывает никто. При этом реестр промптов утверждал: «Портрет потом
подмешивается в генерацию персон».

─── Куда подключено и почему именно туда ─────────────────────────────────────
В обогащение, а не в сэмплирование скелета — решение владельца. Скелет
(возраст, география, ценности) обязан остаться детерминированной выборкой из
долей корпуса: на этом держится метрика `persona_grounding`. Портрет влияет на
то, КАК персона описана, а не на то, кто она.

─── Ловушка, ради которой половина этих тестов ───────────────────────────────
`cache_key` хэширует ШАБЛОН. Подставь портрет после хэширования — и две персоны
с одинаковым скелетом из разных сегментов получат один кэшированный narrative,
собранный по чужому портрету. Причём выглядеть он будет совершенно нормально.
"""

from __future__ import annotations

from agent_core.persona.enrich import cache_key, render_prompt

TEMPLATE = "Опиши персону.\n{{portrait_md}}\nВозраст: {{age}}, город: {{city}}."

PERSONA = {
    "demographics": {"age": 30, "gender": "женский", "city": "Москва", "geo": "город-миллионник"},
    "values_and_beliefs": {"important_values": ["семья"]},
    "lifestyle_and_interests": {"hobbies": ["кино"], "work_status": "работает"},
}


def test_portrait_reaches_the_prompt():
    out = render_prompt(TEMPLATE, PERSONA, portrait_md="## Портрет 25-34\nСмотрят вечером.")
    assert "Смотрят вечером" in out, "портрет не доехал до промпта"


def test_slot_is_emptied_when_there_is_no_portrait():
    """
    Персона без подходящего портрета обогащается как раньше. Оставленный
    `{{portrait_md}}` уехал бы в модель буквально — она увидела бы фигурные
    скобки и приняла их за часть задания.
    """
    out = render_prompt(TEMPLATE, PERSONA)
    assert "{{portrait_md}}" not in out
    assert "Возраст: 30" in out


def test_template_without_the_slot_still_works():
    """
    Шаблон арендатора из Промпт-студии может не содержать слота вовсе. Это не
    повод ни падать, ни дописывать портрет куда попало.
    """
    out = render_prompt("Опиши персону {{age}} лет.", PERSONA, portrait_md="## Портрет")
    assert out == "Опиши персону 30 лет."


# ─── Кэш ─────────────────────────────────────────────────────────────────────

def test_portrait_changes_the_cache_key():
    skeleton = {"a": 1}
    without = cache_key(skeleton, TEMPLATE, "модель")
    with_a = cache_key(skeleton, TEMPLATE, "модель", portrait_md="## A")
    with_b = cache_key(skeleton, TEMPLATE, "модель", portrait_md="## B")

    assert with_a != without, "портрет не влияет на ключ — кэш отдаст чужой narrative"
    assert with_a != with_b, "разные портреты дают один ключ"


def test_same_portrait_gives_the_same_key():
    """Иначе кэш не сработает никогда и обогащение будет платным всегда."""
    skeleton = {"a": 1}
    assert cache_key(skeleton, TEMPLATE, "м", portrait_md="## A") == cache_key(
        skeleton, TEMPLATE, "м", portrait_md="## A"
    )


def test_no_portrait_key_matches_the_old_behaviour():
    """
    Ключ без портрета обязан остаться прежним: иначе весь накопленный кэш
    обесценится в день выкладки, и первый же прогон оплатит обогащение заново.
    """
    skeleton = {"a": 1}
    import hashlib
    import json

    h = hashlib.sha256()
    h.update(json.dumps(skeleton, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(TEMPLATE.encode("utf-8"))
    h.update("модель".encode())
    assert cache_key(skeleton, TEMPLATE, "модель") == h.hexdigest()


# ─── Сопоставление персоны с портретом ───────────────────────────────────────
#
# Ключ сегмента — тот же, что у дистилляции: `age_group|geo|gender`. Свой формат
# здесь означал бы, что портреты, собранные дистилляцией, не найдутся никогда, и
# заметить это можно было бы только по тому, что narrative не поменялся.

from agent_core.persona.portraits import portrait_for, segment_key_of  # noqa: E402


def _persona(age="25-34", geo="город-миллионник", gender="женский"):
    return {"demographics": {"age_group": age, "geo": geo, "gender": gender}}


def test_segment_key_matches_the_distillation_format():
    assert segment_key_of(_persona()) == "25-34|город-миллионник|женский"


def test_exact_segment_wins():
    portraits = {
        "25-34|город-миллионник|женский": "## точный",
        "25-34|город-миллионник|*": "## общий",
    }
    assert portrait_for(_persona(), portraits) == "## точный"


def test_broad_bucket_is_the_fallback():
    """
    Дистилляция сливает тонкие сегменты в `age|geo|*`. Не искать этот запасной
    ключ значило бы оставить без портрета ровно те сегменты, ради которых
    слияние и сделано.
    """
    portraits = {"25-34|город-миллионник|*": "## общий"}
    assert portrait_for(_persona(), portraits) == "## общий"


def test_no_match_is_empty_not_random():
    """
    Чужой портрет хуже отсутствующего: персона получит описание сегмента, к
    которому не принадлежит, и выглядеть это будет убедительно.
    """
    assert portrait_for(_persona(), {"55+|село|мужской": "## чужой"}) == ""
    assert portrait_for(_persona(), {}) == ""


def test_missing_demographics_do_not_crash():
    assert portrait_for({}, {"?|?|?": "## что-то"}) == "## что-то"
