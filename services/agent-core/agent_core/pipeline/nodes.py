"""
Реализации узлов конвейера.

Каждый узел — тонкая обвязка над модулем своей задачи: `agent_core.media` (#14),
`.asr` (#15), `.frames` (#16), `.content` (#17), `.respondent` (#18). Логики
этапа здесь нет и быть не должно — иначе она оказывается написанной дважды:
один экземпляр вызывается из графа, другой проверяется CDD-тестом задачи, и
расходятся они молча.

─── Импорты внутри функций ──────────────────────────────────────────────────
Намеренно. Модуль импортируется при сборке графа — в том числе в CDD-тесте, где
узлы подменены заглушками. Импорт faster-whisper на уровне модуля тянул бы
CTranslate2 и torch в каждый такой вызов: секунды на импорт и сотни мегабайт
там, где ни одна модель не нужна.

─── Незаконченные этапы отказывают явно ─────────────────────────────────────
Узлы `qa` (#19) и `analytics` (#20) поднимают StageNotImplemented с номером
задачи. Альтернатива — вернуть пустой результат — выглядела бы как успешный
прогон с пустым отчётом, и отличить «QA ничего не нашёл» от «QA не написан»
было бы нечем. Чекпоинтер при этом работает на пользу: когда задача будет
сделана, прогон продолжится с этого узла, а не с транскрипции.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .state import PipelineState


class StageNotImplemented(RuntimeError):
    """Этап конвейера ещё не реализован. Текст обязан называть номер задачи."""


def workdir(state: PipelineState) -> Path:
    """
    Каталог промежуточных файлов прогона.

    По task_id, а не по имени видео: два прогона одного ролика — это два разных
    набора артефактов, и складывать их в один каталог значило бы, что повторный
    запуск читает proxy предыдущего.
    """
    base = Path(os.environ.get("PIPELINE_WORKDIR", "/tmp/agora"))
    path = base / str(state.get("task_id") or "unknown")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _prompt(name: str, state: PipelineState) -> tuple[str, str | None]:
    """
    Шаблон промпта: сначала запиннённая версия прогона, потом файл.

    Возвращает (шаблон, причина деградации). Снимок промптов (Decision Log #10)
    пиннится на запуске (#11) именно затем, чтобы правка в Промпт-студии между
    двумя прогонами не меняла результат задним числом. Молча читать файл, когда
    снимок есть, значило бы обесценить пиннинг: прогон шёл бы по инструкции,
    которая не записана нигде, а отчёт ссылался бы на версию из снимка.

    Поэтому падение назад к файлу возможно, но не бесшумно: причина уходит в
    `degraded` и обязана попасть в отчёт.
    """
    snapshot = state.get("prompts_snapshot") or {}
    pinned = snapshot.get(name)
    dsn = os.environ.get("DATABASE_URL")

    if pinned and dsn:
        import psycopg

        from ..db import tenant_scope

        with psycopg.connect(dsn) as conn, tenant_scope(conn, state["tenant_id"]) as cur:
            cur.execute("SELECT template FROM prompt_versions WHERE id = %s", (pinned["id"],))
            row = cur.fetchone()
            if row:
                return row[0], None

    here = Path(__file__).resolve()
    for parent in here.parents[:6]:
        candidate = parent / "prompts" / f"{name}.md"
        if candidate.exists():
            why = None if not pinned else (
                f"промпт {name}: снимок есть, но версия не прочитана из базы — "
                f"взят файл prompts/{name}.md"
            )
            return candidate.read_text("utf-8"), why
    raise StageNotImplemented(f"промпт {name} не найден ни в снимке, ни в prompts/")


def _source(state: PipelineState) -> Path:
    """
    Исходный файл ролика.

    `video_ref` сейчас трактуется как путь в файловой системе воркера. Загрузка
    из S3 в воркере не написана: клиент S3 живёт только в веб-слое
    (`apps/web/lib/server/s3.ts`), а тянуть его сюда — отдельная работа со своим
    контрактом на подписанные ссылки и политику хранения.

    Отказ здесь явный и с текстом. Молчаливый возврат пустого пути дал бы
    падение ffprobe «файл не найден» на узле probe_and_normalize — то есть
    сообщение об отсутствии файла вместо сообщения об отсутствующей возможности.
    """
    ref = state.get("video_ref")
    if not ref:
        raise ValueError("video_ref пуст: запускать конвейер нечего")
    path = Path(str(ref))
    if not path.exists():
        raise StageNotImplemented(
            f"video_ref={ref!r} не найден на диске воркера. Загрузка из S3 в воркер "
            f"не реализована — сейчас конвейер принимает только локальный путь"
        )
    return path


# ─── Медиа (#14) ─────────────────────────────────────────────────────────────


def probe_and_normalize(state: PipelineState) -> dict[str, Any]:
    from ..media.probe import probe
    from ..media.proxy import make_proxy

    src = _source(state)
    info = probe(src)
    proxy = workdir(state) / "proxy.mp4"
    make_proxy(src, proxy)
    return {"proxy_ref": str(proxy), "duration_sec": info.duration_sec}


def extract_audio(state: PipelineState) -> dict[str, Any]:
    """
    Аудио берётся из ИСХОДНИКА, а не из прокси.

    make_proxy отбрасывает звук (`-an`) намеренно: прокси нужен для сцен и
    кадров, а звуковая дорожка в нём — лишние мегабайты. Вызов на прокси даёт
    «в файле нет звуковой дорожки», и это верное поведение, а не дефект.
    """
    from ..media.audio import extract_audio as extract

    dst = workdir(state) / "audio.wav"
    extract(_source(state), dst)
    return {"audio_ref": str(dst)}


def detect_speech(state: PipelineState) -> dict[str, Any]:
    from ..asr.transcribe import vad_segments

    regions = vad_segments(str(state["audio_ref"]))
    return {"speech_regions": [[start, end] for start, end in regions]}


def segment_video(state: PipelineState) -> dict[str, Any]:
    """Нарезка длинного ролика. Оффсет обязателен: без него таймкоды локальные."""
    from ..media.probe import probe
    from ..media.proxy import segment

    parts = segment(str(state["proxy_ref"]), workdir(state) / "parts", seconds=600)
    segments: list[dict[str, Any]] = []
    offset = 0.0
    for part in parts:
        duration = probe(part).duration_sec
        segments.append({"path": str(part), "offset_sec": offset, "duration_sec": duration})
        offset += duration
    return {"segments": segments}


# ─── Транскрипт (#15) ────────────────────────────────────────────────────────


def transcribe(state: PipelineState) -> dict[str, Any]:
    from ..asr.transcribe import transcribe as run

    segments = run(str(state["audio_ref"]))
    return {
        "transcript_raw": [
            {"start": s.start, "end": s.end, "text": s.text} for s in segments
        ]
    }


def diarize(state: PipelineState) -> dict[str, Any]:
    """
    Диаризация по участкам речи.

    Недоступность pyannote — не отказ прогона: транскрипт без ярлыков спикеров
    остаётся полезным, а исследование про реакцию зрителя, а не про то, кто
    говорит. Поэтому DiarizationUnavailable гасится и попадает в `degraded`,
    откуда отчёт обязан его показать.
    """
    from ..asr.diarize import DiarizationUnavailable
    from ..asr.diarize import diarize as run

    spans = [(a, b) for a, b in state.get("speech_regions", [])]
    try:
        turns = run(str(state["audio_ref"]), spans=spans or None)
    except DiarizationUnavailable as e:
        return {"speaker_turns": [], "degraded": [f"diarize: {e}"]}
    return {
        "speaker_turns": [
            {"start": t.start, "end": t.end, "speaker": t.speaker} for t in turns
        ]
    }


def merge_transcript(state: PipelineState) -> dict[str, Any]:
    """Транскрипт — позвоночник (PRD §8): спикер приписывается реплике, не наоборот."""
    from ..content.pack import _speaker_at

    turns = state.get("speaker_turns", [])
    merged = []
    for line in state.get("transcript_raw", []):
        merged.append({**line, "speaker": _speaker_at(turns, line["start"], line["end"])})
    return {"transcript_diarized": merged}


# ─── Кадры и разбор (#16) ────────────────────────────────────────────────────


def sample_frames(state: PipelineState) -> dict[str, Any]:
    from ..frames.dedup import dedupe
    from ..frames.extract import build_panels, extract_frames
    from ..frames.scenes import detect_scenes, keyframe_timestamps

    proxy = str(state["proxy_ref"])
    scenes = detect_scenes(proxy)
    stamps = keyframe_timestamps(scenes)
    frames = extract_frames(proxy, stamps, workdir(state) / "frames")

    kept = dedupe(frames)
    kept_stamps = [stamps[frames.index(f)] for f in kept]

    panels_dir = workdir(state) / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    refs: list[dict[str, Any]] = []
    for i, panel in enumerate(build_panels(kept, timestamps=kept_stamps)):
        path = panels_dir / f"panel_{i:04d}.jpg"
        path.write_bytes(panel.image)
        refs.append({"path": str(path), "timestamp_sec": panel.timestamp_sec})
    return {"panel_refs": refs}


def analyze_chunks(state: PipelineState) -> dict[str, Any]:
    """MAP по панелям. Результат кладётся на диск: в state ему не место по объёму."""
    from ..frames.analyze import QwenVlmClient, analyze_panels

    refs = state.get("panel_refs", [])
    if not refs:
        raise StageNotImplemented("panel_refs пуст: sample_frames ничего не отдал")

    from ..frames.extract import Panel

    template, degraded = _prompt("content.frame_analysis", state)
    panels = [
        Panel(index=i, timestamp_sec=r["timestamp_sec"], image=Path(r["path"]).read_bytes())
        for i, r in enumerate(refs)
    ]

    result = analyze_panels(panels, client=QwenVlmClient(), prompt=template)
    out = workdir(state) / "chunk_analyses.json"
    out.write_text(json.dumps(result.scenes, ensure_ascii=False), "utf-8")

    update: dict[str, Any] = {"chunk_analyses_ref": str(out)}
    if degraded:
        update["degraded"] = [degraded]
    return update


# ─── Склейка и пакет (#17) ───────────────────────────────────────────────────


def stitch(state: PipelineState) -> dict[str, Any]:
    ref = state.get("chunk_analyses_ref")
    scenes = json.loads(Path(str(ref)).read_text("utf-8")) if ref else []
    return {
        "video_understanding": {
            "scenes": scenes,
            "stitched": state.get("mode") == "long",
        }
    }


def pack(state: PipelineState) -> dict[str, Any]:
    from ..content.pack import build_pack

    understanding = state.get("video_understanding") or {}
    built = build_pack(
        transcript=state.get("transcript_diarized", []),
        speakers=state.get("speaker_turns", []),
        scenes=understanding.get("scenes", []),
        duration_sec=float(state.get("duration_sec") or 0.0),
        mode=str(state.get("mode") or "short"),
        title=str(state.get("task_id")),
    )
    return {"content_pack_full": built.full(), "content_pack_compact": built.compact()}


# ─── Респонденты (#18) ───────────────────────────────────────────────────────


def evaluate_personas(state: PipelineState) -> dict[str, Any]:
    """
    Массовый прогон. В срез персоны уходит КОМПАКТНАЯ форма пакета.

    Полная форма (Decision Log #15) предназначена контрольной подвыборке. При
    500 респондентах разница между «каждому полный пакет» и «полный — подвыборке»
    измеряется разами стоимости запуска.
    """
    from ..respondent.run import QwenRespondentClient, run_survey

    personas = _load_personas(state)
    if not personas:
        raise StageNotImplemented(
            "персоны не загружены: persona_ids пуст или нет доступа к Postgres"
        )

    outcome = run_survey(
        personas=personas,
        pack=state.get("content_pack_compact") or {},
        survey=state.get("survey") or {},
        client=QwenRespondentClient(),
        replication_count=int(state.get("replication_count") or 1),
        artifact_path=workdir(state) / "persona_answers.json",
    )
    update: dict[str, Any] = {"persona_answers": outcome.answers}
    if outcome.failures:
        update["degraded"] = [f"evaluate_personas: отказов {outcome.failures}"]
    return update


def _load_personas(state: PipelineState) -> list[dict[str, Any]]:
    """Персоны арендатора по идентификаторам. Только через tenant_scope — RLS обязателен."""
    ids = state.get("persona_ids") or []
    if not ids:
        return []

    import psycopg

    from ..db import tenant_scope

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return []

    with psycopg.connect(dsn) as conn, tenant_scope(conn, state["tenant_id"]) as cur:
        cur.execute(
            "SELECT id::text, name, dna FROM personas WHERE id = ANY(%s::uuid[])",
            (list(ids),),
        )
        return [{"id": r[0], "name": r[1], "dna": r[2]} for r in cur.fetchall()]


# ─── Ещё не реализованные этапы ──────────────────────────────────────────────


def qa(state: PipelineState) -> dict[str, Any]:
    raise StageNotImplemented(
        "QA-агент не реализован — задача #19. Прогон остановлен на этом узле; "
        "чекпоинт сохранён, продолжение пойдёт отсюда, а не с транскрипции"
    )


def analytics(state: PipelineState) -> dict[str, Any]:
    raise StageNotImplemented(
        "Analytics-агент не реализован — задача #20. Прогон остановлен на этом узле; "
        "чекпоинт сохранён, продолжение пойдёт отсюда, а не с транскрипции"
    )


DEFAULT_NODES = {
    "probe_and_normalize": probe_and_normalize,
    "extract_audio": extract_audio,
    "detect_speech": detect_speech,
    "transcribe": transcribe,
    "diarize": diarize,
    "merge_transcript": merge_transcript,
    "segment_video": segment_video,
    "sample_frames": sample_frames,
    "analyze_chunks": analyze_chunks,
    "stitch": stitch,
    "pack": pack,
    "evaluate_personas": evaluate_personas,
    "qa": qa,
    "analytics": analytics,
}
