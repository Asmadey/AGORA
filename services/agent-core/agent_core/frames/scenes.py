"""
Разбиение видео на сцены (задача #16).

Работает по proxy из agent_core.media, а не по исходнику. Причина в шкале
времени: PySceneDetect считает границы в НОМЕРАХ КАДРОВ и переводит их в секунды
делением на фреймрейт. На переменном фреймрейте такое деление даёт неверное
время, и найденная сцена указала бы не на тот момент транскрипта.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..media.errors import MediaError
from ..media.probe import _tool, probe

#: Шаг разбиения ролика, в котором детектор не нашёл ни одной склейки.
#:
#: Величина не косметическая: на ролике без монтажа она одна определяет, сколько
#: панелей уедет в VLM, то есть стоимость прогона. 10 секунд выбраны по нижней
#: границе осмысленности — короче интервал, и соседние панели показывают модели
#: одно и то же.
FALLBACK_INTERVAL_SEC = 10.0

#: Порог детектора содержимого. Ниже — ловятся движения камеры и смены света как
#: склейки; выше — теряются монтажные переходы внутри одной локации.
DEFAULT_THRESHOLD = 27.0


@dataclass(frozen=True)
class Scene:
    """Отрезок видео в секундах от начала proxy."""

    index: int
    start_sec: float
    end_sec: float

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec

    @property
    def midpoint_sec(self) -> float:
        """Момент, с которого берётся представительный кадр сцены.

        Середина, а не начало: первый кадр сцены часто застаёт незавершённый
        переход — затемнение, шторку, полукадр наплыва.
        """
        return self.start_sec + self.duration_sec / 2


def detect_scenes(
    video: str | Path,
    threshold: float = DEFAULT_THRESHOLD,
    fallback_interval_sec: float = FALLBACK_INTERVAL_SEC,
) -> list[Scene]:
    """
    Границы сцен. Пустого списка не возвращает никогда.

    Ноль сцен — штатный исход, а не ошибка: так выглядит любая непрерывная
    съёмка — интервью, запись экрана, монолог на камеру. Именно в этих случаях
    отсутствие fallback било бы больнее всего: разбор молча получил бы ноль
    кадров, ролик остался бы неразобранным, и ни одна проверка не сработала бы —
    ошибки-то не было.

    Поэтому детекция и fallback здесь в одной функции, а не разнесены по
    вызывающему коду: вызывающих будет несколько (#13, #30), и правило «пустого
    не бывает» должно держаться в одном месте.
    """
    duration = probe(video).duration_sec
    cuts = _detect_cuts(video, threshold)

    if not cuts:
        return _by_interval(duration, fallback_interval_sec)

    bounds = [0.0, *cuts, duration]
    scenes: list[Scene] = []
    for start, end in zip(bounds, bounds[1:], strict=False):
        # Нулевые отрезки отбрасываются, поэтому индекс сцены — это её место в
        # итоговом списке, а не в списке границ.
        if end - start > 0.01:
            scenes.append(Scene(index=len(scenes), start_sec=start, end_sec=end))
    return scenes or _by_interval(duration, fallback_interval_sec)


def _detect_cuts(video: str | Path, threshold: float) -> list[float]:
    """Моменты склеек в секундах. Пустой список — склеек нет."""
    try:
        from scenedetect import ContentDetector, SceneManager, open_video
    except ImportError as e:  # pragma: no cover — проверяется отсутствием пакета
        raise MediaError(
            "PySceneDetect не установлен: pip install 'scenedetect[opencv-headless]'"
        ) from e

    video_stream = open_video(str(video))
    manager = SceneManager()
    manager.add_detector(ContentDetector(threshold=threshold))
    manager.detect_scenes(video_stream, show_progress=False)

    # Список сцен от PySceneDetect содержит границы, а не разрезы: первая
    # начинается в нуле. Нам нужны именно разрезы, поэтому начало отбрасывается.
    return [s[0].get_seconds() for s in manager.get_scene_list()[1:]]


def _by_interval(duration_sec: float, interval_sec: float) -> list[Scene]:
    """Равномерная нарезка — запасной план, когда склеек нет."""
    if duration_sec <= 0:
        raise MediaError("нулевая длительность: нечего разбивать на сцены")

    scenes: list[Scene] = []
    start = 0.0
    while start < duration_sec - 0.01:
        end = min(start + interval_sec, duration_sec)
        scenes.append(Scene(index=len(scenes), start_sec=start, end_sec=end))
        start = end
    return scenes


def keyframe_timestamps(scenes: list[Scene]) -> list[float]:
    """Таймкоды представительных кадров — по одному на сцену."""
    return [s.midpoint_sec for s in scenes]


def frame_count(video: str | Path) -> int:
    """Число кадров. Нужно только диагностике, в разборе не участвует."""
    out = subprocess.run(
        [_tool("ffprobe"), "-v", "quiet", "-select_streams", "v:0",
         "-count_packets", "-show_entries", "stream=nb_read_packets",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, timeout=300,
    ).stdout.strip()
    return int(out) if out.isdigit() else 0
