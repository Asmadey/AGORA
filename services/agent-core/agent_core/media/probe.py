"""
Съём параметров видео через ffprobe (задача #14).

Первый пункт cdd: файл без видеодорожки обязан отвергаться внятной ошибкой, а
не падением. Разница практическая — падение по KeyError или StopIteration
уезжает в лог как «внутренняя ошибка», и пользователь получает пятисотку вместо
объяснения, что он загрузил аудиофайл.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import FFmpegMissing, MediaError

FFPROBE_TIMEOUT = 60


@dataclass(frozen=True)
class VideoInfo:
    """Параметры ролика, нужные дальше по конвейеру."""

    duration_sec: float
    width: int
    height: int
    codec: str
    fps: float
    has_audio: bool
    start_time: float
    size_bytes: int

    @property
    def is_variable_fps(self) -> bool:
        """
        Признак переменного фреймрейта.

        Для PySceneDetect это принципиально: он считает сцены в номерах кадров,
        а перевод номера в секунды при VFR неверен. Такой ролик обязан пройти
        через make_proxy до покадрового разбора.
        """
        return self._r_fps != self._avg_fps

    _r_fps: float = 0.0
    _avg_fps: float = 0.0


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FFmpegMissing(
            f"{name} не найден. Это поломка развёртывания, а не проблема файла: "
            f"образ обязан содержать ffmpeg (см. infra/worker.Dockerfile)."
        )
    return path


def _ratio(value: str | None) -> float:
    """Переводит «25/1» в 25.0. Ноль в знаменателе — это отсутствие данных."""
    if not value or "/" not in value:
        try:
            return float(value or 0)
        except ValueError:
            return 0.0
    num, _, den = value.partition("/")
    try:
        d = float(den)
        return float(num) / d if d else 0.0
    except ValueError:
        return 0.0


def probe(path: str | Path) -> VideoInfo:
    """
    Читает параметры файла. Бросает MediaError, если это не пригодное видео.

    Проверок две, и обе про реальные случаи, а не про теорию: файла может не
    быть на диске (ошибка пути), и в файле может не быть видеодорожки (человек
    загрузил подкаст вместо ролика).
    """
    p = Path(path)
    if not p.exists():
        raise MediaError(f"файл не найден: {p}")

    proc = subprocess.run(
        [_tool("ffprobe"), "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", str(p)],
        capture_output=True, text=True, timeout=FFPROBE_TIMEOUT,
    )
    if proc.returncode != 0:
        raise MediaError(
            f"ffprobe не смог прочитать файл: {(proc.stderr or '').strip()[:200] or 'без объяснения'}"
        )

    try:
        meta = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise MediaError(f"ffprobe вернул невалидный JSON: {e}") from e

    streams = meta.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        # Ровно тот случай из cdd. Текст обязан называть причину: пользователь
        # должен понять, что загрузил не то, а не гадать над «ошибкой обработки».
        raise MediaError(
            "в файле нет видеодорожки — вероятно, это аудиофайл; "
            "загрузите видео (mp4, mov, avi)"
        )

    fmt = meta.get("format") or {}
    r_fps = _ratio(video.get("r_frame_rate"))
    avg_fps = _ratio(video.get("avg_frame_rate"))

    return VideoInfo(
        duration_sec=float(fmt.get("duration") or video.get("duration") or 0.0),
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        codec=str(video.get("codec_name") or ""),
        fps=avg_fps or r_fps,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        start_time=float(fmt.get("start_time") or 0.0),
        size_bytes=int(fmt.get("size") or 0),
        _r_fps=r_fps,
        _avg_fps=avg_fps,
    )
