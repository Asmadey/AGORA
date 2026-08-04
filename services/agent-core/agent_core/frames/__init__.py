"""
Нарезка кадров и VLM-разбор (задача #16).

Превращает proxy-видео из agent_core.media в список разобранных сцен —
структурированное описание того, что происходит на экране, с таймкодами.

─── Конвейер ──────────────────────────────────────────────────────────────
    detect_scenes    границы сцен (PySceneDetect), при нуле склеек — интервал
    extract_frames   по одному кадру на сцену
    dedupe           выбрасывает визуально неотличимые кадры
    build_panels     сетка 2×2 из четырёх кадров — один вызов вместо четырёх
    analyze_panels   VLM с кэшем и капом вызовов

─── Что здесь главное ─────────────────────────────────────────────────────
Не разбор как таковой, а ЧИСЛО ВЫЗОВОВ модели. Это самая дорогая стадия
пайплайна, и три из пяти пунктов cdd задачи — про то, сколько раз модель
вызвана: после дедупликации, при попадании в кэш, при исчерпанном капе.

Отсюда два решения, которые иначе выглядят избыточными:

· клиент VLM передаётся параметром, а не создаётся внутри. Проверить «повторный
  прогон делает 0 новых вызовов» можно только считая вызовы, а считать их можно
  только у подставленного клиента;

· кэш ключуется содержимым панели, шаблоном промпта и именем модели — но не
  идентификатором задачи. Иначе перезапуск исследования (#30) не нашёл бы
  разбор родительской задачи, ради которого кэш и существует.

─── Единственный источник времени ─────────────────────────────────────────
Таймкод сцены проставляется из proxy, а не из ответа модели, даже там, где
промпт просит его вернуть (Decision Log #14). Модель видит только текст, в
который мы сами подставили значение, и вольна его переписать — а цитата в
отчёте, уехавшая на пару секунд, читается как ошибка оценки, а не как дефект
разбора.

─── OCR ───────────────────────────────────────────────────────────────────
Отдельного контура распознавания текста здесь нет и не будет: решение принято
по домену заказчика (нет субтитров и титров) и записано в Decision Log #17.
Текст на экране, если он есть, забирает поле on_screen_text промпта
content.frame_analysis.
"""

from __future__ import annotations

from ..media.errors import MediaError
from .analyze import (
    AnalysisResult,
    Cache,
    CallBudget,
    CostCapExceeded,
    MemoryCache,
    MongoCache,
    QwenVlmClient,
    VlmClient,
    analyze_panels,
    cache_key,
)
from .dedup import DEFAULT_THRESHOLD as DEDUP_THRESHOLD
from .dedup import dedupe, dhash, hamming
from .extract import FRAME_WIDTH, PANEL_SIZE, Panel, build_panels, extract_frames
from .scenes import (
    FALLBACK_INTERVAL_SEC,
    Scene,
    detect_scenes,
    keyframe_timestamps,
)

__all__ = [
    "MediaError",
    # сцены
    "Scene",
    "detect_scenes",
    "keyframe_timestamps",
    "FALLBACK_INTERVAL_SEC",
    # кадры и панели
    "Panel",
    "extract_frames",
    "build_panels",
    "PANEL_SIZE",
    "FRAME_WIDTH",
    # дедупликация
    "dedupe",
    "dhash",
    "hamming",
    "DEDUP_THRESHOLD",
    # разбор
    "analyze_panels",
    "AnalysisResult",
    "VlmClient",
    "QwenVlmClient",
    "Cache",
    "MemoryCache",
    "MongoCache",
    "cache_key",
    "CallBudget",
    "CostCapExceeded",
]
