"""
Шкала базовых критериев объявлена в четырёх местах. Они обязаны совпадать.

─── Почему это отдельный тест ───────────────────────────────────────────────
17.09.2026 владелец решил: базовые критерии живут на шкале 0–10. Решение
доехало до конструктора и до данных анкеты — и не доехало до промпта и до
правила согласованности. Получилось так:

    промпт просит          "overall_impression": <1..10>
    правило QA требует     1 <= value <= 10
    анкета объявляет       scaleMin: 0, scaleMax: 10

Персона, поставившая ноль, выполняла анкету и нарушала промпт, а правило
браковало её ответ — с пометкой `source: "rule"`, то есть с выбыванием из
агрегата. Систематически выбывали бы только САМЫЕ НИЗКИЕ оценки, и средний
балл отчёта полз бы вверх сам собой. Заметить это по отчёту невозможно: он
выглядит нормальным отчётом с хорошими оценками.

Дефект нашёл независимый ревьюер прямым запуском, а не чтением: по отдельности
каждый из четырёх файлов выглядит исправным.

─── Что здесь проверяется ───────────────────────────────────────────────────
Не «шкала правильная», а «все четверо говорят одно». Правильность — решение
владельца, и оно записано в одном месте: `BASE_SCALE_MIN`/`BASE_SCALE_MAX` в
`survey-validator.ts`. Остальные три сверяются с ним.
"""
from __future__ import annotations

import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[3]
VALIDATOR = REPO / "apps" / "web" / "lib" / "server" / "survey-validator.ts"
PROMPT = REPO / "prompts" / "respondent.user.md"
SURVEY = REPO / "data" / "survey" / "customer_2026.json"


def _declared() -> tuple[int, int]:
    """Источник истины — константы валидатора."""
    text = VALIDATOR.read_text("utf-8")
    low = re.search(r"export const BASE_SCALE_MIN\s*=\s*(-?\d+)", text)
    high = re.search(r"export const BASE_SCALE_MAX\s*=\s*(-?\d+)", text)
    assert low and high, "в survey-validator.ts нет BASE_SCALE_MIN/BASE_SCALE_MAX"
    return int(low.group(1)), int(high.group(1))


def test_правило_qa_знает_ту_же_шкалу():
    from agent_core.qa.checks import DEFAULT_SCORE_MAX, DEFAULT_SCORE_MIN

    assert (DEFAULT_SCORE_MIN, DEFAULT_SCORE_MAX) == _declared()


def test_промпт_просит_ту_же_шкалу():
    """
    Промпт — единственная сторона, которую нельзя проверить исполнением: он
    всего лишь текст, и разойтись может молча.
    """
    low, high = _declared()
    text = PROMPT.read_text("utf-8")
    for key in ("overall_impression", "plot", "acting", "music", "cinematography"):
        assert f'"{key}": <{low}..{high}>' in text, (
            f"промпт просит у критерия {key} не шкалу {low}..{high}"
        )
    assert re.search(rf"Баллы {low}–{high} целые", text), (
        f"правило в промпте называет не шкалу {low}–{high}"
    )


def test_анкета_заказчика_на_той_же_шкале():
    low, high = _declared()
    doc = json.loads(SURVEY.read_text("utf-8"))
    base = [q for q in doc["questions"] if q.get("baseKey")]
    assert base, "в анкете заказчика нет базовых критериев"
    for q in base:
        assert (q.get("scaleMin"), q.get("scaleMax")) == (low, high), (
            f"{q['id']}: шкала {q.get('scaleMin')}–{q.get('scaleMax')}, "
            f"а объявлена {low}–{high}"
        )
