"""
Отсев одинаковых кадров и возобновление прогона после перезапуска.

─── Дедупликация ─────────────────────────────────────────────────────────────
Режет стоимость разбора: каждый оставленный кадр — это оплаченный вызов модели
зрения. Ошибка в обе стороны дорога и невидима. Слишком жадный отсев выбрасывает
сцену, и в отчёте её просто нет — отличить от «модель не заметила» нельзя.
Слишком слабый удваивает счёт от провайдера, и заметно это только в конце месяца.

─── Чекпоинт ─────────────────────────────────────────────────────────────────
Единственное, что позволяет прогону пережить перезапуск воркера. Без него
пятнадцатиминутный ролик после падения на разборе кадров начинается с
расшифровки заново — то есть заново оплачивается.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_core.frames.dedup import dedupe, hamming

# ─────────────────────────────────────────────────────────────────────────
# Дедупликация
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def hashes(monkeypatch):
    """
    Подменяет вычисление хэша: сравнение хэшей — предмет проверки, а чтение
    картинки с диска — нет. Кадр задаётся именем файла, хэш берётся из словаря.
    """
    table: dict[str, int] = {}

    def fake_dhash(path):
        return table[Path(path).name]

    import agent_core.frames.dedup as mod

    monkeypatch.setattr(mod, "dhash", fake_dhash)
    return table


def test_hamming_counts_differing_bits():
    assert hamming(0b0000, 0b0000) == 0
    assert hamming(0b1010, 0b0000) == 2
    assert hamming(0, (1 << 64) - 1) == 64


def test_identical_frames_collapse(hashes):
    hashes.update({"a.png": 0xDEADBEEF, "b.png": 0xDEADBEEF})
    kept = dedupe([Path("a.png"), Path("b.png")])
    assert [p.name for p in kept] == ["a.png"]


def test_different_frames_are_both_kept(hashes):
    hashes.update({"a.png": 0x0000000000000000, "b.png": 0xFFFFFFFFFFFFFFFF})
    kept = dedupe([Path("a.png"), Path("b.png")])
    assert [p.name for p in kept] == ["a.png", "b.png"]


def test_slow_pan_does_not_collapse_the_whole_chain(hashes):
    """
    Главное свойство: сравнение идёт с УЖЕ ОСТАВЛЕННЫМИ кадрами, а не с
    соседом. При плавном движении камеры каждый следующий кадр отличается от
    предыдущего на пару битов, а от первого — на сорок. Сравнение с соседом
    схлопнуло бы всю панораму в один кадр, и половина ролика исчезла бы из
    разбора, выглядя при этом «пропущенной моделью».
    """
    # Каждый следующий отличается от предыдущего на 2 бита, от первого — сильно.
    hashes.update({f"{i}.png": (1 << (2 * i)) - 1 for i in range(12)})
    kept = dedupe([Path(f"{i}.png") for i in range(12)], threshold=3)
    assert len(kept) > 2, f"панорама схлопнулась в {len(kept)} кадра"


def test_order_is_preserved(hashes):
    """
    Дальше по конвейеру этот порядок — порядок таймкодов.

    Хэши разведены на 16 бит каждый, а не «по одному биту на кадр»: первая
    редакция теста поставила по единственному установленному биту, и любые два
    таких хэша отличаются ровно на два бита — то есть меньше порога. Кадры
    честно схлопнулись, и падал тест, а не код.
    """
    hashes.update({f"{i}.png": ((1 << 16) - 1) << (i * 16) for i in range(4)})
    kept = dedupe([Path(f"{i}.png") for i in range(4)])
    assert [p.name for p in kept] == [f"{i}.png" for i in range(4)]


def test_empty_input_is_legal(hashes):
    assert dedupe([]) == []


def test_threshold_zero_keeps_everything_but_exact_duplicates(hashes):
    hashes.update({"a.png": 0b1000, "b.png": 0b1001, "c.png": 0b1000})
    kept = dedupe([Path("a.png"), Path("b.png"), Path("c.png")], threshold=0)
    assert [p.name for p in kept] == ["a.png", "b.png"]


# ─────────────────────────────────────────────────────────────────────────
# Чекпоинт
# ─────────────────────────────────────────────────────────────────────────

class _FakeValkey:
    """Хранилище в памяти: set/get/delete/scan_iter — всё, что трогает saver."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def set(self, key, value, **kwargs):  # noqa: ARG002
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    def scan_iter(self, match=None, **kwargs):  # noqa: ARG002
        if match is None:
            return iter(list(self.store))
        prefix = match.rstrip("*")
        return iter([k for k in list(self.store) if k.startswith(prefix)])


