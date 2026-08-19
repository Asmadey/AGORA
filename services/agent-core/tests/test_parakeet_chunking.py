"""
Длинная дорожка режется на куски — иначе parakeet не работает вовсе.

─── Замер, из которого это следует ───────────────────────────────────────────
Боевое железо, 18.08.2026, дорожка `15 min.mp4`, четыре потока CPU. Каждая длина
распознавалась в отдельном процессе, пик RSS — `ru_maxrss`:

     60 с →  1,2 ГБ,   6,2 с
    120 с →  1,7 ГБ,  16,6 с
    180 с →  2,5 ГБ,  27,0 с
    300 с →  2,9 ГБ,  62,0 с
    400 с →  4,6 ГБ,  96,1 с
    410 с →  ПАДЕНИЕ

Падение — не нехватка памяти. Это onnxruntime:

    /layers.0/self_attn/Add_2 … Attempting to broadcast an axis by a dimension
    other than 1. 125 by 5125

5125 — число кадров энкодера на 410 секундах (12,5 кадра в секунду), 125 — на
сколько оно превысило 5000. В экспортированном ONNX таблица относительных
позиций рассчитана ровно на 5000 кадров, то есть на 400 секунд. Это ПОТОЛОК
МОДЕЛИ, а не настройка: дорожку длиннее 6 минут 40 секунд parakeet не примет ни
на каком железе.

─── Почему кусок именно такой длины ──────────────────────────────────────────
Внимание квадратично, поэтому короткий кусок не только влезает в память, но и
считается дешевле в пересчёте на секунду звука: 0,103 с/с на кусках по минуте
против 0,240 на кусках по 400 секунд. Резать «на максимум, который влезает» —
худший выбор из возможных.

─── Что проверяется здесь ────────────────────────────────────────────────────
Распознаватель подменяется заглушкой: она записывает, сколько звука ей дали, и
возвращает предсказуемый ответ. Проверяется не текст, а то, что ни один кусок не
превышает потолок и что таймкоды сдвинуты на смещение куска. Тест на настоящей
модели проверил бы то же самое за десять минут и только в образе воркера.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from agent_core.asr import parakeet  # noqa: E402

RATE = 16000


def _wav(path: Path, seconds: float, silence_every: float | None = None) -> Path:
    """
    Дорожка нужной длины. `silence_every` — куда положить паузы: без них резать
    негде, и это тоже законный случай, который обязан отработать.
    """
    t = np.arange(int(seconds * RATE)) / RATE
    data = 0.3 * np.sin(2 * math.pi * 220 * t)
    if silence_every:
        for k in range(1, int(seconds // silence_every) + 1):
            centre = int(k * silence_every * RATE)
            data[max(0, centre - RATE // 2) : centre + RATE // 2] = 0.0
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((data * 32767).astype(np.int16).tobytes())
    return path


class _Stream:
    def __init__(self) -> None:
        self.samples = 0

    def accept_waveform(self, rate: int, data) -> None:
        self.samples += len(data)

    @property
    def result(self):
        seconds = self.samples / RATE

        class R:
            text = "кусок"
            segment_texts = ["кусок"]
            segment_timestamps = [0.0]
            segment_durations = [seconds]
            timestamps = [0.0, seconds]

        return R()


class _Recognizer:
    def __init__(self) -> None:
        self.streams: list[_Stream] = []

    def create_stream(self) -> _Stream:
        s = _Stream()
        self.streams.append(s)
        return s

    def decode_stream(self, stream) -> None:  # noqa: ARG002
        pass


@pytest.fixture
def stub(monkeypatch):
    r = _Recognizer()
    monkeypatch.setattr(parakeet, "_model", lambda: r)
    return r


def test_no_chunk_exceeds_the_model_ceiling(tmp_path: Path, stub):
    """
    Пятнадцать минут — та самая длина, на которой прогон падал у владельца.
    """
    parakeet.transcribe(_wav(tmp_path / "long.wav", 900, silence_every=30))

    assert stub.streams, "распознаватель не был вызван ни разу"
    longest = max(s.samples for s in stub.streams) / RATE
    assert longest <= parakeet.MODEL_CEILING_SEC, (
        f"кусок длиной {longest:.0f} с при потолке модели "
        f"{parakeet.MODEL_CEILING_SEC} с: onnxruntime упадёт на broadcast, и "
        f"выглядеть это будет как случайный сбой воркера"
    )


def test_every_sample_reaches_the_recognizer_exactly_once(tmp_path: Path, stub):
    """
    Куски не должны ни терять звук на стыках, ни подавать его дважды: первое —
    пропавшая реплика, второе — удвоенная фраза в транскрипте.
    """
    seconds = 600
    parakeet.transcribe(_wav(tmp_path / "long.wav", seconds, silence_every=30))

    total = sum(s.samples for s in stub.streams) / RATE
    assert abs(total - seconds) < 0.05, (
        f"распознавателю отдали {total:.2f} с из {seconds}: звук теряется или "
        f"дублируется на стыке кусков"
    )


def test_timecodes_are_shifted_by_chunk_offset(tmp_path: Path, stub):
    """
    Без сдвига каждый кусок начинается с нуля, и вторая половина ролика
    оказывается в транскрипте поверх первой — не пустым местом, а неверным.
    """
    seconds = 600
    out = parakeet.transcribe(_wav(tmp_path / "long.wav", seconds, silence_every=30))

    assert len(out) > 1, "длинная дорожка вернулась одним сегментом"
    starts = [s.start for s in out]
    assert starts == sorted(starts), f"таймкоды не монотонны: {starts[:5]}"
    assert out[-1].end <= seconds + 1, (
        f"последний сегмент кончается на {out[-1].end:.1f} с при длительности "
        f"{seconds} с"
    )
    assert out[-1].start > parakeet.MODEL_CEILING_SEC, (
        "последний кусок не сдвинут: его таймкоды остались от начала дорожки"
    )


def test_short_audio_is_not_chunked(tmp_path: Path, stub):
    """Короткая дорожка обязана идти одним куском — иначе стык на ровном месте."""
    parakeet.transcribe(_wav(tmp_path / "short.wav", 20))
    assert len(stub.streams) == 1, f"дорожка 20 с разрезана на {len(stub.streams)}"


def test_continuous_speech_is_still_chunked(tmp_path: Path, stub):
    """
    Тишины может не быть вовсе — например, музыка на весь ролик. Резать всё
    равно обязаны: отсутствие удобного места для разреза не отменяет потолка.
    """
    parakeet.transcribe(_wav(tmp_path / "solid.wav", 900))
    longest = max(s.samples for s in stub.streams) / RATE
    assert longest <= parakeet.MODEL_CEILING_SEC, (
        f"кусок {longest:.0f} с: при сплошном звуке разрез не сделан вовсе"
    )


# ─── Длина куска выбрана замером качества, а не только стоимости ─────────────
#
# Первая редакция ставила минуту по замеру памяти и скорости. Замер молчал о
# КАЧЕСТВЕ, и на боевом прогоне № 0051 это дало 59 % покрытия речью, «тишину» на
# участках с явным диалогом и английскую бессмыслицу поверх русского звука.
#
# Замер 19.08.2026 на пяти минутах разговорной части: 60 с → 107 слов, 15 с →
# 145 слов при том же времени счёта. Причина в устройстве модели: трансдьюсер
# декодирует кусок как одно высказывание и на длинном куске киношного звука
# схлопывается.

def test_chunk_is_short_enough_for_a_transducer():
    assert parakeet.CHUNK_SEC <= 20, (
        f"кусок {parakeet.CHUNK_SEC} с: на длинном куске parakeet отдаёт одну "
        f"короткую фразу на весь кусок или пустоту — замер 19.08.2026"
    )


def test_chunk_is_not_so_short_that_it_tears_phrases():
    assert parakeet.CHUNK_SEC >= 12, (
        f"кусок {parakeet.CHUNK_SEC} с: ниже пятнадцати качество снова падает — "
        f"куски начинают рвать фразы чаще, чем помогают (136 слов против 145)"
    )


def test_seek_window_is_small_relative_to_the_chunk():
    """
    Сдвиг разреза не должен заметно менять длину куска. При ±3 с на куске в 15
    секунд разброс достигал бы 40 %, и половина кусков оказалась бы за пределами
    измеренного оптимума.
    """
    assert parakeet.SEEK_SEC <= parakeet.CHUNK_SEC / 8, (
        f"сдвиг ±{parakeet.SEEK_SEC} с на куске {parakeet.CHUNK_SEC} с — "
        f"это разброс длины в {2 * parakeet.SEEK_SEC / parakeet.CHUNK_SEC:.0%}"
    )
