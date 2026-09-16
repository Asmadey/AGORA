"""
Цикл вызовов инструментов: сколько раундов, что уходит в поток, где потолок.

─── Почему цикл, а не один запрос ───────────────────────────────────────────
Модель получает оглавление и инструменты. Чтобы ответить, ей нужно сходить за
материалом — иногда дважды: сначала найти сцены по словам, потом взять речь на
их отрезке. Один запрос это не покрывает.

─── Почему у цикла обязан быть потолок ──────────────────────────────────────
Каждый раунд — это оплаченный вызов модели. Цикл без потолка при неудачном
вопросе крутится, пока не кончатся деньги, и заметить это можно только по
счёту. Потолок ставит границу, известную заранее.

Дойдя до потолка, цикл не молчит и не падает: он требует от модели ответить
тем, что уже собрано. Молчаливый обрыв выглядел бы как зависший чат.

─── Почему поток остаётся ───────────────────────────────────────────────────
Владелец выбрал поток по словам (`chat/client.py`), и раунды инструментов его
не отменяют: они идут ДО ответа. Пока они идут, человеку показывается, что
именно сейчас смотрят, — это лучше нынешнего молчаливого ожидания, а не хуже.
"""
from __future__ import annotations

import json
from typing import Any

from agent_core.chat.loop import MAX_ROUNDS, ToolCall, run_with_tools

PACK = {
    "scenes": [
        {"time": "0:00–0:06", "timestamp_sec": 0.0, "end_sec": 6.0,
         "scene_description": "Разрушение объектов", "actions": [], "characters": []},
        {"time": "1:00–1:35", "timestamp_sec": 60.0, "end_sec": 95.0,
         "scene_description": "Разговор на кухне", "actions": [], "characters": []},
    ],
    "transcript": [{"start": 67.0, "end": 72.0, "text": "Смотри.", "speaker": "S0"}],
}
ANSWERS = [{"persona_id": "p1", "persona_name": "Анна", "answers": {"overall": 7}}]


class FakeModel:
    """
    Шлюз, отвечающий по заранее заданному сценарию.

    Живой вызов здесь не нужен и вреден: проверяется устройство цикла, а не
    сообразительность модели. Сценарий — список шагов: список `ToolCall` либо
    список кусков финального ответа.

    Одно поведение подделка обязана повторять точно: **без инструментов модель
    отвечает текстом**. Шлюз, которому не дали инструментов, вызвать их не
    может — и подделка, продолжающая их «вызывать», проверяла бы потолок,
    которого в жизни нет.
    """

    def __init__(self, script):
        self.script = list(script)
        self.seen: list[list[dict]] = []
        self.tools_seen: list[Any] = []

    @property
    def tools_last_call(self):
        return self.tools_seen[-1] if self.tools_seen else None

    def __call__(self, *, messages, tools):
        self.seen.append([dict(m) for m in messages])
        self.tools_seen.append(tools)

        if not tools:
            # Инструментов не дали — отвечаем первым текстовым шагом.
            while self.script and not _is_answer(self.script[0]):
                self.script.pop(0)
            return [], self.script.pop(0) if self.script else [""]

        step = self.script.pop(0)
        return (step, None) if not _is_answer(step) else ([], step)


def _is_answer(step) -> bool:
    return bool(step) and isinstance(step[0], str)


def _chunks(gen):
    return list(gen)


# ─── Раунды инструментов ────────────────────────────────────────────────────


