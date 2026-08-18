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

#: Потолок модели, а не настройка. Замер 18.08.2026: дорожка 400 секунд
#: распознаётся, 410 роняет onnxruntime сообщением
#:
#:     /layers.0/self_attn/Add_2 … Attempting to broadcast an axis by a
#:     dimension other than 1. 125 by 5125
#:
#: 5125 — кадров энкодера на 410 секундах (12,5 кадра в секунду), 125 — на
#: сколько превышены 5000. В экспортированном ONNX таблица относительных позиций
#: рассчитана ровно на 5000 кадров. Дорожку длиннее parakeet не примет ни на
#: каком железе, и падение приходит не как «слишком длинный вход», а как
#: внутренняя ошибка среды исполнения.
MODEL_CEILING_SEC = 400.0

#: Длина куска. Не «максимум, который влезает»: внимание квадратично, поэтому
#: короткий кусок дешевле в пересчёте на секунду звука. Тот же замер, время на
#: секунду дорожки:
#:
#:      60 с → 0,103   1,2 ГБ
#:     120 с → 0,138   1,7 ГБ
#:     300 с → 0,207   2,9 ГБ
#:     400 с → 0,240   4,6 ГБ
#:
#: Минута выбрана по обеим шкалам сразу: она и самая дешёвая, и оставляет
#: четырёхкратный зазор до потолка. Пятнадцать минут при таком куске считаются
#: за полторы минуты и занимают полтора гигабайта вместо восьми с половиной.
CHUNK_SEC = 60.0

#: На сколько разрешено подвинуть разрез, чтобы попасть в паузу. Разрез посреди
#: слова стоит одного искажённого слова на стык; в живой речи пауза в пределах
#: трёх секунд находится почти всегда, а когда не находится — режем по месту,
#: потому что потолок важнее одного слова.
SEEK_SEC = 3.0

#: Окно, по которому считается громкость при поиске паузы. 20 миллисекунд —
#: короче слога и длиннее периода основного тона: на первом разрез попадал бы в
#: провал внутри гласной, на втором — мимо самой паузы.
RMS_WINDOW_SEC = 0.02


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


def _cut_points(audio_data, rate: int) -> list[int]:
    """
    Границы кусков в отсчётах: `[0, …, len]`.

    Каждая граница ставится на номинальную длину куска, а затем сдвигается в
    самое тихое место в пределах `SEEK_SEC`. Именно сдвигается, а не ищется
    заново: тишина может не наступить вовсе (сплошная музыка), и алгоритм,
    который ждёт паузу, на таком материале не разрежет ничего и упрётся в
    потолок — то есть починит частый случай ценой падения на редком.

    Перекрытия нет намеренно. Куски с перекрытием требуют склейки повторов, а
    склейка распознанного текста — это отдельная задача с собственными
    ошибками: в неё уезжает то самое слово, ради которого перекрытие и делалось.
    Разрез в паузе решает ту же задачу и не заводит второй источник дефектов.
    """
    import numpy as np

    total = len(audio_data)
    chunk = int(CHUNK_SEC * rate)
    if total <= int(MODEL_CEILING_SEC * rate):
        return [0, total]

    seek = int(SEEK_SEC * rate)
    window = max(1, int(RMS_WINDOW_SEC * rate))

    points = [0]
    while points[-1] + chunk < total:
        nominal = points[-1] + chunk
        lo = max(points[-1] + window, nominal - seek)
        hi = min(total - window, nominal + seek)

        cut = nominal
        if hi > lo:
            zone = audio_data[lo:hi]
            usable = (len(zone) // window) * window
            if usable >= window:
                frames = zone[:usable].reshape(-1, window)
                # Средний квадрат, без корня: корень монотонен, а минимум ищется
                # по порядку, не по значению.
                cut = lo + int(np.argmin((frames * frames).mean(axis=1))) * window
        points.append(min(cut, total))

    points.append(total)
    return points


def transcribe(
    audio: str | Path,
    language: str | None = None,
    model: str | None = None,
) -> list[Segment]:
    """
    Речь в текст с таймкодами. Форма ответа та же, что у whisper.

    `language` принимается и игнорируется: parakeet-tdt-0.6b-v3 многоязычен и
    определяет язык сам. `model` — тоже: веса лежат в каталоге, а не выбираются
    именем. Оба параметра оставлены, чтобы вызывающий код не расходился между
    двумя моделями — расхождение сигнатур означало бы `if` в конвейере, а он и
    есть то место, где две реализации однажды разъедутся.
    """
    _ = language, model
    recognizer = _model()
    audio_data, rate = _read_wav(audio)

    out: list[Segment] = []
    points = _cut_points(audio_data, rate)
    for lo, hi in zip(points, points[1:], strict=False):
        if hi <= lo:
            continue
        offset = lo / rate
        out.extend(_decode(recognizer, audio_data[lo:hi], rate, offset))
    return out


def _decode(recognizer, audio_data, rate: int, offset: float) -> list[Segment]:
    """
    Один кусок. `offset` — его начало в исходной дорожке: распознаватель ведёт
    отсчёт от начала того, что ему дали, и без сдвига второй кусок лёг бы в
    транскрипт поверх первого — не пустым местом, а неверным текстом под
    правильно выглядящими таймкодами.
    """
    stream = recognizer.create_stream()
    stream.accept_waveform(rate, audio_data)
    recognizer.decode_stream(stream)
    result = stream.result

    texts = list(getattr(result, "segment_texts", None) or [])
    starts = list(getattr(result, "segment_timestamps", None) or [])
    durations = list(getattr(result, "segment_durations", None) or [])

    # Готовых сегментов может не быть — тогда собираем один на весь текст.
    # Пустой ответ законен: в куске может не быть речи.
    if not texts:
        text = (result.text or "").strip()
        if not text:
            return []
        stamps = list(getattr(result, "timestamps", None) or [0.0])
        return [
            Segment(
                start=offset + float(stamps[0]),
                end=offset + float(stamps[-1]),
                text=text,
            )
        ]

    out: list[Segment] = []
    for i, text in enumerate(texts):
        start = float(starts[i]) if i < len(starts) else 0.0
        length = float(durations[i]) if i < len(durations) else 0.0
        out.append(
            Segment(
                start=offset + start,
                end=offset + start + length,
                text=str(text).strip(),
            )
        )
    return out
