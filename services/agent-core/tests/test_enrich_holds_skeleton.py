"""
Промпт обогащения показывает модели те черты, которые она чаще всего опровергает.

─── Замер, из которого это следует ──────────────────────────────────────────
17.09.2026 прочитаны накопленные причины отбраковки персон на боевом
(`personas.validation`, 74 претензии к 27 персонам из 70). Половина — 38 из 74 —
это НАСТОЯЩИЕ противоречия: обогащение пишет текст, опровергающий собственный
скелет. Примеры дословно:

    'pacing_tolerance': 'медленный', а в тексте «предпочитая быстрые, короткие ролики»
    'directness': 'окольный', а в тексте «прямолинейно»
    возраст 25 (группа 25-34), в тексте «Девятнадцатилетняя»

Судья здесь прав, и лечить надо не его. Частота претензий по полям:

    length_tolerance 9, social_activity 8, attention_span 7, children 6,
    pacing_tolerance 5, education_level 5, directness 4, impulsivity 4,
    ad_response 3, streaming_frequency 3, tech_savviness 3 …

Против развёрнутых в промпте: age 5, important_values 3, work_status 2, hobbies 1.
На поле выходит 4.4 против 2.75 — разница в 1.6 раза, то есть зацепка, а не
доказательство: полей в первой группе просто больше. Но механизм при этом виден
и без статистики. Промпт разворачивает семь полей в «опорные признаки», а
остальные отдаёт одним `{{skeleton_json}}` — и тут же требует «покажи, как эти
черты выглядят в поведении», то есть ПЕРЕВЕСТИ атрибут в поступок. Перевод и
есть место, где черта переворачивается.

Запрета переворачивать в промпте не было вовсе: «Только факты из списка выше.
Не добавляй…» охраняет от ПРИБАВЛЕНИЯ, а не от ОПРОВЕРЖЕНИЯ.

─── Что проверяется ─────────────────────────────────────────────────────────
Не формулировки, а два свойства: часто опровергаемые группы показаны отдельно,
и запрет противоречить скелету в промпте есть. Формулировки — дело автора
промпта, и тест, прибитый к ним, покраснеет на первой же редактуре.
"""

from __future__ import annotations

from pathlib import Path

from agent_core.persona.enrich import render_prompt

CORE = Path(__file__).resolve().parents[1]
PROMPT = CORE.parents[1] / "prompts" / "persona.enrich.md"

#: Группы, по которым пришли претензии на боевом. Ключ — имя переменной промпта,
#: значение — поле DNA, из которого она собирается.
GROUPS = {
    "viewer_behavior": "viewer_behavior",
    "communication_style": "communication_style",
    "decision_making": "decision_making",
    # Добавлено 17.09.2026 вторым заходом. Первый развернул три группы и покрыл
    # 47 упоминаний из 78; остальные 31 остались видны модели только внутри
    # `skeleton_json`. Среди непокрытых оказалось ВТОРОЕ по частоте поле всего
    # списка — `social_activity` (8 претензий), плюс `education_level` (5),
    # `media_consumption` (2), `streaming_frequency` и `tech_savviness` (по 3).
    "lifestyle_and_interests": "lifestyle_and_interests",
    "technology_usage": "technology_usage",
}

#: Отдельные поля вне групп, по которым тоже приходили претензии.
#:
#: `children` — четвёртое по частоте (6 претензий). Лежит в `demographics`, где
#: развёрнуты возраст, пол, город и гео, а наличие детей не было.
SINGLE_FIELDS = ("children",)

PERSONA = {
    "demographics": {"age": 41, "gender": "жен", "city": "Казань",
                     "geo": "центры субъектов", "children": "Не указано"},
    "values_and_beliefs": {"important_values": ["Крепкая семья"]},
    "lifestyle_and_interests": {"hobbies": ["чтение"], "work_status": "работает",
                                "social_activity": "одиночка",
                                "media_consumption": "среднее",
                                "education_level": "среднее"},
    "viewer_behavior": {"pacing_tolerance": "медленный", "attention_span": "длинный",
                        "length_tolerance": "длинные", "violence_tolerance": "низкая",
                        "streaming_frequency": "раз в неделю"},
    "communication_style": {"verbosity": "лаконичный", "directness": "окольный",
                            "emotionality": "сдержанный"},
    "decision_making": {"impulsivity": 1, "ad_response": "доверие"},
    "technology_usage": {"streaming_frequency": "раз в неделю", "tech_savviness": 2},
}


def test_prompt_declares_the_single_fields():
    """Отдельные часто опровергаемые поля объявлены переменными."""
    text = PROMPT.read_text("utf-8")
    missing = [f for f in SINGLE_FIELDS if "{{" + f + "}}" not in text]
    assert not missing, f"в промпте нет переменных для полей: {', '.join(missing)}"


def test_prompt_declares_the_contradicted_groups():
    """Часто опровергаемые группы объявлены переменными, а не спрятаны в JSON."""
    text = PROMPT.read_text("utf-8")
    missing = [v for v in GROUPS if "{{" + v + "}}" not in text]
    assert not missing, (
        "в промпте нет переменных для групп, по которым пришла половина "
        f"претензий с боевого: {', '.join(missing)}"
    )


def test_prompt_forbids_contradicting_the_skeleton():
    """
    Запрет противоречить, а не только прибавлять.

    Прежний текст охранял лишь от выдумывания новых фактов; 38 из 74 претензий —
    про перевёрнутые существующие.
    """
    text = PROMPT.read_text("utf-8").lower()
    assert "противореч" in text, (
        "в требованиях нет запрета противоречить скелету — а именно это "
        "половина претензий судьи"
    )


def test_render_substitutes_the_groups():
    """Переменные не остаются в тексте и несут реальные значения персоны."""
    out = render_prompt(PROMPT.read_text("utf-8"), PERSONA)

    for name in GROUPS:
        assert "{{" + name + "}}" not in out, (
            f"переменная {name} не подставлена — уедет в модель фигурными скобками"
        )

    # Значения из тех самых полей, которые переворачивались на боевом.
    for value in ("медленный", "окольный", "длинный", "одиночка", "раз в неделю",
                  "Нет детей" if False else "Не указано"):
        assert value in out, f"значение «{value}» не доехало до промпта"


def test_skeleton_still_present():
    """
    Полный скелет остаётся.

    Развёрнутые поля ДОБАВЛЯЮТСЯ к нему, а не заменяют: комментарий
    `render_prompt` объясняет, что модель держится фактов лучше, когда видит их
    и списком, и в структуре. Замена оставила бы без опоры всё, что не попало в
    группы.
    """
    text = PROMPT.read_text("utf-8")
    assert "{{skeleton_json}}" in text
    out = render_prompt(text, PERSONA)
    assert "Казань" in out and "{{skeleton_json}}" not in out