def test_вызов_инструмента_исполняется_и_ответ_уходит_модели():
    model = FakeModel([
        [ToolCall(id="c1", name="get_scenes", arguments={"numbers": [2]})],
        ["Готово."],
    ])
    out = _chunks(run_with_tools(
        model=model, base_messages=[{"role": "user", "content": "вопрос"}],
        pack=PACK, answers=ANSWERS,
    ))
    assert "".join(p for kind, p in out if kind == "delta") == "Готово."

    # Второй заход обязан нести результат инструмента.
    second = model.seen[1]
    tool_msgs = [m for m in second if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    payload = json.loads(tool_msgs[0]["content"])
    assert payload["scenes"][0]["n"] == 2
    assert tool_msgs[0]["tool_call_id"] == "c1"


def test_несколько_инструментов_за_один_раунд():
    model = FakeModel([
        [
            ToolCall(id="a", name="search_scenes", arguments={"query": "кухне"}),
            ToolCall(id="b", name="get_transcript", arguments={"from_sec": 60, "to_sec": 90}),
        ],
        ["Ответ."],
    ])
    _chunks(run_with_tools(
        model=model, base_messages=[{"role": "user", "content": "q"}],
        pack=PACK, answers=ANSWERS,
    ))
    tool_msgs = [m for m in model.seen[1] if m.get("role") == "tool"]
    assert {m["tool_call_id"] for m in tool_msgs} == {"a", "b"}


def test_ход_инструментов_виден_человеку():
    """Молчание на десять секунд читается как зависание, а не как работа."""
    model = FakeModel([
        [ToolCall(id="c1", name="get_scenes", arguments={"numbers": [1]})],
        ["Ответ."],
    ])
    out = _chunks(run_with_tools(
        model=model, base_messages=[{"role": "user", "content": "q"}],
        pack=PACK, answers=ANSWERS,
    ))
    steps = [p for kind, p in out if kind == "step"]
    assert steps, "ход инструментов обязан доезжать до экрана"
    assert any("get_scenes" in s or "сцен" in s.lower() for s in steps)


# ─── Потолок ────────────────────────────────────────────────────────────────


def test_потолок_раундов_существует_и_невелик():
    assert 2 <= MAX_ROUNDS <= 8, f"MAX_ROUNDS={MAX_ROUNDS}"


def test_на_потолке_цикл_требует_ответа_а_не_обрывается():
    """
    Дойдя до потолка, цикл делает последний заход БЕЗ инструментов. Обрыв
    молчанием выглядел бы как зависший чат, а отказ — как поломка, хотя
    материал уже собран и ответить есть чем.
    """
    script = [[ToolCall(id=f"c{i}", name="get_scenes", arguments={"numbers": [1]})]
              for i in range(MAX_ROUNDS + 3)]
    script.append(["Отвечаю тем, что собрал."])
    model = FakeModel(script)

    out = _chunks(run_with_tools(
        model=model, base_messages=[{"role": "user", "content": "q"}],
        pack=PACK, answers=ANSWERS,
    ))
    assert "".join(p for kind, p in out if kind == "delta") == "Отвечаю тем, что собрал."

    # Последний заход — без инструментов: иначе потолка не существует.
    assert model.tools_last_call is None or model.tools_last_call == []


def test_вызовов_модели_не_больше_чем_потолок_плюс_один():
    script = [[ToolCall(id=f"c{i}", name="get_scenes", arguments={"numbers": [1]})]
              for i in range(MAX_ROUNDS + 5)]
    script.append(["Всё."])
    model = FakeModel(script)
    _chunks(run_with_tools(
        model=model, base_messages=[{"role": "user", "content": "q"}],
        pack=PACK, answers=ANSWERS,
    ))
    assert len(model.seen) <= MAX_ROUNDS + 1, f"вызовов {len(model.seen)}"


# ─── Ответ без инструментов ─────────────────────────────────────────────────


def test_модель_вправе_ответить_сразу():
    model = FakeModel([["Это ", "простой ", "вопрос."]])
    out = _chunks(run_with_tools(
        model=model, base_messages=[{"role": "user", "content": "q"}],
        pack=PACK, answers=ANSWERS,
    ))
    assert "".join(p for kind, p in out if kind == "delta") == "Это простой вопрос."
    assert len(model.seen) == 1


# ─── Изоляция доезжает до цикла ─────────────────────────────────────────────


def test_персона_не_получит_чужие_ответы_через_инструмент():
    answers = [
        {"persona_id": "p1", "persona_name": "Анна", "answers": {"overall": 7}},
        {"persona_id": "p2", "persona_name": "Борис", "answers": {"overall": 3}},
    ]
    model = FakeModel([
        [ToolCall(id="c1", name="get_persona_answers",
                  arguments={"persona_ids": ["p1", "p2"]})],
        ["Ответ."],
    ])
    _chunks(run_with_tools(
        model=model, base_messages=[{"role": "user", "content": "q"}],
        pack=PACK, answers=answers, persona_id="p1",
    ))
    payload = json.loads([m for m in model.seen[1] if m.get("role") == "tool"][0]["content"])
    assert [a["persona_id"] for a in payload["answers"]] == ["p1"]
