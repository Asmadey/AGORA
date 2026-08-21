"""
Сколько занял каждый этап — восстановимо после прогона.

─── Почему этого не было ────────────────────────────────────────────────────
Снимок прогресса лежит в одном ключе Valkey и перезаписывается на каждое
событие: в нём всегда только текущий узел. Колонка `tasks.progress` заведена в
схеме с первого дня и не пишется никем. То есть длительность этапа не хранилась
нигде — ни на лету, ни после.

Для продукта это не мелочь. «Время обработки» — показатель экрана исследования,
а на вопрос «почему прогон шёл сорок минут» отвечать было нечем: транскрипция,
разбор кадров и опрос персон отличаются по цене в разы, и без разбивки не видно,
за что заплачено.

─── Почему тайминги живут в снимке ──────────────────────────────────────────
Рядом с текущим узлом, а не в отдельном ключе. Ключ один — значит один TTL, одна
запись, один порядок. Отдельный ключ пришлось бы синхронизировать с этим, и
расхождение проявлялось бы как «этап шёл ноль секунд».

Список ограничен числом узлов конвейера (около десятка), поэтому снимок от него
не распухает.
"""

from __future__ import annotations

from agent_core.pipeline.progress import ProgressWriter


class FakeValkey:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.published: list[tuple[str, str]] = []

    def set(self, key: str, value: str, **kwargs: object) -> None:  # noqa: ARG002
        self.store[key] = value

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))


def test_node_duration_is_recoverable():
    """RUNNING и DONE одного узла складываются в замер длительности."""
    writer = ProgressWriter(FakeValkey(), "t-1")

    writer.emit("preprocess", "RUNNING")
    snapshot = writer.emit("preprocess", "DONE")

    timings = snapshot["timings"]
    assert len(timings) == 1
    assert timings[0]["node"] == "preprocess"
    assert timings[0]["started_at"] is not None
    assert timings[0]["finished_at"] is not None
    assert timings[0]["duration_sec"] >= 0


def test_every_node_gets_its_own_entry():
    """Замеры накапливаются, а не перезаписываются текущим узлом."""
    writer = ProgressWriter(FakeValkey(), "t-2")

    for node in ("preprocess", "transcribe", "sample_frames"):
        writer.emit(node, "RUNNING")
        writer.emit(node, "DONE")

    assert [t["node"] for t in writer.snapshot()["timings"]] == [
        "preprocess", "transcribe", "sample_frames",
    ]


def test_failed_node_is_closed_too():
    """
    Упавший этап тоже имеет длительность.

    Иначе самый интересный для разбора случай — «на чём именно встало и через
    сколько» — остаётся единственным, о котором ничего не известно.
    """
    writer = ProgressWriter(FakeValkey(), "t-3")

    writer.emit("transcribe", "RUNNING")
    snapshot = writer.fail("transcribe", "провайдер молчит")

    entry = snapshot["timings"][-1]
    assert entry["node"] == "transcribe"
    assert entry["finished_at"] is not None
    assert entry["status"] == "FAILED"


def test_timings_survive_a_resumed_run():
    """
    Возобновление с чекпоинта продолжает счёт, а не начинает с нуля.

    Воркер может перезапуститься посреди прогона — ради этого и заведён
    чекпоинтер. Новый `ProgressWriter` обязан подхватить уже записанные замеры,
    иначе «время обработки» покажет длительность последней попытки.
    """
    client = FakeValkey()
    first = ProgressWriter(client, "t-4")
    first.emit("preprocess", "RUNNING")
    first.emit("preprocess", "DONE")

    second = ProgressWriter(client, "t-4")
    second.emit("transcribe", "RUNNING")
    snapshot = second.emit("transcribe", "DONE")

    assert [t["node"] for t in snapshot["timings"]] == ["preprocess", "transcribe"]
