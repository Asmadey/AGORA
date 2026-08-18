"""
Распознавание речи моделью parakeet-tdt-0.6b-v3 через ONNX.

─── Зачем вторая модель ──────────────────────────────────────────────────────
Замер на боевом железе 18.08.2026, одна дорожка 161,6 секунды, четыре потока CPU:

    faster-whisper large-v3 (int8)      198,1 с   — 0,8× реального времени
    parakeet-tdt-0.6b-v3 (int8 ONNX)     24,7 с   — 6,5× реального времени

Транскрипция занимала около половины четырёхсотсекундного прогона, так что
разница здесь — это не удобство, а стоимость каждого исследования.

─── Почему ONNX, а не NeMo ───────────────────────────────────────────────────
`onnxruntime` уже лежит в образе, `sherpa-onnx` весит 38,5 МБ, веса в int8 —
671 МБ. Маршрут через NeMo, которого я опасался, тянул бы за собой torch-стек
целиком; он оказался не единственным и не нужным.

─── Почему веса в образе, а не скачиваются ──────────────────────────────────
Скачивание 671 МБ посреди прогона — ровно тот дефект, который чинился для
whisper: он не выглядит нехваткой модели, он выглядит случайно долгой
транскрипцией в первый раз и нормальной во второй, то есть чинит себя сам и не
воспроизводится, когда за него берутся.
"""

from __future__ import annotations

import os
import wave
from functools import lru_cache
from pathlib import Path

from .transcribe import Segment

#: Где лежат веса. Каталог, а не имя модели: `sherpa-onnx` принимает три файла
#: (encoder, decoder, joiner) и словарь токенов, и собирать путь к каждому из
#: имени модели значило бы зашить раскладку чужого репозитория.
DEFAULT_MODEL_DIR = "/opt/models/parakeet-tdt-0.6b-v3"

#: Потоков на распознавание. Столько же, сколько у whisper: обе модели считают
#: на одном и том же процессоре, и разные значения дали бы разное поведение под
#: нагрузкой при одинаковой постановке задачи.
THREADS = 4


def model_dir() -> Path:
    return Path(os.environ.get("PARAKEET_MODEL_DIR") or DEFAULT_MODEL_DIR)


@lru_cache(maxsize=1)
def _model():
    """
    Поднятая модель. Кэшируется: загрузка занимает 4,3 секунды, и платить их на
    каждую дорожку длинного ролика незачем.
    """
    import sherpa_onnx

    d = model_dir()
    files = {
        "encoder": d / "encoder.int8.onnx",
        "decoder": d / "decoder.int8.onnx",
        "joiner": d / "joiner.int8.onnx",
        "tokens": d / "tokens.txt",
    }
    missing = [str(p) for p in files.values() if not p.exists()]
    if missing:
        raise RuntimeError(
            f"веса parakeet не найдены: {', '.join(missing)}. "
            f"Каталог задаётся переменной PARAKEET_MODEL_DIR, по умолчанию "
            f"{DEFAULT_MODEL_DIR}; веса пекутся в образ воркера, чтобы прогон не "
            f"уходил качать 671 МБ посреди работы"
        )

    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(files["encoder"]),
        decoder=str(files["decoder"]),
        joiner=str(files["joiner"]),
        tokens=str(files["tokens"]),
        num_threads=THREADS,
        model_type="nemo_transducer",
    )


def _read_wav(path: str | Path) -> tuple[object, int]:
    """Моно float32 и частота. Ресемплирование не делаем — дорожку готовит ffmpeg."""
    import numpy as np

    with wave.open(str(path)) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise RuntimeError(
                "ожидается моно PCM 16 бит: дорожку готовит media.audio, и другой "
                "формат означает, что её собрали в обход конвейера"
            )
        frames = w.readframes(w.getnframes())
        rate = w.getframerate()
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0, rate


def transcribe(audio: str | Path, language: str | None = None) -> list[Segment]:
    """
    Речь в текст с таймкодами. Форма ответа та же, что у whisper.

    `language` принимается и игнорируется: parakeet-tdt-0.6b-v3 многоязычен и
    определяет язык сам. Параметр оставлен, чтобы вызывающий код не расходился
    между двумя моделями — расхождение сигнатур означало бы `if` в конвейере, а
    он и есть то место, где две реализации однажды разъедутся.
    """
    _ = language
    recognizer = _model()
    audio_data, rate = _read_wav(audio)

    stream = recognizer.create_stream()
    stream.accept_waveform(rate, audio_data)
    recognizer.decode_stream(stream)
    result = stream.result

    texts = list(getattr(result, "segment_texts", None) or [])
    starts = list(getattr(result, "segment_timestamps", None) or [])
    durations = list(getattr(result, "segment_durations", None) or [])

    # Готовых сегментов может не быть — тогда собираем один на весь текст.
    # Пустой ответ законен: в дорожке может не быть речи.
    if not texts:
        text = (result.text or "").strip()
        if not text:
            return []
        stamps = list(getattr(result, "timestamps", None) or [0.0])
        return [Segment(start=float(stamps[0]), end=float(stamps[-1]), text=text)]

    out: list[Segment] = []
    for i, text in enumerate(texts):
        start = float(starts[i]) if i < len(starts) else 0.0
        length = float(durations[i]) if i < len(durations) else 0.0
        out.append(Segment(start=start, end=start + length, text=str(text).strip()))
    return out
