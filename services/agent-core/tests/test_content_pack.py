"""
Тесты склейки в Content Pack (#17).

CDD-тест задачи проверяет пять условий приёмки на одном показательном входе.
Здесь — краевые случаи, на которых редьюс ломается тихо: пустой материал, немое
видео, реплика ровно на границе сцены, мусор в таймкодах от модели.
"""

from __future__ import annotations

import json

from agent_core.content.pack import (
    MAX_KEY_SCENES,
    MIN_COMPACT_LINE_CHARS,
    build_pack,
)


def line(start: float, end: float, text: str = "Достаточно длинная реплика для компакта") -> dict:
    return {"start": start, "end": end, "text": text}


def scene(ts: float, mood: str = "спокойное", desc: str = "Что-то происходит") -> dict:
    return {"timestamp_sec": ts, "scene_description": desc, "mood": mood}


def build(**kw):
    base = dict(
        transcript=[], speakers=[], scenes=[],
        duration_sec=100.0, mode="short", title="Т",
    )
    base.update(kw)
    return build_pack(**base)


# ─── Пустой и вырожденный вход ───────────────────────────────────────────────


def test_empty_input_yields_valid_pack():
    """Пустой материал не роняет склейку: пакет валиден и пуст."""
    pack = build()
    assert pack.full()["timeline"] == []
    assert pack.full()["scenes"] == []
    assert pack.compact()["scenes"] == []


def test_silent_video_keeps_scenes():
    """Немое видео: реплик нет, но сцены обязаны доехать.

    Иначе ролик без речи — заставка, клип, тизер — давал бы пустой пакет, и
    респонденту было бы нечего смотреть.
    """
    pack = build(scenes=[scene(0.0), scene(50.0, mood="тревожное")])
    full = pack.full()
    assert len(full["scenes"]) == 2
    assert len(full["timeline"]) == 2
    assert all(e["lines"] == [] for e in full["timeline"])


def test_speech_before_first_scene_is_kept():
    """Реплики до первой сцены не теряются — под них заводится запись."""
    pack = build(transcript=[line(0.0, 3.0)], scenes=[scene(40.0)])
    timeline = pack.full()["timeline"]
    assert timeline[0]["scene"] is None
    assert len(timeline[0]["lines"]) == 1


def test_no_scenes_still_builds_timeline():
    pack = build(transcript=[line(0.0, 3.0), line(5.0, 8.0)])
    timeline = pack.full()["timeline"]
    assert len(timeline) == 1
    assert len(timeline[0]["lines"]) == 2


# ─── Границы ─────────────────────────────────────────────────────────────────


def test_line_on_scene_boundary_counted_once():
    """Реплика ровно на границе сцен принадлежит следующей, и только ей.

    Полуинтервал [start, end) выбран именно для этого: при включении обеих
    границ реплика попала бы в две записи, и число реплик в статистике разошлось
    бы с их числом в транскрипте.
    """
    pack = build(
        transcript=[line(50.0, 52.0)],
        scenes=[scene(0.0), scene(50.0)],
    )
    timeline = pack.full()["timeline"]
    counts = [len(e["lines"]) for e in timeline]
    assert counts == [0, 1], counts
    assert sum(counts) == len(pack.full()["transcript"])


def test_final_line_at_exact_duration_survives():
    """Реплика, начинающаяся ровно на длительности, не теряется."""
    pack = build(transcript=[line(100.0, 100.0, "Финальное слово героя тут")],
                 scenes=[scene(0.0)], duration_sec=100.0)
    assert sum(len(e["lines"]) for e in pack.full()["timeline"]) == 1


def test_whisper_overshoot_is_clamped_not_dropped():
    """Хвост реплики за длительностью подрезается, а не выбрасывается.

    Whisper округляет конец сегмента вверх — это свойство декодера, а не
    выдумка модели, и терять из-за него последнюю фразу нельзя.
    """
    pack = build(transcript=[line(95.0, 103.0)], duration_sec=100.0)
    assert pack.full()["transcript"][0]["end"] == 100.0


def test_scene_beyond_duration_dropped_with_reason():
    pack = build(scenes=[scene(0.0), scene(500.0)], duration_sec=100.0)
    full = pack.full()
    assert [s["timestamp_sec"] for s in full["scenes"]] == [0.0]
    assert len(full["dropped_scenes"]) == 1
    assert "за концом ролика" in full["dropped_scenes"][0]["reason"]


def test_negative_scene_dropped_with_reason():
    pack = build(scenes=[scene(-5.0), scene(10.0)], duration_sec=100.0)
    dropped = pack.full()["dropped_scenes"]
    assert len(dropped) == 1
    assert "отрицательный" in dropped[0]["reason"]


def test_unparseable_timestamp_dropped():
    """Модель вернула не число — сцена выбрасывается, а не ломает склейку."""
    pack = build(scenes=[{"timestamp_sec": "начало", "scene_description": "x"}])
    assert pack.full()["scenes"] == []
    assert len(pack.full()["dropped_scenes"]) == 1


def test_string_timestamp_is_accepted():
    """Таймкод строкой — штатный ответ модели, его надо принимать."""
    pack = build(scenes=[{"timestamp_sec": "42.5", "scene_description": "x"}])
    assert pack.full()["scenes"][0]["timestamp_sec"] == 42.5


