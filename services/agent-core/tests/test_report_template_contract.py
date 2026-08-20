"""
Отчёт обязан сказать, что синтеза не было.

─── Что случилось ────────────────────────────────────────────────────────────
Переопределение промпта `analytics.report` у арендатора с 03.08.2026 выглядело
так — целиком:

    test {{content}}

Прогон 0051 отправил в модель 64 токена, получил `{"content": "test
{{content}}"}` и записал отчёт, в котором `narrative`, `themes`,
`disagreements`, `strengths`, `weaknesses` — пустые списки, `rationales` —
пустой словарь, а `degraded` — пустой СПИСОК. То есть отчёт сообщил: всё в
порядке, просто сказать нечего.

Числовая часть при этом посчиталась полностью и выглядела убедительно. Отличить
такой отчёт от честного «модель не нашла общих тем» по экрану было нельзя.

─── Что проверяем ────────────────────────────────────────────────────────────
Два признака негодного шаблона, каждый ловится отдельно:

1. В отрендеренном промпте остались `{{плейсхолдеры}}` — значит шаблон просит
   переменную, которой стадия не даёт, и модель получает фигурные скобки.
2. Модель ответила, ответ разобрался, и в нём нет ни одного поля синтеза.

Оба пишутся в `degraded`, а не роняют прогон: числовая часть отчёта от модели
не зависит и обязана доехать.
"""

from __future__ import annotations

import json

from agent_core.analytics.report import build_report

PACK = {"title": "материал", "scenes": []}

ANSWERS = [
    {
        "persona_id": "p1",
        "answer": {
            "scores": {"overall_impression": 7},
            "perception": {"recommendation_nps_1_to_10": 7, "watched_share_pct": 80},
            "verbatims": {"why_impression": "смотрится"},
        },
    }
]

GOOD_TEMPLATE = "Агрегат: {{aggregate}}. Ответы: {{all_persona_answers}}."


class Model:
    """Аналитик, который отвечает заданным JSON."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.seen: list[str] = []

    def complete(self, *, system: str, user: str) -> str:
        self.seen.append(user)
        return json.dumps(self.payload, ensure_ascii=False)


def test_empty_synthesis_is_named_in_degraded():
    """Модель ответила, но синтеза в ответе нет — отчёт обязан это сказать."""
    model = Model({"content": "test {{content}}"})

    report = build_report(
        answers=ANSWERS, pack=PACK, model=model, template=GOOD_TEMPLATE
    )

    assert report["narrative"] == []
    assert report["degraded"], "пустой синтез прошёл молча"
    assert any("синтез" in line.lower() for line in report["degraded"])


def test_unfilled_placeholders_are_named_in_degraded():
    """Шаблон просит переменную, которой стадия не даёт."""
    model = Model({"narrative": ["всё хорошо (0:10)"]})

    report = build_report(
        answers=ANSWERS, pack=PACK, model=model, template="test {{content}}"
    )

    assert report["degraded"], "негодный шаблон прошёл молча"
    joined = " ".join(report["degraded"])
    assert "content" in joined, joined


def test_a_working_template_stays_quiet():
    """
    Обратная сторона: исправный прогон не должен обрастать жалобами.

    Без этого проверка «в degraded что-то есть» зеленела бы всегда.
    """
    model = Model({
        "narrative": ["Персоны сошлись на напряжении (20:58)"],
        "themes": [{"name": "напряжение", "quotes": ["давит с первых минут"]}],
    })

    report = build_report(
        answers=ANSWERS, pack=PACK, model=model, template=GOOD_TEMPLATE
    )

    assert report["narrative"]
    assert report["degraded"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Миграция, снимающая уже сохранённые заглушки
# ─────────────────────────────────────────────────────────────────────────────
#
# Проверка контракта в промпт-студии закрывает дверь на будущее и не трогает то,
# что лежит в базе с августа. Строку снимает миграция 36 — и она обязана быть
# узкой: удаление лишнего здесь означает потерю авторской правки промпта, а её
# нигде больше нет.

import re  # noqa: E402
from pathlib import Path  # noqa: E402

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "infra" / "postgres" / "init" / "36_drop_stub_prompt_overrides.sql"
)


def _sql_without_comments() -> str:
    text = MIGRATION.read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))


def test_migration_exists():
    assert MIGRATION.exists(), "миграция 36 не заведена"


def test_migration_never_touches_defaults():
    """
    Дефолт — то, на что откатывается резолвер. Удалить его значит оставить
    стадию вообще без промпта.
    """
    sql = _sql_without_comments()
    assert "tenant_id IS NOT NULL" in sql
    assert re.search(r"DELETE\s+FROM\s+prompts", sql, re.IGNORECASE)
    # Единственный DELETE, и он по списку отобранных id, а не по ключу.
    assert len(re.findall(r"\bDELETE\b", sql, re.IGNORECASE)) == 1
    assert "IN (SELECT id FROM unusable)" in sql


def test_migration_keeps_overrides_that_use_at_least_one_variable():
    """
    Отбор идёт по «не использована НИ ОДНА переменная стадии». Условие «не все»
    удалило бы осмысленные правки, где владелец сознательно убрал одну.
    """
    sql = _sql_without_comments()
    assert "NOT EXISTS" in sql
    assert "cardinality(d.names) > 0" in sql
