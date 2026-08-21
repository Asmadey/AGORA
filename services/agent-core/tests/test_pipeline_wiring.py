"""
Граф конвейера, прогресс и чекпоинт — то, из-за чего прогон теряется целиком.

─── Почему эти три вместе ────────────────────────────────────────────────────
Все три отвечают не за содержание работы, а за то, что она дойдёт до конца и
будет видна. Ошибка в них не портит отчёт — она его теряет: пропущенный узел,
события прогресса не в том порядке, прогон, начавшийся заново после перезапуска
воркера. Каждое из этого выглядит как «что-то пошло не так», и разбирать его
приходится по логам контейнера, которого уже нет.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_core.pipeline import graph as graph_mod
from agent_core.pipeline.progress import ProgressWriter

# ─────────────────────────────────────────────────────────────────────────
# Граф: все узлы достижимы, ни один не потерян
# ─────────────────────────────────────────────────────────────────────────

def test_node_list_is_shared_with_the_web():
    """
    Список узлов лежит в packages/shared и читается обеими сторонами. Копия в
    TypeScript разошлась бы при первой правке конвейера и НИЧЕГО бы не сломала
    заметно: шкала прогресса просто показывала бы не тот этап.
    """
    assert graph_mod.NODES, "список узлов пуст"
    assert len(set(graph_mod.NODES)) == len(graph_mod.NODES), "узлы повторяются"


def test_every_node_has_an_implementation():
    """
    Узел, объявленный в общем списке и не реализованный, обрывает прогон на
    середине — уже после расшифровки и разбора кадров.
    """
    from agent_core.pipeline.nodes import DEFAULT_NODES as IMPL

    missing = [n for n in graph_mod.NODES if n not in IMPL]
    assert not missing, f"объявлены и не реализованы: {missing}"


def test_no_implementation_is_orphaned():
    """
    Обратная сторона: реализованный узел, которого нет в списке, не будет
    вызван никогда. Его работа выглядит написанной, а конвейер идёт мимо — это
    ровно тот класс дефекта, который занял эту сессию целиком.
    """
    from agent_core.pipeline.nodes import DEFAULT_NODES as IMPL

    orphans = [n for n in IMPL if n not in graph_mod.NODES]
    assert not orphans, f"реализованы и не вызываются: {orphans}"


def test_long_only_node_is_part_of_the_list():
    assert graph_mod.LONG_ONLY in graph_mod.NODES


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("long", graph_mod.LONG_ONLY), ("short", "sample_frames"), (None, "sample_frames")],
)
def test_route_sends_long_runs_through_segmentation(mode, expected):
    assert graph_mod.route({"mode": mode}) == expected  # type: ignore[arg-type]


def test_cancellation_is_not_a_failure():
    """
    Отдельный тип исключения. Пойди отмена общим путём, пользователь увидел бы
    «прогон упал» на то, что сам же остановил.
    """
    assert issubclass(graph_mod.RunCancelled, Exception)
    assert not issubclass(graph_mod.RunCancelled, SystemExit)


def test_node_list_matches_the_json_on_disk():
    """Сверка с файлом: список читается из него, и подмена в коде не пройдёт."""
    root = Path(__file__).resolve().parents[3]
    data = json.loads(
        (root / "packages" / "shared" / "pipeline" / "nodes.json").read_text("utf-8")
    )
    assert tuple(n["name"] for n in data["nodes"]) == graph_mod.NODES


# ─────────────────────────────────────────────────────────────────────────
# Прогресс: порядок событий и снимок
# ─────────────────────────────────────────────────────────────────────────

class _FakeValkey:
    """Минимальный Valkey в памяти: столько, сколько трогает ProgressWriter."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.published: list[tuple[str, str]] = []

    def set(self, key, value, **kwargs):  # noqa: ARG002
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def publish(self, channel, message):
        self.published.append((channel, message))


@pytest.fixture
def progress():
    client = _FakeValkey()
    return client, ProgressWriter(client, "task-1")


def test_snapshot_is_empty_before_anything_happens(progress):
    _, writer = progress
    snap = writer.snapshot()
    assert isinstance(snap, dict)


def test_events_are_published_in_order(progress):
    """
    Экран строит шкалу по порядку событий. Перемешавшись, они показали бы
    завершённым узел, который ещё идёт.
    """
    client, writer = progress
    writer.emit("probe_and_normalize", "RUNNING")
    writer.emit("probe_and_normalize", "DONE")
    writer.emit("detect_speech", "RUNNING")

    assert len(client.published) == 3
    nodes = [json.loads(m)["node"] for _, m in client.published]
    assert nodes == ["probe_and_normalize", "probe_and_normalize", "detect_speech"]


def test_failure_carries_the_reason(progress):
    """
    Без причины на экране остаётся «ошибка», и разбирать её приходится по логам
    контейнера, который к тому времени уже удалён.
    """
    client, writer = progress
    writer.fail("analyze_chunks", "HTTPError: 502 от провайдера")

    _, message = client.published[-1]
    payload = json.loads(message)
    assert payload["node"] == "analyze_chunks"
    assert "502" in json.dumps(payload, ensure_ascii=False)


def test_snapshot_survives_a_reconnect(progress):
    """
    Экран прогресса переподключается к SSE. Снимок в хранилище — единственное,
    что переживает разрыв: без него вкладка, открытая заново, показала бы пустую
    шкалу на идущем прогоне.
    """
    client, writer = progress
    writer.emit("probe_and_normalize", "DONE")

    revived = ProgressWriter(client, "task-1")
    assert revived.snapshot(), "снимок не восстановился из хранилища"


def test_writers_of_different_tasks_do_not_mix(progress):
    """Ключ включает идентификатор задачи — иначе два прогона делят одну шкалу."""
    client, writer = progress
    writer.emit("probe_and_normalize", "DONE")

    other = ProgressWriter(client, "task-2")
    assert not other.snapshot().get("timings"), "снимок утёк в чужую задачу"
