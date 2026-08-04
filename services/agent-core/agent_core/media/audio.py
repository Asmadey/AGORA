"""
Извлечение звуковой дорожки (задача #14, потребитель — #15).

Формат вывода задан требованиями faster-whisper и pyannote, а не вкусом:
16 кГц, моно, PCM 16 бит. Оба принимают и другое, но внутри всё равно приводят
к этому виду — разница в том, что при явном приведении здесь шкала времени
одна и та же для транскрипта и для диаризации, а при неявном каждый пересчитает
её сам, и таймкоды разойдутся.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import MediaError
from .probe import _tool, probe

SAMPLE_RATE = 16_000
FFMPEG_TIMEOUT = 60 * 30


def extract_audio(
    src: str | Path,
    dst: str | Path,
    sample_rate: int = SAMPLE_RATE,
) -> Path:
    """
    Достаёт звук в wav 16 кГц моно.

    `-vn` убирает видео, `-ac 1` сводит в моно. Моно здесь не упрощение:
    диаризация различает говорящих по голосу, а не по каналам, и стереодорожка
    с одинаковым содержимым в обоих каналах только удваивает объём.

    `-af aresample=async=1` выравнивает дорожку по времени, если в исходнике
    есть разрывы: без этого звук «съезжает» относительно видео на длинных
    роликах, и таймкод транскрипта перестаёт совпадать с таймкодом сцены.

    Файл без звуковой дорожки — предсказуемый отказ, а не пустой wav. Пустой
    файл прошёл бы дальше по конвейеру и дал бы пустой транскрипт, который
    невозможно отличить от «в ролике молчание».
    """
    src_p, dst_p = Path(src), Path(dst)
    info = probe(src_p)
    if not info.has_audio:
        raise MediaError(
            "в файле нет звуковой дорожки — транскрипция невозможна; "
            "проверьте исходный ролик"
        )

    dst_p.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [_tool("ffmpeg"), "-y",
         "-i", str(src_p),
         "-vn",
         "-ac", "1",
         "-ar", str(sample_rate),
         "-af", "aresample=async=1",
         "-c:a", "pcm_s16le",
         "-start_at_zero", "-reset_timestamps", "1",
         str(dst_p)],
        capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
    )
    if proc.returncode != 0 or not dst_p.exists() or dst_p.stat().st_size == 0:
        raise MediaError(
            f"не удалось извлечь аудио: {(proc.stderr or '').strip()[-200:] or 'файл пуст'}"
        )
    return dst_p
