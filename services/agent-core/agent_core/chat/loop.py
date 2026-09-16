"""
Цикл вызовов инструментов: модель ходит за материалом сама.

─── Что здесь происходит ────────────────────────────────────────────────────
Модель получает оглавление сцен и объявления инструментов (`chat/tools.py`).
Чтобы ответить, она просит нужное — иногда в два захода: сначала найти сцены по
словам, потом взять речь на их отрезке. Результаты исполняются локально, по уже
прочитанным данным, и возвращаются ей сообщениями роли `tool`.

─── Почему у цикла потолок ──────────────────────────────────────────────────
Каждый раунд — оплаченный вызов модели. Цикл без потолка при неудачном вопросе
крутится, пока не кончатся деньги, и заметить это можно только по счёту.

Дойдя до потолка, цикл НЕ обрывается молчанием и НЕ отвечает отказом. Он делает
последний заход без инструментов: материал к этому моменту уже собран, и
ответить есть чем. Обрыв выглядел бы как зависший чат, отказ — как поломка.

Потолок держится не уговором, а механизмом: на последнем заходе инструменты не
передаются вовсе, поэтому вызвать их нечем.

─── Почему ход виден человеку ───────────────────────────────────────────────
Раунды идут ДО первого слова ответа. Молчание на десять секунд читается как
зависание, а не как работа, — поэтому цикл отдаёт наружу события двух видов:
`step` (что смотрим сейчас) и `delta` (кусок ответа).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from .tools import TOOL_SPECS, dispatch

#: Сколько раз модель может сходить за материалом, прежде чем обязана ответить.
#:
#: Пять — это «найти, уточнить, добрать речь, добрать ответы персон и ещё один
#: про запас». Больше означает счёт, который никто не заметит; меньше — что
#: сложный вопрос упрётся в потолок на середине.
MAX_ROUNDS = 5

#: Сколько символов результата инструмента уезжает модели.
#:
#: Потолки в самих инструментах считают ЗАПИСИ (сцены, реплики, ответы), а этот
#: считает символы: двадцать сцен с длинными описаниями весят больше двадцати
#: коротких. Второй рубеж нужен затем, чтобы вес одного раунда был известен
#: заранее, а не зависел от материала.
MAX_TOOL_RESULT_CHARS = 40_000


@dataclass(frozen=True)
class ToolCall:
    """Вызов, о котором попросила модель."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


#: Как назвать человеку то, что сейчас смотрят.
_STEP_WORDS = {
    "get_scenes": "смотрю сцены",
    "search_scenes": "ищу сцены",
    "get_transcript": "читаю реплики",
    "get_persona_answers": "смотрю ответы персон",
}


def _step_text(call: ToolCall) -> str:
    """Подпись хода. Имя инструмента остаётся в скобках — по нему видно, что шло."""
    words = _STEP_WORDS.get(call.name, "смотрю материал")
    args = call.arguments or {}
    lo, hi = args.get("from_sec"), args.get("to_sec")
    if numbers := args.get("numbers"):
        detail = f"№ {', '.join(str(n) for n in list(numbers)[:6])}"
    elif lo is not None or hi is not None:
        detail = f"{lo or 0:.0f}–{hi or 0:.0f} с"
    elif q := args.get("query"):
        detail = f"«{q}»"
    else:
        detail = ""
    return f"{words} {detail}".strip() + f" ({call.name})"


def _tool_payload(result: dict[str, Any]) -> str:
    """
    Результат инструмента как текст для модели.

    Перебор по символам обрезается, и обрезка НАЗЫВАЕТСЯ: молча укороченный
    JSON модель прочтёт как повреждённый ответ либо, что хуже, как полный.
    """
    text = json.dumps(result, ensure_ascii=False)
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return json.dumps(
        {
            "error": (
                f"ответ инструмента не поместился ({len(text)} символов при потолке "
                f"{MAX_TOOL_RESULT_CHARS}). Запросите меньше: сузьте диапазон или "
                f"перечислите номера сцен."
            )
        },
        ensure_ascii=False,
    )


def run_with_tools(
    *,
    model: Callable[..., tuple[list[ToolCall], Any]],
    base_messages: list[dict[str, Any]],
    pack: dict[str, Any],
    answers: list[dict[str, Any]],
    persona_id: str | None = None,
) -> Iterator[tuple[str, str]]:
    """
    Гоняет раунды инструментов и отдаёт ответ.

    Наружу идут пары `(вид, текст)`: `step` — что смотрим сейчас, `delta` —
    кусок ответа. Вызывающий решает, что показывать человеку, а что копить.

    `model` — вызов шлюза: принимает `messages` и `tools`, возвращает пару
    «вызовы инструментов, поток кусков». Передаётся параметром, а не берётся
    из модуля, чтобы устройство цикла проверялось без похода в сеть.
    """
    messages = [dict(m) for m in base_messages]

    for round_no in range(MAX_ROUNDS):
        # На последнем заходе инструментов нет: потолок обязан держаться
        # механизмом, а не просьбой к модели остановиться.
        last = round_no == MAX_ROUNDS - 1
        calls, stream = model(messages=messages, tools=None if last else TOOL_SPECS)

        if not calls:
            for piece in stream or []:
                yield ("delta", piece)
            return

        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {
                            "name": c.name,
                            "arguments": json.dumps(c.arguments, ensure_ascii=False),
                        },
                    }
                    for c in calls
                ],
            }
        )

        for call in calls:
            yield ("step", _step_text(call))
            result = dispatch(
                call.name,
                call.arguments,
                pack=pack,
                answers=answers,
                persona_id=persona_id,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": _tool_payload(result),
                }
            )

    # Потолок исчерпан, а модель всё ещё просит инструменты. Материал собран —
    # требуем ответить им.
    _, stream = model(messages=messages, tools=None)
    for piece in stream or []:
        yield ("delta", piece)
