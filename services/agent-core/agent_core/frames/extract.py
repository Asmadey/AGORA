"""
Извлечение кадров и сборка панелей (задача #16).

─── Почему панель, а не кадр ──────────────────────────────────────────────
Модель получает не одиночную картинку, а сетку 2×2 из четырёх последовательных
кадров. Причины две, и обе про качество, а не про экономию.

· Одиночный кадр не отличает «человек стоит» от «человек садится». Действие
  видно только в изменении между кадрами, а промпт content.frame_analysis
  требует поле actions.

· Четыре кадра в одном изображении — это один вызов вместо четырёх. Экономия
  здесь следствие, а не цель, но именно она делает разбор длинного ролика
  выполнимым в пределах капа из Настроек (#27).

Больше четырёх в панель не кладём: на 2×2 каждый кадр занимает половину стороны
изображения, при 3×3 — треть, и мелкие детали (выражение лица, текст на экране)
перестают различаться после масштабирования на входе модели.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..media.errors import MediaError
from ..media.probe import _tool

#: Кадров в одной панели. Сетка 2×2 — см. шапку модуля.
PANEL_SIZE = 4

#: Ширина кадра для панели. Совпадать с шириной proxy не обязано: proxy нужен
#: детектору сцен, а сюда идёт то, что увидит модель.
FRAME_WIDTH = 512

FFMPEG_TIMEOUT = 300


@dataclass
class Panel:
    """Сетка кадров, уходящая в модель одним вызовом.

    `image` — готовые байты JPEG, а не путь. Так панель можно положить в кэш и
    посчитать по ней ключ, не завися от того, жив ли ещё временный каталог: на
    момент повторного прогона (#30) файлов родительской задачи давно нет.
    """

    index: int
    timestamp_sec: float
    frames: list[Path] = field(default_factory=list)
    image: bytes = b""


def extract_frames(
    video: str | Path,
    timestamps: list[float],
    out_dir: str | Path,
) -> list[Path]:
    """
    Вытаскивает по одному кадру на каждый таймкод.

    `-ss` стоит ДО `-i` намеренно: так ffmpeg перематывает по индексу, а не
    декодирует ролик с начала до нужной секунды. На двухчасовом материале
    разница между этими двумя режимами — минуты против часов.

    Кадры, которые ffmpeg не отдал, пропускаются молча: таймкод за последним
    кадром — обычное следствие округления длительности, и падать на нём значило
    бы ронять разбор целого ролика из-за миллисекунды в хвосте.
    """
    out_p = Path(out_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    frames: list[Path] = []
    for i, ts in enumerate(timestamps):
        dst = out_p / f"frame_{i:05d}.jpg"
        subprocess.run(
            [_tool("ffmpeg"), "-y", "-v", "error",
             "-ss", f"{max(ts, 0.0):.3f}", "-i", str(video),
             "-frames:v", "1",
             "-vf", f"scale={FRAME_WIDTH}:-2",
             "-q:v", "3", str(dst)],
            capture_output=True, timeout=FFMPEG_TIMEOUT,
        )
        if dst.exists() and dst.stat().st_size > 0:
            frames.append(dst)

    if not frames:
        raise MediaError(
            f"не удалось извлечь ни одного кадра из {Path(video).name} "
            f"по {len(timestamps)} таймкодам"
        )
    return frames


def build_panels(
    frames: list[Path],
    size: int = PANEL_SIZE,
    timestamps: list[float] | None = None,
) -> list[Panel]:
    """
    Собирает кадры в панели по `size` штук.

    Последняя панель может быть неполной — недостающие ячейки заполняются
    чёрным. Отбрасывать хвост нельзя: в нём финал ролика, а именно про финал
    respondent-агентов спрашивают в анкете («досмотрели бы до конца»).

    `timestamps` — время первого кадра каждой панели в глобальной шкале proxy.
    Без него панель нумеруется по порядку, и ссылка из отчёта на таймкод
    становится невозможной.
    """
    panels: list[Panel] = []
    for i in range(0, len(frames), size):
        chunk = frames[i : i + size]
        ts = timestamps[i] if timestamps and i < len(timestamps) else float(i)
        panels.append(
            Panel(
                index=len(panels),
                timestamp_sec=ts,
                frames=chunk,
                image=_tile(chunk, size),
            )
        )
    return panels


def _tile(frames: list[Path], size: int) -> bytes:
    """Склеивает кадры в одно изображение сеткой."""
    if not frames:
        return b""

    cols = 2 if size >= 2 else 1
    rows = (size + cols - 1) // cols

    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        # Фильтр tile читает последовательность по маске имени, поэтому кадры
        # переименовываются в непрерывный ряд: исходные имена приходят от
        # дедупликации с пропусками, а на пропуске ffmpeg остановит чтение.
        for i, f in enumerate(frames, start=1):
            shutil.copy(f, tmpd / f"in_{i:03d}.jpg")

        dst = tmpd / "panel.jpg"
        proc = subprocess.run(
            [_tool("ffmpeg"), "-y", "-v", "error",
             "-framerate", "1", "-i", str(tmpd / "in_%03d.jpg"),
             "-vf", f"tile={cols}x{rows}:padding=4:color=black",
             "-frames:v", "1", "-q:v", "3", str(dst)],
            capture_output=True, timeout=FFMPEG_TIMEOUT,
        )
        if not dst.exists() or dst.stat().st_size == 0:
            why = (proc.stderr or b"").decode("utf-8", "replace").strip()[-160:]
            raise MediaError(
                f"не удалось собрать панель из {len(frames)} кадров: "
                f"{why or 'пустой вывод'}"
            )
        return dst.read_bytes()
