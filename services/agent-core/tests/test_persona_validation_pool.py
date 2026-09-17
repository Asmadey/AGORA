"""
Судье связности показывают реплики корпуса, а не пустоту.

─── Что было ─────────────────────────────────────────────────────────────────
`prompts/persona.validate.md` бракует персону по трём признакам, и второй из них
звучит так:

    **Досочинённый факт.** В тексте появилась биографическая подробность,
    которой нет ни в атрибутах, НИ В РЕПЛИКАХ КОРПУСА.

Реплики подставляются в раздел «## Реплики корпуса, из которого собрана персона»
из `{{verbatim_pool}}`. `validate_set` принимает пул необязательным параметром
(`verbatim_pool: list[str] | None = None`), и единственный продовый вызов —
`persona/tasks.py` — его НЕ ПЕРЕДАВАЛ. Раздел рендерился пустым при каждой
проверке: судью просили сверить текст с образцом, а образец не показывали.

Вторая половина того же противоречия — в соседнем промпте: `persona.enrich.md`
требует «одним абзацем, не короче {{min_len}} символов» от скелета из атрибутов,
то есть ОБЯЗЫВАЕТ модель добавить красок. Судья затем читает добавленное как
выдумку, потому что сверить не с чем.

Цена известна: на боевом наборе из 60 персон 30 не прошли с первого раза, трое
не прошли вовсе (см. `test_validation_first_verdict.py`). Каждое пересоздание —
новая генерация, новое обогащение и новая проверка.

─── Два уровня ───────────────────────────────────────────────────────────────
Статический разбирает исходник и работает где угодно. Поведенческий поднимает
продовый путь сборки аудитории и потому требует celery: на хосте его нет
намеренно — зависимости воркера живут в его образе (CLAUDE.md §9). Без среды он
уходит в SKIP, а не выдумывает результат.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from agent_core.persona.generator import CorpusDistribution
from agent_core.persona.validate import _render

CORE = Path(__file__).resolve().parents[1]
TASKS = CORE / "agent_core" / "persona" / "tasks.py"
PROMPT = CORE.parents[1] / "prompts" / "persona.validate.md"

#: Ярлык говорящего в стенограмме фокус-группы: «Женщина:», «Сергей:».
SPEAKER = re.compile(r"^\s*[А-ЯЁA-Z][а-яёa-z]+\s*:")


def _pool_section(prompt: str) -> str:
    """Текст между заголовком «Реплики корпуса» и следующим заголовком."""
    start = prompt.find("Реплики корпуса")
    assert start != -1, "в промпте судьи нет раздела с репликами корпуса"
    rest = prompt[start:]
    end = rest.find("\n## ", 1)
    return rest[:end] if end != -1 else rest


# ─── Статический уровень ─────────────────────────────────────────────────────


def test_production_call_passes_the_pool():
    """
    `tasks.py` передаёт `verbatim_pool` в `validate_set`.

    Разбор через `ast`, а не грепом: `verbatim_pool` встречается в файле и в
    комментарии, и в имени переменной, а нас интересует именно аргумент именно
    этого вызова.
    """
    tree = ast.parse(TASKS.read_text("utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_set"
    ]
    assert calls, "в tasks.py нет вызова validate_set — тест устарел"

    for call in calls:
        passed = {kw.arg for kw in call.keywords}
        assert "verbatim_pool" in passed, (
            f"validate_set вызван без verbatim_pool (строка {call.lineno}): судья "
            f"бракует за «досочинённый факт», сверяя с пустым разделом. "
            f"Передано: {sorted(n for n in passed if n)}"
        )


def test_prompt_still_references_the_pool():
    """
    Страховка от починки не с той стороны.

    Если из промпта уберут `{{verbatim_pool}}`, предыдущий тест останется зелёным,
    а судья снова будет сверять с пустотой — просто молча.
    """
    text = PROMPT.read_text("utf-8")
    assert "{{verbatim_pool}}" in text, "промпт судьи перестал подставлять реплики"
    assert "ни в репликах корпуса" in text, (
        "критерий «досочинённый факт» больше не ссылается на реплики — "
        "тогда и передавать их незачем, и этот тест надо пересмотреть"
    )


# ─── Уровень сборки пула ─────────────────────────────────────────────────────


def test_pool_has_no_speaker_labels():
    """
    Ярлык говорящего снят при сборке пула.

    Замер на корпусе: 60 % цитат начинаются с ярлыка стенограммы («Женщина:» 376,
    «Мужчина:» 207, «Сергей:» 51, «Оксана:» 23), 53 % — с гендерного. Показать их
    судье как «реплики корпуса» значит положить перед ним чужой пол и чужие имена
    в качестве образца речи персоны.
    """
    pool = CorpusDistribution.from_file().verbatims
    assert pool, "пул корпуса пуст — проверять нечего"

    offenders = [v[:60] for v in pool if SPEAKER.match(v)]
    assert not offenders, (
        f"в пуле {len(offenders)} из {len(pool)} реплик с ярлыком говорящего: "
        + "; ".join(offenders[:3])
    )


def test_render_fills_the_section():
    """Непустой пул доезжает до раздела промпта — звено между передачей и судьёй."""
    rendered = _render(
        PROMPT.read_text("utf-8"),
        {"demographics": {"age": 33}, "narrative": "Текст."},
        ["Сериал затянут, но смотрится.", "Музыка не подошла сцене."],
    )
    body = _pool_section(rendered).split("\n", 1)[1]
    assert "Сериал затянут" in body, f"реплики не подставлены: {body[:200]!r}"


# ─── Поведенческий уровень ───────────────────────────────────────────────────


def test_judge_actually_sees_corpus_lines(monkeypatch):
    """Промпт, доехавший до судьи в продовом пути, содержит реплики корпуса."""
    pytest.importorskip(
        "celery",
        reason="зависимости воркера живут в его образе (CLAUDE.md §9); "
        "прогон — в CI или в контейнере воркера",
    )
    import json
    from contextlib import nullcontext

    import psycopg

    from agent_core import db, tracing
    from agent_core.persona import enrich, tasks

    seen: list[str] = []

    class Judge:
        def __init__(self, **kwargs):
            self.validator = "response_schema" in kwargs

        def complete(self, *, prompt: str) -> str:
            if self.validator:
                seen.append(prompt)
                return json.dumps({"consistent": True, "confidence": 1.0, "issues": []})
            return "Описание проверяемой персоны. " * 20

    class Cursor:
        def execute(self, sql, params):  # noqa: ARG002
            return None

    monkeypatch.setenv("DATABASE_URL", "postgresql://test.invalid/test")
    monkeypatch.setattr(psycopg, "connect", lambda *a, **kw: nullcontext())
    monkeypatch.setattr(db, "tenant_scope", lambda *a: nullcontext(Cursor()))
    monkeypatch.setattr(tasks, "_update", lambda *a: None)
    monkeypatch.setattr(tasks, "_load_portraits", lambda *a: {})
    monkeypatch.setattr(tracing, "run", lambda **kw: nullcontext())
    monkeypatch.setattr(enrich, "QwenTextClient", Judge)

    result = tasks.generate_audience.run({
        "persona_set_id": "test-set",
        "tenant_id": "test-tenant",
        "config": {"size": 2, "seed": 7, "use_llm": True},
    })
    assert result["status"] == "ready", result
    assert seen, "судья не был вызван — тест не проверил ничего"

    for prompt in seen:
        body = _pool_section(prompt).split("\n", 1)[1]
        assert body.strip(), (
            "раздел «Реплики корпуса» пуст: судья бракует за «досочинённый факт», "
            "сверяя с образцом, которого ему не показали"
        )
        for line in body.splitlines():
            text = line.lstrip("—").strip()
            assert not (text and SPEAKER.match(text)), f"ярлык говорящего: {text[:60]}"
