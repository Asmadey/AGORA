"""
Заголовок файла промпта — документация, а не инструкция модели.

─── Что видно в трассах ──────────────────────────────────────────────────────
Промпт судьи на прогоне 0051 начинается так:

    # qa.grounding (seed) — LLM-as-judge
    Переменные: {
      "scores": { "overall_impression": 7, ...

То есть строка «Переменные: {{persona_answer}}, {{video_understanding}}» —
служебная подпись формата, объясняющая ЧЕЛОВЕКУ, что подставляется, — тоже
проходит подстановку. Ответ персоны и понимание видео уезжают в модель ДВАЖДЫ:
один раз в перечне переменных, второй раз по месту.

Замерено по трассам прогона 0051:

    judge-answer    80 вызовов | 1 356 809 токенов | шапка ≈ 48 % → ~651 000
    answer-survey   27 вызовов |    36 702 каждый | шапка ≈ 48 % → ~476 000
    analyze-frame  233 вызова  |   458 667 токенов | шапка ≈  8 % →  ~37 000

Около 1,16 миллиона токенов из примерно 2,8 миллиона за прогон — то есть
**больше трети** — это повтор тех же данных под заголовком «Переменные».

Дело не только в цене. Модель получает весь разбираемый JSON первым, до
инструкций, в строке, которая по смыслу является подписью к формату. Это шум
ровно там, где промпт должен задавать рамку.

─── Где граница ──────────────────────────────────────────────────────────────
Формат файлов `prompts/*.md` — шапка, разделитель `---`, тело. Так его читает
промпт-студия (`loadPromptSource` в вебе делит по первому `\\n---\\n`). Воркер
делил не делил: и в снимок прогона, и в базу шаблон попал целиком.

Резать по разделителю безусловно нельзя: `---` бывает и внутри текста. Признак
именно служебной шапки — строка «Переменные:» до первого разделителя.
"""

from __future__ import annotations

from agent_core.prompt_text import body_of

SEED = """# qa.grounding (seed) — LLM-as-judge
Переменные: {{persona_answer}}, {{video_understanding}}.

---

Ты — верификатор. Верни JSON.
Ответ: {{persona_answer}}
"""


def test_header_with_variables_is_cut():
    body = body_of(SEED)
    assert "Переменные:" not in body
    assert body.startswith("Ты — верификатор")
    assert "{{persona_answer}}" in body, "тело промпта пострадало вместе с шапкой"


def test_cutting_is_idempotent():
    once = body_of(SEED)
    assert body_of(once) == once


def test_template_without_a_header_is_untouched():
    """Шаблон владельца из промпт-студии шапки не имеет и резать его нечего."""
    plain = "Ты аналитик. Дано: {{aggregate}}. Верни JSON."
    assert body_of(plain) == plain


def test_separator_inside_the_body_is_not_a_header():
    """
    Горизонтальная черта в тексте — не разделитель шапки.

    Без этой проверки правило «резать до первого ---» съело бы начало любого
    промпта, где автор поставил черту для читаемости.
    """
    text = "Ты — верификатор.\n\n---\n\nПравила ниже."
    assert body_of(text) == text


def test_empty_and_none_are_safe():
    assert body_of("") == ""
    assert body_of(None) == ""


def test_header_without_a_separator_is_left_alone():
    """
    Шапка без `---` неотличима от начала промпта. Резать по одной лишь строке
    «Переменные:» значило бы угадывать, где кончается документация.
    """
    text = "# что-то (seed)\nПеременные: {{a}}\nи сразу инструкция"
    assert body_of(text) == text


# ─────────────────────────────────────────────────────────────────────────────
# Шов
# ─────────────────────────────────────────────────────────────────────────────
#
# Сама по себе `body_of` ничего не решает: дефект был в том, что её никто не
# звал. Проверка идёт по исходникам — воспроизвести «забыли одно место» можно
# только живым прогоном с трассировкой, а мест пять.

import ast  # noqa: E402
from pathlib import Path  # noqa: E402

PKG = Path(__file__).resolve().parents[1] / "agent_core"

#: Файлы, которые читают шаблон промпта и обязаны снимать шапку.
READERS = (
    "pipeline/nodes.py",
    "respondent/run.py",
    "qa/judge.py",
    "analytics/report.py",
)


def test_every_prompt_reader_strips_the_header():
    for rel in READERS:
        source = (PKG / rel).read_text(encoding="utf-8")
        assert "body_of(" in source, (
            f"{rel} читает шаблон промпта и не снимает служебную шапку: "
            f"строка «Переменные: …» уедет в модель вместе с подставленными "
            f"значениями"
        )


def test_pipeline_prompt_returns_a_body():
    """
    Точка, через которую промпт попадает в прогон, — одна. Здесь проверяем не
    наличие вызова, а что оба возврата шаблона обёрнуты.
    """
    tree = ast.parse((PKG / "pipeline" / "nodes.py").read_text(encoding="utf-8"))
    fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_prompt"
    )
    returned_templates = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple)
    ]
    assert returned_templates, "у _prompt не нашлось возвратов шаблона"
    for node in returned_templates:
        first = node.value.elts[0]
        assert isinstance(first, ast.Call) and getattr(first.func, "id", "") == "body_of", (
            "_prompt возвращает шаблон без body_of — шапка доедет до модели"
        )