def _saver(client):
    from agent_core.pipeline.checkpoint import ValkeyCheckpointSaver

    return ValkeyCheckpointSaver(client)


def test_nothing_saved_means_nothing_to_resume():
    """
    Отсутствие чекпоинта — законное состояние: прогон запускается впервые.
    `run_pipeline` различает по нему «начать» и «продолжить», и ошибка здесь
    либо начинает заново оплаченный прогон, либо не начинает новый вовсе.
    """
    saver = _saver(_FakeValkey())
    assert saver.get_tuple({"configurable": {"thread_id": "task-1"}}) is None


def test_saved_checkpoint_is_found_by_the_same_thread():
    client = _FakeValkey()
    saver = _saver(client)
    config = {"configurable": {"thread_id": "task-1", "checkpoint_ns": ""}}

    checkpoint = {"id": "cp-1", "ts": "2026-08-19T00:00:00", "channel_values": {"x": 1},
                  "channel_versions": {}, "versions_seen": {}, "v": 1}
    saver.put(config, checkpoint, {"source": "loop", "step": 1}, {})

    found = saver.get_tuple({"configurable": {"thread_id": "task-1", "checkpoint_ns": ""}})
    assert found is not None, "сохранённый чекпоинт не найден — прогон начнётся заново"


def test_checkpoints_of_different_runs_do_not_mix():
    """
    Ключ включает идентификатор задачи. Смешавшись, два прогона продолжили бы
    друг друга — и увидеть это можно было бы только по отчёту про чужой ролик.
    """
    client = _FakeValkey()
    saver = _saver(client)
    checkpoint = {"id": "cp-1", "ts": "2026-08-19T00:00:00", "channel_values": {"x": 1},
                  "channel_versions": {}, "versions_seen": {}, "v": 1}
    saver.put({"configurable": {"thread_id": "task-1", "checkpoint_ns": ""}},
              checkpoint, {"source": "loop", "step": 1}, {})

    assert saver.get_tuple({"configurable": {"thread_id": "task-2", "checkpoint_ns": ""}}) is None


def test_stored_value_survives_a_round_trip_with_types_intact():
    """
    В хранилище обязан лежать РАЗБИРАЕМЫЙ формат, а не `repr`. Строка от repr
    тоже сохранилась бы и тоже прочиталась — но обратно превратилась бы в
    строку, и прогон продолжился бы с состоянием, где все значения текстовые:
    счётчики стали бы строками, списки — их изображением.

    Первая редакция теста требовала bytes и падала: saver кладёт JSON с
    msgpack в base64 внутри. Формат другой, свойство то же — проверяем свойство.
    """
    client = _FakeValkey()
    saver = _saver(client)
    checkpoint = {"id": "cp-1", "ts": "2026-08-19T00:00:00",
                  "channel_values": {"n": 7, "items": [1, 2, 3]},
                  "channel_versions": {}, "versions_seen": {}, "v": 1}
    config = {"configurable": {"thread_id": "task-1", "checkpoint_ns": ""}}
    saver.put(config, checkpoint, {"source": "loop", "step": 1}, {})

    assert client.store, "ничего не записано"
    stored = next(iter(client.store.values()))
    json.loads(stored)  # упадёт, если это repr, а не сериализованный формат

    revived = saver.get_tuple(config)
    assert revived is not None
    values = revived.checkpoint["channel_values"]
    assert values["n"] == 7 and isinstance(values["n"], int), values
    assert values["items"] == [1, 2, 3] and isinstance(values["items"], list), values
