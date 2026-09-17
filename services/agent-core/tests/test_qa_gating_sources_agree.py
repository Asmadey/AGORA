"""
Список гейтящих источников совпадает на обоих языках.

─── Зачем ────────────────────────────────────────────────────────────────────
С 17.09.2026 ответ выбывает из агрегата только по вердикту детерминированного
правила; вердикт судьи помечает карточку и не блокирует. Правило это записано
ДВАЖДЫ: `GATING_SOURCES` в `analytics/aggregate.py` считает агрегат, а
`GATING_QA_SOURCES` в `apps/web/lib/report-view.ts` — вклад в раскрытии «откуда
это число».

Разойдясь на одно значение, они дадут экран, где метрика посчитана по одному
числу ответов, а её расшифровка по другому. Заметит это только тот, кто сложит
числа руками.

Проверка появилась после ревью: комментарий в `report-view.ts` УЖЕ утверждал,
что списки держит тест, — а теста не было. Ложная уверенность в проверке хуже
её отсутствия: отсутствие видно.
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_core.analytics.aggregate import GATING_SOURCES

WEB = Path(__file__).resolve().parents[3] / "apps" / "web" / "lib" / "report-view.ts"


def ts_sources() -> set[str]:
    """Состав `GATING_QA_SOURCES` из TypeScript."""
    text = WEB.read_text("utf-8")
    m = re.search(
        r"GATING_QA_SOURCES\s*:\s*ReadonlySet<string>\s*=\s*new Set\(\[([^\]]*)\]\)",
        text,
    )
    assert m, "в report-view.ts не найдено объявление GATING_QA_SOURCES"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def test_lists_agree():
    assert ts_sources() == set(GATING_SOURCES), (
        f"составы разошлись: питон {sorted(GATING_SOURCES)}, "
        f"веб {sorted(ts_sources())}. Метрика и её расшифровка посчитаются по "
        f"разному числу ответов"
    )


def test_judge_is_not_gating():
    """
    Смысловая проверка, а не только совпадение.

    Два списка можно согласовать и одновременно вернуть блокировку по судье —
    совпадение это не поймает. Здесь закреплено само решение владельца.
    """
    assert "judge" not in GATING_SOURCES, "вердикт судьи снова блокирует ответ"
    assert "escalated" not in GATING_SOURCES, (
        "эскалация — тот же вердикт судьи, только модель побольше; "
        "субъективность от размера не исчезает"
    )
    assert "rule" in GATING_SOURCES, (
        "правила перестали гейтить — балл вне шкалы 1–10 попадёт в среднее"
    )
