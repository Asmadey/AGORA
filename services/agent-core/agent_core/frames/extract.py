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
from typing import Any

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
    """
    Сетка кадров одной сцены, уходящая в модель одним вызовом.

    `image` — готовые байты JPEG, а не путь. Так панель можно положить в кэш и
    посчитать по ней ключ, не завися от того, жив ли ещё временный каталог: на
    момент повторного прогона (#30) файлов родительской задачи давно нет.

    ─── Почему у панели интервал, а не момент ──────────────────────────────
    Панель = сцена. Раньше панель была просто четвёркой подряд идущих кадров, и
    ей проставлялось время ПЕРВОГО из них: описание, полученное по четырём
    моментам, оказывалось привязано к одному. На ролике 2:42 это дало шесть
    описаний вместо двух десятков, а персона, сославшаяся на середину панели,
    получала описание от её начала — отсюда отбраковки по grounding.

    Теперь границы панели — это границы сцены, а кадры берутся внутри неё.
    Описание относится к отрезку, и разъехаться ему не с чем.
    """

    index: int
    #: Начало сцены. Оставлено имя `timestamp_sec` — на него смотрят кэш,
    #: артефакты прежних прогонов и отчёт.
    timestamp_sec: float
    end_sec: float = 0.0
    #: Граница пришла от детектора (монтажная склейка), а не от нарезки длинной
    #: сцены на блоки.
    is_cut: bool = True
    #: Моменты кадров панели в глобальной шкале — по одному на кадр, в том же
    #: порядке. Хранится рядом с кадрами, а не считается заново по индексу:
    #: именно пересчёт по индексу (`stamps[frames.index(f)]`) и разъезжался,
    #: стоило ffmpeg пропустить один кадр.
    frame_times: list[float] = field(default_factory=list)
    frames: list[Path] = field(default_factory=list)
    image: bytes = b""

    @property
    def duration_sec(self) -> float:
        return max(self.end_sec - self.timestamp_sec, 0.0)


def extract_frames(
    video: str | Path,
    timestamps: list[float],
    out_dir: str | Path,
) -> list[tuple[float, Path]]:
    """
    Вытаскивает по одному кадру на каждый таймкод. Возвращает ПАРЫ.

    Пары, а не два списка: связь кадра со временем не должна восстанавливаться
    вызывающим. Она и не восстанавливалась — `stamps[frames.index(f)]` в
    пайплайне давал верное время ровно до первого пропущенного кадра, а дальше
    сдвигал все последующие. Пропуск при этом штатный (см. ниже), то есть
    рассинхрон включался сам собой и ничем себя не выдавал.

    `-ss` стоит ДО `-i` намеренно: так ffmpeg перематывает по индексу, а не
    декодирует ролик с начала до нужной секунды. На двухчасовом материале
    разница между этими двумя режимами — минуты против часов.

    Кадры, которые ffmpeg не отдал, пропускаются молча: таймкод за последним
    кадром — обычное следствие округления длительности, и падать на нём значило
    бы ронять разбор целого ролика из-за миллисекунды в хвосте.
    """
    out_p = Path(out_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    frames: list[tuple[float, Path]] = []
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
            frames.append((ts, dst))

    if not frames:
        raise MediaError(
            f"не удалось извлечь ни одного кадра из {Path(video).name} "
            f"по {len(timestamps)} таймкодам"
        )
    return frames


def panels_for_scenes(
    video: str | Path,
    scenes: list[Any],
    out_dir: str | Path,
    *,
    per_scene: int = PANEL_SIZE,
) -> list[Panel]:
    """
    Одна сцена — одна панель — один вызов модели.

    Кадры берутся ВНУТРИ сцены (`sample_times`), а не подряд по всему ролику:
    так модель видит движение внутри той сцены, которую описывает, и описание
    не может относиться к соседней.

    Сцена, из которой не удалось вытащить ни одного кадра, пропускается: это
    штатный исход на нулевой длительности в хвосте, и ронять разбор ролика
    из-за него незачем. Индекс панели при этом — её место в результате, а не
    номер сцены: пропуск не должен оставлять дыру в нумерации.
    """
    from .scenes import sample_times

    out_p = Path(out_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    panels: list[Panel] = []
    for scene in scenes:
        pairs = []
        scene_dir = out_p / f"scene_{scene.index:04d}"
        try:
            pairs = extract_frames(video, sample_times(scene, per_scene), scene_dir)
        except MediaError:
            continue

        times = [t for t, _ in pairs]
        paths = [p for _, p in pairs]
        panels.append(
            Panel(
                index=len(panels),
                timestamp_sec=scene.start_sec,
                end_sec=scene.end_sec,
                is_cut=bool(getattr(scene, "is_cut", True)),
                frame_times=times,
                frames=paths,
                image=_tile(paths, per_scene),
            )
        )

    if not panels:
        raise MediaError(
            f"из {len(scenes)} сцен не собралось ни одной панели: "
            f"ffmpeg не отдал ни одного кадра"
        )
    return panels


def build_panels(
    frames: list[tuple[float, Path]] | list[Path],
    size: int = PANEL_SIZE,
) -> list[Panel]:
    """
    Собирает кадры в панели по `size` штук — путь без сцен.

    Остаётся для прямых вызовов и проверок: пайплайн ходит через
    `panels_for_scenes`, где границы панели — это границы сцены. Здесь панель
    получает время ПЕРВОГО своего кадра и конец — время последнего; интервал
    поэтому приблизительный, и опираться на него в отчёте не следует.

    Последняя панель может быть неполной — недостающие ячейки заполняются
    чёрным. Отбрасывать хвост нельзя: в нём финал ролика, а именно про финал
    respondent-агентов спрашивают в анкете («досмотрели бы до конца»).
    """
    pairs: list[tuple[float, Path]] = [
        item if isinstance(item, tuple) else (float(i), item)
        for i, item in enumerate(frames)
    ]

    panels: list[Panel] = []
    for i in range(0, len(pairs), size):
        chunk = pairs[i : i + size]
        times = [t for t, _ in chunk]
        paths = [p for _, p in chunk]
        panels.append(
            Panel(
                index=len(panels),
                timestamp_sec=times[0],
                end_sec=times[-1],
                frame_times=times,
                frames=paths,
                image=_tile(paths, size),
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
