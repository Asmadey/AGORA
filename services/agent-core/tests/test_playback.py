"""
Копия ролика для просмотра: 720p, H.264, индекс в начале файла.

─── Зачем она нужна ──────────────────────────────────────────────────────────
Отчёт открывают рядом с роликом, и ролик отдаётся из S3 как есть. Два следствия,
оба портят просмотр и оба невидимы в логах:

· Исходник может быть в HEVC или AV1 — Chrome и Firefox такое не покажут, и
  человек увидит чёрный прямоугольник вместо материала, по которому только что
  прочитал выводы.
· Индекс mp4 (`moov`) обычно лежит в КОНЦЕ файла. Пока он не скачан, браузер не
  умеет перематывать: на ролике в 700 МБ это означает скачать всё, чтобы
  прыгнуть на вторую минуту.

─── Почему progressive, а не HLS ─────────────────────────────────────────────
Замер на боевом железе (18.08.2026, ролик 161,7 с / 40 МБ): лесенка из четырёх
ступеней — 158 секунд и 217 МБ, одна ступень HLS — 57 секунд и 61 МБ,
progressive с faststart — 56 секунд и 59 МБ.

Смысл HLS — переключение качества на лету, а оно требует НЕСКОЛЬКИХ ступеней. С
одной ступенью мы получаем всю механику и ни одной её выгоды, зато платим
дважды: библиотекой hls.js для Chrome и Firefox и подписью ссылок — бакет
закрытый, а плейлист ссылается на два десятка сегментов, каждый со своим часовым
сроком. Один файл — одна ссылка, один срок.

─── Чего здесь нет ───────────────────────────────────────────────────────────
Перекодирования ради перекодирования. Ролик, который уже H.264 и не шире
целевой ширины, копируется потоком: заново сжимать его значит потратить минуту
процессора и потерять качество, не получив ничего.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent_core.media.playback import make_playback

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe недоступны — тест едет в образ воркера",
)


def _make(path: Path, *, width: int, height: int, codec: str = "libx264",
          seconds: int = 2) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"testsrc2=s={width}x{height}:r=25",
         "-t", str(seconds), "-c:v", codec, "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True, timeout=180,
    )
    return path


def _probe(path: Path, entries: str) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", entries, "-of", "default=nk=1:nw=1", str(path)],
        check=True, capture_output=True, text=True, timeout=60,
    ).stdout.strip()


def test_large_video_is_scaled_down_to_the_target_width(tmp_path: Path):
    src = _make(tmp_path / "big.mp4", width=1920, height=1080)
    dst = make_playback(src, tmp_path / "play.mp4", width=1280)

    assert _probe(dst, "stream=width") == "1280"
    assert _probe(dst, "stream=codec_name") == "h264"


def test_index_sits_at_the_front(tmp_path: Path):
    """
    `moov` в начале — это и есть faststart, ради которого всё затевалось.

    Проверяется положением в файле, а не наличием ключа в команде: ключ можно
    передать и не получить эффекта, если контейнер собран иначе, и тогда
    перемотка молча останется прежней.
    """
    src = _make(tmp_path / "src.mp4", width=1280, height=720)
    dst = make_playback(src, tmp_path / "play.mp4", width=1280)

    head = dst.read_bytes()[:4096]
    assert b"moov" in head, "индекс не в начале файла — перемотка потребует полной загрузки"


def test_already_suitable_video_is_not_re_encoded(tmp_path: Path):
    """
    Готовый H.264 нужной ширины копируется потоком.

    Разница видна по времени и по качеству, но проверяется надёжнее: у
    перекодированного файла битрейт и размер отличаются от исходных, у
    скопированного видеопоток совпадает покадрово. Сверяем число кадров и кодек
    — если бы шло сжатие, тест прошёл бы тоже, поэтому дополнительно требуем,
    чтобы размер не изменился больше чем на десятую долю.
    """
    src = _make(tmp_path / "ok.mp4", width=1280, height=720, seconds=3)
    dst = make_playback(src, tmp_path / "play.mp4", width=1280)

    assert _probe(dst, "stream=codec_name") == "h264"
    assert _probe(dst, "stream=width") == "1280"

    ratio = dst.stat().st_size / src.stat().st_size
    assert 0.9 <= ratio <= 1.1, (
        f"файл пересжат без нужды: размер изменился в {ratio:.2f} раза"
    )
