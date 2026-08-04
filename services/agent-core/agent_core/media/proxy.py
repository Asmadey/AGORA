"""
Proxy-видео и нарезка длинных роликов (задача #14).

Proxy — это перекодированная копия с предсказуемой шкалой времени. Нужна не ради
экономии: покадровый разбор (#16) считает сцены в номерах кадров, и без
постоянного фреймрейта номер кадра не переводится в секунды.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import MediaError
from .probe import _tool, probe

DEFAULT_FPS = 5
DEFAULT_WIDTH = 640
FFMPEG_TIMEOUT = 60 * 30


def make_proxy(
    src: str | Path,
    dst: str | Path,
    fps: int = DEFAULT_FPS,
    width: int = DEFAULT_WIDTH,
) -> Path:
    """
    Собирает proxy с постоянным фреймрейтом и нулевым началом шкалы.

    Два ключа здесь неочевидны и оба обязательны по cdd:

    · `-r {fps}` на ВЫХОДЕ (не на входе) заставляет ffmpeg выдать constant frame
      rate: лишние кадры выбрасываются, недостающие дублируются. Без него
      переменный фреймрейт исходника сохраняется, и r_frame_rate != avg_frame_rate.

    · `-reset_timestamps 1` вместе с `-start_at_zero` сбрасывает start_time
      контейнера. Некоторые mp4 начинаются с ненулевого времени представления,
      и тогда вся шкала таймкодов сдвинута на эту величину — молча, без ошибок.
      Сцена, найденная на 6-й секунде proxy, указала бы на 6 + start_time в
      аудио, и расхождение росло бы незаметно.

    Звук в proxy не нужен: транскрипция работает с отдельной дорожкой
    (extract_audio), а лишний поток только замедляет перекодирование.
    """
    src_p, dst_p = Path(src), Path(dst)
    info = probe(src_p)  # заодно отвергает файл без видеодорожки

    dst_p.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        _tool("ffmpeg"), "-y",
        "-i", str(src_p),
        "-an",                                   # звук отдельно, здесь не нужен
        "-vf", f"scale={width}:-2",              # -2: высота кратна двум, иначе H.264 откажет
        "-r", str(fps),                          # постоянный фреймрейт
        "-fps_mode", "cfr",                      # явно: constant frame rate
        "-start_at_zero",
        "-reset_timestamps", "1",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dst_p),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
    if proc.returncode != 0 or not dst_p.exists():
        raise MediaError(
            f"не удалось собрать proxy: {(proc.stderr or '').strip()[-200:] or 'без объяснения'}"
        )

    # Проверяем результат, а не доверяем коду возврата: ffmpeg возвращает 0 и
    # при частичной записи, а дальше по конвейеру это выглядело бы как странные
    # таймкоды, а не как отказ здесь.
    out = probe(dst_p)
    if out.duration_sec <= 0:
        raise MediaError("proxy собрался пустым: нулевая длительность")
    if abs(out.duration_sec - info.duration_sec) > max(1.0, info.duration_sec * 0.02):
        raise MediaError(
            f"длительность proxy разошлась с исходником: "
            f"{out.duration_sec:.2f}с против {info.duration_sec:.2f}с"
        )
    return dst_p


def segment(
    src: str | Path,
    out_dir: str | Path,
    seconds: int = 600,
    prefix: str = "part",
) -> list[Path]:
    """
    Режет длинное видео на куски по `seconds`.

    Нарезка идёт по ключевым кадрам (`-c copy` + segmenter), поэтому границы
    попадают не ровно на кратные секунды, а на ближайший ключевой кадр. Это
    сознательно: перекодирование ради точной границы стоит дороже, чем
    неточность в доли секунды, а таймкоды внутри куска остаются верными за счёт
    `-reset_timestamps 0` — сквозная шкала сохраняется.

    Возвращает список файлов по порядку. Пустой список означает, что ffmpeg
    ничего не создал, и это ошибка, а не «нечего резать».
    """
    src_p, out_p = Path(src), Path(out_dir)
    out_p.mkdir(parents=True, exist_ok=True)
    pattern = str(out_p / f"{prefix}_%03d.mp4")

    proc = subprocess.run(
        [_tool("ffmpeg"), "-y", "-i", str(src_p),
         "-c", "copy", "-map", "0",
         "-f", "segment", "-segment_time", str(seconds),
         "-reset_timestamps", "0",
         pattern],
        capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
    )
    parts = sorted(out_p.glob(f"{prefix}_*.mp4"))
    if proc.returncode != 0 or not parts:
        raise MediaError(
            f"нарезка не удалась: {(proc.stderr or '').strip()[-200:] or 'файлы не созданы'}"
        )
    return parts
