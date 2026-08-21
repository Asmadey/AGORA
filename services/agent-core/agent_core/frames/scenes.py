"""
Разбиение видео на сцены (задача #16).

Работает по proxy из agent_core.media, а не по исходнику. Причина в шкале
времени: PySceneDetect считает границы в НОМЕРАХ КАДРОВ и переводит их в секунды
делением на фреймрейт. На переменном фреймрейте такое деление даёт неверное
время, и найденная сцена указала бы не на тот момент транскрипта.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..media.errors import MediaError
from ..media.probe import _tool, probe

#: Порог детектора содержимого. Ниже — ловятся движения камеры и смены света как
#: склейки; выше — теряются монтажные переходы внутри одной локации.
DEFAULT_THRESHOLD = 27.0

#: Короче этого сцена не бывает: склейка, случившаяся раньше, — дребезг
#: быстрого монтажа, а не смена сцены. Кусочек приклеивается к предыдущей.
#:
#: Без этого правила клиповая нарезка даёт десятки границ подряд, и каждая
#: становится отдельным вызовом модели за описание вида «то же самое, но на
#: полкадра позже».
MIN_SCENE_SEC = 2.0

#: Длиннее этого сцена не бывает: она режется на равные блоки.
#:
#: Спикер на одном слайде три минуты — это одна сцена по монтажу и три минуты
#: без единого таймкода внутри. Персона, сославшаяся на середину, получила бы
#: описание от начала, а судья справедливо увидел бы несовпадение. Ровно этот
#: дефект — корень отбраковок по grounding.
MAX_SCENE_SEC = 30.0


@dataclass(frozen=True)
class Scene:
    """
    Отрезок видео в секундах от начала proxy.

    `is_cut` различает две границы, которые иначе слились бы в одну: смену
    сцены, найденную детектором, и разрез длинной сцены на блоки. По первой на
    таймлайне рисуется монтажный переход, по второй — продолжение той же сцены.
    Показать в отчёте монтаж, которого в материале нет, значит соврать о
    материале.
    """

    index: int
    start_sec: float
    end_sec: float
    is_cut: bool = True

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
    max_scene_sec: float = MAX_SCENE_SEC,
) -> list[Scene]:
    """
    Границы сцен. Пустого списка не возвращает никогда.

    Ноль склеек — штатный исход, а не ошибка: так выглядит любая непрерывная
    съёмка — интервью, запись экрана, монолог на камеру. Отдельного
    fallback-интервала для этого случая больше нет: `build_scenes` режет любой
    отрезок длиннее `max_scene_sec` на равные блоки, и ролик без монтажа просто
    оказывается одним таким отрезком. Одно правило вместо двух — и та же
    гарантия: список не бывает пустым.
    """
    duration = probe(video).duration_sec
    cuts = _detect_cuts(video, threshold)
    return build_scenes(cuts, duration, max_scene_sec=max_scene_sec)


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


def build_scenes(
    cuts: list[float],
    duration_sec: float,
    *,
    min_sec: float = MIN_SCENE_SEC,
    max_scene_sec: float = MAX_SCENE_SEC,
) -> list[Scene]:
    """
    Склейки → сцены. Встык, без дыр, от нуля до конца.

    Дыра — это кусок ролика, которого нет ни в одном описании: персона его не
    видела, и отчёт об этом не сообщает. Перекрытие — момент с двумя разными
    описаниями, и какое покажет экран, зависит от порядка. Поэтому сборка идёт
    от границ, а не от списка отрезков: границы нельзя нечаянно оставить с
    зазором.

    Два правила из постановки, оба про то, чтобы описание относилось к тому,
    что в нём описано:

    · граница ближе `min_sec` к предыдущей отбрасывается — кусочек уходит в
      предыдущую сцену (дребезг быстрого монтажа);
    · отрезок длиннее `max_scene_sec` режется на РАВНЫЕ блоки. Равные, а не
      «тридцать, тридцать, остаток»: хвост в две секунды получил бы описание
      наравне с полноценным блоком, и на таймлайне это выглядело бы как событие
      там, где ничего не произошло.
    """
    if duration_sec <= 0:
        raise MediaError("нулевая длительность: нечего разбивать на сцены")

    # ── Границы: ноль, принятые склейки, конец ──────────────────────────────
    bounds = [0.0]
    for cut in sorted(cuts):
        if cut <= bounds[-1] + min_sec or cut >= duration_sec:
            continue
        bounds.append(cut)
    # Хвост короче минимума не заводит своей сцены: последним, что видит
    # персона, стало бы описание одного кадра, а анкета спрашивает про финал.
    if len(bounds) > 1 and duration_sec - bounds[-1] < min_sec:
        bounds.pop()
    bounds.append(duration_sec)

    scenes: list[Scene] = []
    for start, end in zip(bounds, bounds[1:], strict=False):
        blocks = max(1, math.ceil((end - start) / max_scene_sec - 1e-9))
        step = (end - start) / blocks
        for block in range(blocks):
            scenes.append(
                Scene(
                    index=len(scenes),
                    start_sec=start + block * step,
                    # Конец последнего блока берётся из границы, а не из
                    # накопленной суммы шагов: иначе плавающая точка оставляет
                    # микрозазор перед следующей сценой, и «встык» перестаёт
                    # быть правдой на длинном материале.
                    end_sec=end if block == blocks - 1 else start + (block + 1) * step,
                    is_cut=block == 0,
                )
            )
    return scenes


def sample_times(scene: Scene, count: int) -> list[float]:
    """
    Моменты кадров внутри сцены — по серединам равных долей.

    Не по границам: первый кадр сцены часто застаёт незавершённый переход
    (затемнение, шторку, полукадр наплыва), последний — начало следующего.
    Модель, увидевшая переход, описывает его как содержание сцены.

    Кадров несколько, а не один, потому что действие видно только в изменении:
    по одному кадру «садится» неотличимо от «сидит», а промпт требует поле
    `actions`.
    """
    if count <= 0:
        return []
    step = scene.duration_sec / count
    return [round(scene.start_sec + step * (i + 0.5), 6) for i in range(count)]


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
