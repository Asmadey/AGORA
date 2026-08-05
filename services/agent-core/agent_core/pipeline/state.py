"""
Состояние конвейера (PRD §8).

Набор полей выписан из PRD дословно и менять его по вкусу нельзя: на эти имена
ссылаются узлы графа, снимок прогресса и веб-слой. Переименование поля здесь —
не рефакторинг, а разрыв контракта, который проявится не при сборке, а на
прогоне, когда узел получит пустое значение вместо данных предыдущего этапа.

─── Почему TypedDict, а не dataclass или pydantic-модель ────────────────────
LangGraph сливает возврат узла со состоянием как словарь: узел возвращает
частичное обновление `{"audio_ref": ...}`, а не целый объект. TypedDict — ровно
эта семантика, причём с проверкой имён на уровне тайпчекера. Dataclass
потребовал бы конструировать полный объект в каждом узле, а pydantic — платить
валидацией на каждом слиянии, которых за прогон сотни.

─── Почему ссылки, а не данные ──────────────────────────────────────────────
`chunk_analyses_ref`, `content_pack_full` и прочее с суффиксом `_ref` — это
ключи в Mongo/S3, а не содержимое. Причина в чекпоинтере: состояние сериализуется
после каждого узла, и разбор кадров 15-минутного ролика внутри state означал бы
мегабайты JSON, переписываемые по десять раз за прогон.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

Mode = Literal["short", "long"]

#: Статусы прогона. Совпадают с CHECK-ограничением колонки `tasks.status`
#: (02_schema.sql): расхождение здесь означало бы, что воркер выставляет статус,
#: который база отвергнет — то есть отказ в самом конце прогона.
STATUS_QUEUED = "QUEUED"
STATUS_RUNNING = "RUNNING"
STATUS_REPORT_READY = "REPORT_READY"
STATUS_FAILED = "FAILED"


class PipelineState(TypedDict, total=False):
    """Состояние прогона по PRD §8. `total=False` — узлы обновляют его частями."""

    task_id: str
    tenant_id: str
    mode: Mode
    video_ref: str | None

    # ── Медиа (#14) ─────────────────────────────────────────────────────────
    proxy_ref: str | None
    audio_ref: str | None
    duration_sec: float | None
    #: Участки речи Silero VAD в глобальных таймкодах: [(начало, конец), …].
    speech_regions: list[list[float]]
    #: Куски длинного видео: [{"path": …, "offset_sec": …, "duration_sec": …}].
    segments: list[dict[str, Any]]

    # ── Транскрипт (#15) ────────────────────────────────────────────────────
    #
    # Две ветки PRD §8 (`WhisperX ∥ pyannote`) пишут в разные каналы, а
    # merge_transcript сводит их в transcript_diarized. Общий канал на две
    # параллельные ветки LangGraph отверг бы как конфликт записи — и был бы прав:
    # какая из веток «победила», зависело бы от порядка завершения.
    transcript_raw: list[dict[str, Any]]
    speaker_turns: list[dict[str, Any]]
    transcript_diarized: list[dict[str, Any]]

    # ── Кадры и разбор (#16, #17) ───────────────────────────────────────────
    #: Панели на диске: [{"path": …, "timestamp_sec": …}]. В состоянии лежат
    #: пути, а не изображения: чекпоинт сериализуется после каждого узла, и
    #: мегабайты JPEG внутри него переписывались бы десятки раз за прогон.
    panel_refs: list[dict[str, Any]]
    chunk_analyses_ref: str | None
    video_understanding: dict[str, Any] | None
    content_pack_full: dict[str, Any] | None
    content_pack_compact: dict[str, Any] | None

    # ── Аудитория и опрос (#9, #10, #18) ────────────────────────────────────
    persona_ids: list[str]
    survey: dict[str, Any] | None
    replication_count: int
    persona_answers: list[dict[str, Any]]

    # ── QA и аналитика (#19, #20) ───────────────────────────────────────────
    qa_flags: list[dict[str, Any]]
    report: dict[str, Any] | None

    # ── Служебное ───────────────────────────────────────────────────────────
    status: str
    progress: dict[str, Any]
    #: Снимок промптов прогона (Decision Log #10): {ключ: {id, version, sha256}}.
    #: Пиннится на запуске (#11); узлы читают шаблон по нему, а не из файлов.
    prompts_snapshot: dict[str, Any]
    #: Этапы, отработавшие не полностью. Пустой список — не то же самое, что
    #: отсутствие поля: отчёт обязан показать, что VLM отвалился, даже если
    #: остальное собралось.
    #:
    #: Список НАКАПЛИВАЕТСЯ (operator.add), а не перезаписывается. Обычный канал
    #: LangGraph хранит последнее значение — и отметка о деградации диаризации
    #: исчезла бы, как только следующий узел записал бы свою. Отчёт показал бы
    #: одну проблему из трёх, причём последнюю по времени, а не главную.
    degraded: Annotated[list[str], operator.add]
    error: str | None


def new_state(
    *,
    task_id: str,
    tenant_id: str,
    mode: Mode = "short",
    video_ref: str | None = None,
    persona_ids: list[str] | None = None,
    survey: dict[str, Any] | None = None,
    replication_count: int = 1,
    prompts_snapshot: dict[str, Any] | None = None,
) -> PipelineState:
    """
    Начальное состояние прогона.

    Списочные поля инициализируются пустыми списками, а не остаются
    отсутствующими: узел, который делает `state["persona_answers"].append(...)`,
    на отсутствующем ключе упадёт посреди прогона, а не при сборке.
    """
    return PipelineState(
        task_id=task_id,
        tenant_id=tenant_id,
        mode=mode,
        video_ref=video_ref,
        proxy_ref=None,
        audio_ref=None,
        duration_sec=None,
        speech_regions=[],
        segments=[],
        transcript_raw=[],
        speaker_turns=[],
        transcript_diarized=[],
        panel_refs=[],
        chunk_analyses_ref=None,
        video_understanding=None,
        content_pack_full=None,
        content_pack_compact=None,
        persona_ids=list(persona_ids or []),
        survey=survey,
        replication_count=replication_count,
        persona_answers=[],
        qa_flags=[],
        report=None,
        status=STATUS_QUEUED,
        progress={},
        prompts_snapshot=dict(prompts_snapshot or {}),
        degraded=[],
        error=None,
    )
