"""
Тесты оркестратора (#13): чекпоинтер на голом Valkey, прогресс, маршрутизация.

Чекпоинтер здесь проверяется не «сохраняет и читает», а через то, ради чего он
заведён: перезапуск обязан НЕ повторять уже пройденные узлы. Проверка по
итоговому состоянию бесполезна — прогон с нуля и прогон с чекпоинта дают
одинаковый результат, в этом и смысл. Отличаются они только объёмом повторной
работы, и виден он лишь по счётчику вызовов.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent_core.pipeline.checkpoint import ValkeyCheckpointSaver
from agent_core.pipeline.graph import NODES, build_graph, route
from agent_core.pipeline.progress import ProgressWriter, progress_channel, progress_key
from agent_core.pipeline.state import new_state


class FakeValkey:
    """Голый Valkey: только команды, которые есть без модулей Redis Stack."""

    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}
        self.published: list[tuple[str, Any]] = []

    def set(self, key, value, **kw):
        self.kv[key] = value

    def get(self, key):
        return self.kv.get(key)

    def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)

    def scan_iter(self, match=None, **kw):
        return iter([k for k in list(self.kv) if k.startswith((match or "*").rstrip("*"))])

    def publish(self, channel, message):
        self.published.append((channel, message))


def stub_nodes(calls: list[str], fail_at: str | None, armed: dict) -> dict:
    def make(name: str):
        def node(state):
            calls.append(name)
            if name == fail_at and armed["on"]:
                raise RuntimeError("узел упал")
            return {}
        return node

    return {n: make(n) for n in NODES}


# ─── Маршрутизация ───────────────────────────────────────────────────────────


def test_route_splits_short_and_long():
    short = route(new_state(task_id="t", tenant_id="x", mode="short"))
    long_ = route(new_state(task_id="t", tenant_id="x", mode="long"))
    assert short != long_
    assert long_ == "segment_video"


def test_route_reads_mode_and_does_not_guess_from_duration():
    """Режим задан на запуске и попал в ключ идемпотентности — пересчёт его запрещён."""
    state = new_state(task_id="t", tenant_id="x", mode="short")
    state["duration_sec"] = 3600.0
    assert route(state) == "sample_frames"


# ─── Чекпоинтер ──────────────────────────────────────────────────────────────


def test_resume_does_not_repeat_completed_nodes():
    valkey = FakeValkey()
    calls: list[str] = []
    armed = {"on": True}
    nodes = stub_nodes(calls, "pack", armed)
    config = {"configurable": {"thread_id": "run-1"}}

    graph = build_graph(checkpointer=ValkeyCheckpointSaver(valkey), nodes=nodes)
    with pytest.raises(RuntimeError):
        graph.invoke(new_state(task_id="run-1", tenant_id="team", mode="short"), config)

    before = list(calls)
    calls.clear()
    armed["on"] = False

    # Новый граф и новый саверт на том же хранилище — это перезапуск процесса:
    # в памяти не осталось ничего, всё берётся из Valkey.
    build_graph(checkpointer=ValkeyCheckpointSaver(valkey), nodes=nodes).invoke(None, config)

    assert "probe_and_normalize" in before
    assert "probe_and_normalize" not in calls, "транскрипция и медиа прогнаны повторно"
    assert calls[0] == "pack", f"продолжили не с упавшего узла: {calls[:3]}"
    assert "analytics" in calls


def test_long_mode_passes_through_segment_video():
    valkey = FakeValkey()
    calls: list[str] = []
    nodes = stub_nodes(calls, None, {"on": False})
    build_graph(checkpointer=ValkeyCheckpointSaver(valkey), nodes=nodes).invoke(
        new_state(task_id="run-2", tenant_id="team", mode="long"),
        {"configurable": {"thread_id": "run-2"}},
    )
    assert "segment_video" in calls


def test_short_mode_skips_segment_video():
    valkey = FakeValkey()
    calls: list[str] = []
    nodes = stub_nodes(calls, None, {"on": False})
    build_graph(checkpointer=ValkeyCheckpointSaver(valkey), nodes=nodes).invoke(
        new_state(task_id="run-3", tenant_id="team", mode="short"),
        {"configurable": {"thread_id": "run-3"}},
    )
    assert "segment_video" not in calls


def test_checkpointer_uses_only_plain_commands():
    """FakeValkey не умеет ничего из Redis Stack — обращение к JSON.*/FT.* упало бы."""
    valkey = FakeValkey()
    nodes = stub_nodes([], None, {"on": False})
    build_graph(checkpointer=ValkeyCheckpointSaver(valkey), nodes=nodes).invoke(
        new_state(task_id="run-4", tenant_id="team"), {"configurable": {"thread_id": "run-4"}},
    )
    assert any(k.startswith("agora:cp:") for k in valkey.kv)


def test_delete_thread_removes_checkpoints():
    valkey = FakeValkey()
    saver = ValkeyCheckpointSaver(valkey)
    nodes = stub_nodes([], None, {"on": False})
    build_graph(checkpointer=saver, nodes=nodes).invoke(
        new_state(task_id="run-5", tenant_id="team"), {"configurable": {"thread_id": "run-5"}},
    )
    saver.delete_thread("run-5")
    assert not [k for k in valkey.kv if "run-5" in k]


def test_degraded_accumulates_across_nodes():
    """Отметки о деградации складываются: обычный канал оставил бы только последнюю."""
    valkey = FakeValkey()
    nodes = stub_nodes([], None, {"on": False})
    nodes["diarize"] = lambda s: {"degraded": ["diarize: нет токена"]}
    nodes["analyze_chunks"] = lambda s: {"degraded": ["analyze_chunks: кап исчерпан"]}

    final = build_graph(checkpointer=ValkeyCheckpointSaver(valkey), nodes=nodes).invoke(
        new_state(task_id="run-6", tenant_id="team"), {"configurable": {"thread_id": "run-6"}},
    )
    assert len(final["degraded"]) == 2


# ─── Прогресс ────────────────────────────────────────────────────────────────


def test_progress_survives_reconnect():
    """Снимок читается из ключа: подписчик, пришедший позже, ничего не потерял."""
    valkey = FakeValkey()
    ProgressWriter(valkey, "run-7").emit("transcribe", "RUNNING")
    assert ProgressWriter(valkey, "run-7").snapshot()["node"] == "transcribe"
    assert progress_key("run-7") in valkey.kv


def test_progress_publishes_after_writing_key():
    """Порядок значим: разбуженный подписчик обязан прочитать новое значение."""
    valkey = FakeValkey()
    writer = ProgressWriter(valkey, "run-8")
    writer.emit("pack", "DONE")
    channel, message = valkey.published[-1]
    assert channel == progress_channel("run-8")
    assert json.loads(message)["node"] == "pack"
    assert json.loads(valkey.kv[progress_key("run-8")])["node"] == "pack"


def test_failed_carries_reason():
    valkey = FakeValkey()
    ProgressWriter(valkey, "run-9").fail("transcribe", "Whisper упал по OOM")
    snap = ProgressWriter(valkey, "run-9").snapshot()
    assert snap["status"] == "FAILED"
    assert "OOM" in snap["error"]


def test_broken_snapshot_does_not_raise():
    """Битый снимок показывает «нет данных», а не роняет экран запущенного прогона."""
    valkey = FakeValkey()
    valkey.kv[progress_key("run-10")] = "{не json"
    assert ProgressWriter(valkey, "run-10").snapshot() == {}


# ─── Отказ узла: «этапа нет» против «входа нет» ──────────────────────────────
#
# Здесь стояла проверка test_unimplemented_stages_fail_loudly: она перечисляла
# qa (#19) и analytics (#20) и требовала от обоих StageNotImplemented с номером
# задачи. Оба узла написаны, и предмета у неё не осталось — последний
# ненаписанный этап конвейера исчез вместе с #20.
#
# Выбрасывать требование вместе с проверкой было бы неверно: правило не в том,
# что qa и analytics отказывают, а в том, ЧЕМ отказывает узел. Оно переживает
# конкретные задачи, поэтому переписано в форме, которая не зависит от того,
# сколько этапов ещё не написано.
#
# История, из-за которой это важно: пока qa был заглушкой, старая проверка
# ждала StageNotImplemented; после реализации она покраснела в CI — и поймала
# ровно то, что должна была, смену контракта узла. Но если из такой проверки
# вычёркивать узел за узлом по мере написания, к концу графа от требования не
# останется ничего.


@pytest.mark.parametrize("node_name", ["qa", "analytics"])
def test_stage_without_input_fails_as_missing_input(node_name):
    """
    Реализованный этап без входа поднимает ValueError, а не StageNotImplemented.

    Различие не косметическое. StageNotImplemented означает «этапа нет», и по
    нему читающий лог идёт искать ненаписанную задачу — вместо отказавшего
    evaluate_personas, который и не дал ответов. Поэтому в тексте отказа обязан
    стоять узел-виновник, а не номер задачи.
    """
    from agent_core.pipeline import nodes

    with pytest.raises(ValueError) as e:
        getattr(nodes, node_name)(new_state(task_id="t", tenant_id="x"))
    assert not isinstance(e.value, nodes.StageNotImplemented)
    assert "evaluate_personas" in str(e.value)


def test_stage_not_implemented_stays_available_for_future_stages():
    """
    Исключение «этап не написан» никуда не делось вместе с последней заглушкой.

    Ф4 (#28–#31) добавит узлы, и первым их состоянием снова будет заглушка.
    Проверка держит сам механизм: класс на месте и остаётся подтипом ошибки
    времени выполнения, а не превращается, скажем, в ValueError — иначе
    проверка выше перестала бы что-либо различать.
    """
    from agent_core.pipeline.nodes import StageNotImplemented

    assert issubclass(StageNotImplemented, RuntimeError)
    assert not issubclass(StageNotImplemented, ValueError)