def test_scenes_are_sorted():
    pack = build(scenes=[scene(80.0), scene(10.0), scene(45.0)])
    ts = [s["timestamp_sec"] for s in pack.full()["scenes"]]
    assert ts == sorted(ts)


# ─── Диаризация ──────────────────────────────────────────────────────────────


def test_speaker_by_max_overlap():
    """Говорящий выбирается по наибольшему перекрытию, а не по первому попаданию.

    На стыке реплика транскрипта задевает обоих; «первый подходящий» отдал бы её
    тому, кто успел сказать полслова.
    """
    pack = build(
        transcript=[line(10.0, 20.0)],
        speakers=[
            {"start": 9.0, "end": 11.0, "speaker": "SPEAKER_00"},
            {"start": 11.0, "end": 25.0, "speaker": "SPEAKER_01"},
        ],
    )
    assert pack.full()["transcript"][0]["speaker"] == "SPEAKER_01"


def test_speaker_absent_is_none_not_crash():
    pack = build(transcript=[line(10.0, 20.0)], speakers=[])
    assert pack.full()["transcript"][0]["speaker"] is None


def test_malformed_speaker_turn_ignored():
    pack = build(
        transcript=[line(10.0, 20.0)],
        speakers=[{"start": None, "end": "x", "speaker": "SPEAKER_00"}],
    )
    assert pack.full()["transcript"][0]["speaker"] is None


# ─── Две формы ───────────────────────────────────────────────────────────────


def test_compact_drops_short_lines():
    pack = build(
        transcript=[line(1.0, 2.0, "Да"), line(3.0, 9.0)],
        scenes=[scene(0.0)],
    )
    compact_lines = [ln for e in pack.compact()["timeline"] for ln in e["lines"]]
    assert all(len(ln["text"]) >= MIN_COMPACT_LINE_CHARS for ln in compact_lines)
    assert len(compact_lines) == 1


def test_compact_has_no_transcript_or_diagnostics():
    pack = build(transcript=[line(1.0, 9.0)], scenes=[scene(0.0), scene(500.0)])
    compact = pack.compact()
    assert "transcript" not in compact
    assert "dropped_scenes" not in compact


def test_compact_smaller_on_realistic_volume():
    """Экономия должна быть заметной, а не арифметической.

    Полсотни сцен и три сотни реплик — обычный пятнадцатиминутный ролик.
    """
    pack = build(
        transcript=[line(float(i), float(i) + 0.9) for i in range(300)],
        scenes=[scene(float(i * 6), mood=f"m{i % 3}") for i in range(50)],
        duration_sec=400.0, mode="long",
    )
    full_len = len(json.dumps(pack.full(), ensure_ascii=False))
    compact_len = len(json.dumps(pack.compact(), ensure_ascii=False))
    assert compact_len < full_len / 2, f"экономия всего {full_len / compact_len:.2f}×"
    assert pack.size_ratio() > 2


def test_key_scenes_capped():
    pack = build(
        scenes=[scene(float(i * 5), mood=f"m{i}") for i in range(40)],
        duration_sec=400.0,
    )
    assert sum(1 for s in pack.full()["scenes"] if s["key"]) <= MAX_KEY_SCENES


def test_edges_always_key():
    """Завязка и финал переживают сжатие при любом потолке."""
    scenes = [scene(float(i * 5), mood=f"m{i}") for i in range(40)]
    pack = build(scenes=scenes, duration_sec=400.0)
    kept = {s["timestamp_sec"] for s in pack.full()["scenes"] if s["key"]}
    assert 0.0 in kept
    assert 195.0 in kept


def test_mood_shift_marks_key_scene():
    pack = build(scenes=[scene(0.0, "спокойное"), scene(30.0, "спокойное"),
                         scene(60.0, "паника")], duration_sec=100.0)
    by_ts = {s["timestamp_sec"]: s["key"] for s in pack.full()["scenes"]}
    assert by_ts[60.0] is True


# ─── Инварианты ──────────────────────────────────────────────────────────────


def test_stitched_follows_mode_not_scene_count():
    """Длинный режим сшит даже при одной сцене: сегментация — свойство прогона."""
    assert build(scenes=[scene(0.0)], mode="long").full()["stitched"] is True
    assert build(scenes=[scene(float(i)) for i in range(9)],
                 mode="short").full()["stitched"] is False


def test_determinism():
    kw = dict(
        transcript=[line(float(i), float(i) + 0.9) for i in range(30)],
        scenes=[scene(float(i * 3), mood=f"m{i % 2}") for i in range(20)],
        duration_sec=100.0, mode="long",
    )
    assert build(**kw).full() == build(**kw).full()


def test_input_scenes_not_mutated():
    """Вход не портится: пометка key ставится на копии.

    Иначе повторная склейка того же списка считала бы ключевыми сцены,
    помеченные прошлым прогоном, — и результат зависел бы от истории вызовов.
    """
    src = [scene(0.0), scene(50.0)]
    build(scenes=src, duration_sec=100.0)
    assert all("key" not in s for s in src)


def test_line_counts_match_transcript():
    """Сумма реплик по таймлайну равна их числу в транскрипте: ни потерь, ни дублей."""
    pack = build(
        transcript=[line(float(i * 2), float(i * 2) + 1.5) for i in range(20)],
        scenes=[scene(float(i * 8)) for i in range(5)],
        duration_sec=100.0,
    )
    full = pack.full()
    assert sum(len(e["lines"]) for e in full["timeline"]) == len(full["transcript"])
