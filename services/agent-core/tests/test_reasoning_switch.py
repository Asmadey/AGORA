"""
Режим размышления выключен во всех обращениях к модели.

─── Замер, ради которого это сделано ────────────────────────────────────────
`Qwen3.6-35B-A3B` — думающая модель: рассуждение уходит в поле `reasoning`, а
`content` пуст, пока оно не закончится. На одном и том же запросе
(«верни JSON с оценкой»):

    базовый                      6.5 с   600 токенов (упёрся в лимит)   content ПУСТ
    enable_thinking: false       0.4 с    16 токенов                    content есть
    reasoning_effort: "none"     0.6 с     7 токенов                    content есть

Двенадцать персон плюс судья по каждой плюс аналитика — и прогон занимал 23
минуты вместо десяти по критерию приёмки #22. Рассуждение здесь не улучшает
ответ: персона отвечает впечатлением, а не выводом, разбор кадра — это описание
увиденного, и в обоих случаях модель тратит сотни токенов на проговаривание
задачи самой себе.

─── Почему это ещё и вопрос надёжности ──────────────────────────────────────
Когда рассуждение упирается в лимит токенов, `content` приходит `null`. Код
повсеместно пишет `(response.choices[0].message.content or "").strip()`, то
есть превращает `null` в пустую строку молча — ответ выглядит как «модель
ничего не сказала», а не как «бюджет съеден рассуждением». Выключенное
размышление убирает саму возможность такого отказа.

─── Почему проверка статическая ─────────────────────────────────────────────
Клиентов шесть, и они написаны в разное время в разных модулях. Проверить
поведением можно один, а забыть — любой из остальных: пропущенный клиент не
сломает ничего заметного, он просто будет в двенадцать раз медленнее и иногда
молча пустым. Поэтому здесь разбирается исходник: каждый вызов
`chat.completions.create` обязан нести выключатель.

`thinking: false` из документации провайдера этот шлюз ИГНОРИРУЕТ — проверено
замером выше. Работает `enable_thinking` (соглашение vLLM/Qwen), поэтому имя
ключа тоже под проверкой: опечатка здесь ничего не сломает, только вернёт
двадцатитрёхминутные прогоны.
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "agent_core"


def _create_calls() -> list[tuple[str, ast.Call]]:
    """Все вызовы `*.chat.completions.create(...)` в пакете."""
    out: list[tuple[str, ast.Call]] = []
    for path in sorted(PKG.rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "create":
                # ...chat.completions.create
                owner = func.value
                if isinstance(owner, ast.Attribute) and owner.attr == "completions":
                    out.append((str(path.relative_to(PKG.parent)), node))
    return out


def test_there_are_model_calls_to_check():
    """Страховка теста: пустой разбор сделал бы его зелёным навсегда."""
    calls = _create_calls()
    assert len(calls) >= 4, f"найдено вызовов модели: {len(calls)}"


def test_every_model_call_disables_reasoning():
    """
    Ни один вызов не уходит без выключателя размышления.

    Пропущенный клиент не покраснеет нигде: он просто будет в двенадцать раз
    медленнее остальных, а изредка — молча пустым.
    """
    offenders = []
    for where, call in _create_calls():
        kwargs = {kw.arg for kw in call.keywords if kw.arg}
        if "extra_body" not in kwargs:
            offenders.append(where)
    assert not offenders, (
        "вызовы модели без extra_body с выключателем размышления: "
        + ", ".join(sorted(set(offenders)))
    )


def test_switch_uses_the_key_provider_understands():
    """
    Ключ именно `enable_thinking`.

    `thinking: false` — то, что написано в документации провайдера, — шлюз
    игнорирует: замер показал те же 600 токенов рассуждения и пустой content.
    Опечатка в имени ключа ничего не сломает и потому не будет замечена.
    """
    from agent_core.config import ModelConfig

    config = ModelConfig(
        api_key="k", base_url="u", vlm_base_url="u",
        text_model="m", vlm_model="m", proxy_source="s",
    )
    body = config.extra_body()
    assert body["chat_template_kwargs"]["enable_thinking"] is False, body


def test_reasoning_can_be_turned_back_on():
    """
    Выключатель управляется окружением, а не прибит гвоздями.

    Размышление может понадобиться судье QA и синтезу аналитики — там модель
    выносит суждение, а не описывает увиденное. Если метрика
    `qa_catches_injected` просядет, включать обратно надо переменной, а не
    правкой шести клиентов.
    """
    from agent_core.config import ModelConfig

    config = ModelConfig(
        api_key="k", base_url="u", vlm_base_url="u",
        text_model="m", vlm_model="m", proxy_source="s", thinking=True,
    )
    assert config.extra_body() == {}, config.extra_body()
