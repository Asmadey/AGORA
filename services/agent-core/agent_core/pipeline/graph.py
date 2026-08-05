"""
Граф конвейера (PRD §8) на LangGraph.

Этот модуль отвечает только за ТОПОЛОГИЮ: какие узлы есть, в каком порядке они
идут, куда ведёт маршрутизация и что записывается в прогресс. Работа этапов
живёт в `nodes.py` и дальше — в `agent_core.media`, `.asr`, `.frames`,
`.content`, `.respondent`.

Разделение не косметическое. Оркестратор, внутри которого написана логика
этапа, становится вторым местом, где эта логика существует: одно вызывается из
графа, другое — из CDD-теста задачи, и расходятся они молча. CDD-тест #13
проверяет это отдельным условием — граф не имеет права звать провайдера модели.

─── Параллельные ветки ──────────────────────────────────────────────────────
PRD ставит транскрипцию и диаризацию рядом: `[WhisperX ∥ pyannote] →
merge_transcript`. В LangGraph это два ребра из detect_speech и два ребра в
merge_transcript — фан-ин ждёт обе ветки сам. Последовательная запись дала бы
тот же результат, но вдвое дольше на самом длинном участке прогона.

─── Прогресс пишется вокруг узла, а не внутри ───────────────────────────────
Обёртка `_traced` отбивает RUNNING перед вызовом и DONE после. Писать прогресс
внутри узла значило бы, что каждый новый узел обязан не забыть это сделать, —
а забытый вызов виден не как ошибка, а как «прогресс замер на предыдущем шаге».
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from .progress import ProgressWriter
from .state import PipelineState

#: Узлы конвейера в порядке PRD §8. Порядок значим: по нему экран прогресса
#: (#12) рисует шкалу, не зная устройства графа.
NODES: tuple[str, ...] = (
    "probe_and_normalize",
    "extract_audio",
    "detect_speech",
    "transcribe",
    "diarize",
    "merge_transcript",
    "segment_video",
    "sample_frames",
    "analyze_chunks",
    "stitch",
    "pack",
    "evaluate_personas",
    "qa",
    "analytics",
)

#: Узел, который проходят только длинные прогоны.
LONG_ONLY = "segment_video"


def route(state: PipelineState) -> str:
    """
    Маршрутизация short | long.

    Длинный ролик режется на куски ~10 минут, чтобы транскрипция и разбор кадров
    шли параллельно, а таймкоды сводились обратно в глобальные. Короткий проходит
    мимо: сегментация ролика на три минуты стоит дороже, чем экономит.

    Режим берётся из состояния, а не вычисляется здесь по длительности,
    намеренно. Он задан пользователем на шаге запуска (#11) и попал в ключ
    идемпотентности; вычисление его заново означало бы, что два запуска с
    одинаковыми параметрами могут разойтись по ветке из-за разницы в округлении
    длительности.
    """
    return LONG_ONLY if state.get("mode") == "long" else "sample_frames"


def _traced(
    name: str,
    fn: Callable[[PipelineState], dict[str, Any]],
    progress: ProgressWriter | None,
) -> Callable[[PipelineState], dict[str, Any]]:
    """Узел с прогрессом и превращением исключения в FAILED с причиной."""

    def node(state: PipelineState) -> dict[str, Any]:
        if progress is not None:
            progress.emit(name, "RUNNING")
        try:
            update = fn(state) or {}
        except Exception as e:  # noqa: BLE001 — причина обязана дойти до пользователя
            reason = f"{type(e).__name__}: {e}"
            if progress is not None:
                progress.fail(name, reason)
            raise
        if progress is not None:
            progress.emit(name, "DONE")
        return update

    node.__name__ = name
    return node


def build_graph(
    checkpointer: Any = None,
    nodes: dict[str, Callable[[PipelineState], dict[str, Any]]] | None = None,
    progress: ProgressWriter | None = None,
):
    """
    Собранный граф конвейера.

    `nodes` подменяет реализации — этим пользуется CDD-тест: настоящие узлы
    требуют ffmpeg, Whisper и живую модель, а проверяется в тесте не они, а
    поведение чекпоинтера и маршрутизации.

    `checkpointer=None` даёт граф без сохранения состояния. Это законно для
    разовых прогонов в тестах, но не для Celery: там чекпоинтер обязателен,
    иначе перезапуск воркера начинает пятнадцатиминутную транскрипцию заново.
    """
    from . import nodes as default_nodes

    impl = dict(default_nodes.DEFAULT_NODES)
    if nodes:
        impl.update(nodes)

    missing = [n for n in NODES if n not in impl]
    if missing:
        raise ValueError(f"нет реализации узлов: {', '.join(missing)}")

    graph = StateGraph(PipelineState)
    for name in NODES:
        graph.add_node(name, _traced(name, impl[name], progress))

    graph.add_edge(START, "probe_and_normalize")
    graph.add_edge("probe_and_normalize", "extract_audio")
    graph.add_edge("extract_audio", "detect_speech")

    # Параллельно: распознавание и диаризация по одним и тем же участкам речи.
    graph.add_edge("detect_speech", "transcribe")
    graph.add_edge("detect_speech", "diarize")
    graph.add_edge("transcribe", "merge_transcript")
    graph.add_edge("diarize", "merge_transcript")

    graph.add_conditional_edges(
        "merge_transcript",
        route,
        {LONG_ONLY: LONG_ONLY, "sample_frames": "sample_frames"},
    )
    graph.add_edge(LONG_ONLY, "sample_frames")

    graph.add_edge("sample_frames", "analyze_chunks")
    graph.add_edge("analyze_chunks", "stitch")
    graph.add_edge("stitch", "pack")
    graph.add_edge("pack", "evaluate_personas")
    graph.add_edge("evaluate_personas", "qa")
    graph.add_edge("qa", "analytics")
    graph.add_edge("analytics", END)

    return graph.compile(checkpointer=checkpointer)
