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
Узел `analytics` (#20) поднимает StageNotImplemented с номером задачи.
Альтернатива — вернуть пустой результат — выглядела бы как успешный прогон с
пустым отчётом, и отличить «аналитика ничего не нашла» от «аналитика не
написана» было бы нечем. Чекпоинтер при этом работает на пользу: когда задача
будет сделана, прогон продолжится с этого узла, а не с транскрипции.

Отсюда же граница употребления этого исключения: оно означает «этапа нет», а не
«входа нет». Узел, которому не дали данных, поднимает ValueError — иначе
читающий лог пойдёт искать ненаписанную задачу вместо отказавшего предыдущего
узла.
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
            # Таблица `prompts`, а не `prompt_versions`: версии хранятся строками
            # в ней самой, и снимок пиннит `prompts.id` (apps/web tasks.ts,
            # buildPromptsSnapshot). Таблицы `prompt_versions` не было никогда —
            # запрос к ней падал UndefinedTable через восемьдесят секунд прогона,
            # уже после ffmpeg и транскрипции. Ловится это теперь тестом
            # tests/test_schema_contract.py, а не сквозным прогоном.
            cur.execute("SELECT template FROM prompts WHERE id = %s", (pinned["id"],))
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
    Исходный файл ролика: локальный путь либо объект в S3.

    Веб кладёт видео прямо в S3 подписанной ссылкой и передаёт в задачу ключ
    объекта. До этой правки воркер умел только локальные пути и отказывался
    `StageNotImplemented` — то есть загрузка работала, конвейер работал, а между
    ними не было ничего. Шов нашёл первый сквозной прогон (#22).

    Скачивание вынесено в `agent_core.storage`: оно атомарно и кэшируется в
    рабочем каталоге прогона, потому что граф возобновляется с чекпоинта и
    повторно проходит этот узел.
    """
    from ..storage import fetch_source

    return fetch_source(str(state.get("video_ref") or ""), workdir=workdir(state))


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
    """
    Сцены → панели. Одна сцена — одна панель — один вызов модели.

    ─── Что здесь было ─────────────────────────────────────────────────────
    Кадры брались по одному на сцену (середина), потом склеивались в панели по
    четыре ПОДРЯД — то есть в одну картинку попадали моменты, разнесённые на
    полминуты, а описание получало время первого из них. Отсюда шесть описаний
    на ролик 2:42 и отбраковки по grounding.

    Вторая беда была тише: `kept_stamps = [stamps[frames.index(f)] for f in kept]`.
    `extract_frames` штатно пропускает кадры, которые ffmpeg не отдал, — и после
    первого же пропуска эта строка сдвигала времена всех последующих кадров.
    Рассинхрон включался сам собой и ничем себя не выдавал. Теперь времена
    приезжают парами из `extract_frames` и никем не пересчитываются.

    Дедупликация переехала на уровень панелей (`analyze_panels`): выбрасывать
    кадры внутри сцены нельзя — они там затем и стоят, чтобы модель увидела
    движение, — а вот две подряд идущие одинаковые сцены платить дважды не
    должны.
    """
    from ..frames.extract import panels_for_scenes
    from ..frames.scenes import detect_scenes

    proxy = str(state["proxy_ref"])
    scenes = detect_scenes(proxy)
    panels = panels_for_scenes(proxy, scenes, workdir(state) / "frames")

    panels_dir = workdir(state) / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    refs: list[dict[str, Any]] = []
    for panel in panels:
        path = panels_dir / f"panel_{panel.index:04d}.jpg"
        path.write_bytes(panel.image)
        refs.append({
            "path": str(path),
            "timestamp_sec": panel.timestamp_sec,
            "end_sec": panel.end_sec,
            "is_cut": panel.is_cut,
            "frame_times": panel.frame_times,
            "frames": [str(p) for p in panel.frames],
        })
    return {"panel_refs": refs}


def _vlm_cache(state: PipelineState) -> Any:
    """
    Кэш разбора панелей — в Mongo, между процессами.

    Кэш был написан и не подключён: `analyze_panels` звался без него, и повтор
    прогона (#30) заново оплачивал уже разобранные панели. Дефект тихий вдвойне
    — он не мешает работать, он только стоит денег.

    Недоступная Mongo не роняет разбор: кэш ускоряет, а не определяет результат.
    Возвращается None, и разбор идёт как раньше — платя за всё.
    """
    try:
        from ..frames.analyze import MongoCache
        from ..mongo import mongo_db

        return MongoCache(mongo_db().chunk_analyses, tenant_id=str(state["tenant_id"]))
    except Exception:  # noqa: BLE001 — причина уедет в degraded вызывающего
        return None


def analyze_chunks(state: PipelineState) -> dict[str, Any]:
    """MAP по панелям. Результат кладётся на диск: в state ему не место по объёму."""
    from ..frames.analyze import CallBudget, QwenVlmClient, analyze_panels

    refs = state.get("panel_refs", [])
    if not refs:
        raise StageNotImplemented("panel_refs пуст: sample_frames ничего не отдал")

    from ..frames.extract import Panel

    template, degraded = _prompt("content.frame_analysis", state)
    panels = [
        Panel(
            index=i,
            timestamp_sec=r["timestamp_sec"],
            # Прогоны, начатые до перехода на сцены, несут только начало. Конец
            # у них не выдумывается: пусть интервал вырожден, зато честен.
            end_sec=float(r.get("end_sec") or r["timestamp_sec"]),
            is_cut=bool(r.get("is_cut", True)),
            frame_times=list(r.get("frame_times") or []),
            frames=[Path(p) for p in (r.get("frames") or [])],
            image=Path(r["path"]).read_bytes(),
        )
        for i, r in enumerate(refs)
    ]

    result = analyze_panels(
        panels,
        client=QwenVlmClient(),
        prompt=template,
        # Кэш и кап были написаны и не подключены: разбор платил заново за уже
        # разобранные панели, а жёсткий кап из Настроек (#27) не действовал
        # вовсе — то есть настройка была, а ограничения не было.
        cache=_vlm_cache(state),
        budget=CallBudget.for_task(state.get("settings_snapshot")),
    )
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

    # Промпты — из снимка прогона, а не из файла в образе.
    #
    # Снимок пиннит каждый активный промпт реестра, включая эти два, и делает
    # это ровно затем, чтобы правка в Промпт-студии не меняла прежние прогоны.
    # Пока шаблоны сюда не передавались, run_survey читал файлы: снимок для
    # главного промпта продукта записывался и не использовался, а отчёт
    # ссылался на версию, по которой прогон не шёл. Разойтись эти два источника
    # могут только после первой правки промпта — то есть дефект просыпается в
    # тот день, когда Промпт-студией начинают пользоваться.
    degraded: list[str] = []
    system_template, why = _prompt("respondent.system", state)
    if why:
        degraded.append(why)
    user_template, why = _prompt("respondent.user", state)
    if why:
        degraded.append(why)

    outcome = run_survey(
        personas=personas,
        pack=state.get("content_pack_compact") or {},
        survey=state.get("survey") or {},
        client=QwenRespondentClient(),
        replication_count=int(state.get("replication_count") or 1),
        artifact_path=workdir(state) / "persona_answers.json",
        system_template=system_template,
        user_template=user_template,
    )
    update: dict[str, Any] = {
        "persona_answers": outcome.answers,
        # Заданные вопросы едут в состояние: отчёт обязан показывать те
        # формулировки, которые получили персоны, а не те, что лежат в анкете
        # на момент чтения отчёта.
        "survey_asked": outcome.asked,
    }
    if outcome.failures:
        degraded.append(f"evaluate_personas: отказов {outcome.failures}")
    if degraded:
        update["degraded"] = degraded
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


def _personas_for_segments(
    state: PipelineState, degraded: list[str]
) -> list[dict[str, Any]]:
    """
    Персоны для посегментного разреза — только если срез не пришёл с ответами.

    Ответы нового прогона несут срез в поле `segment`, и тогда база не трогается
    вовсе: лишний запрос на пятьсот строк ради данных, которые уже под рукой.
    Чтение нужно старым прогонам, пересчитанным по сохранённым ответам.

    Отказ чтения не роняет отчёт, а дописывается в `degraded`. Без разреза отчёт
    беднее, но верен; падение здесь стоило бы транскрипции, разбора кадров и всех
    ответов персон, которые уже оплачены.
    """
    answers = state.get("persona_answers") or []
    if any(isinstance(a.get("segment"), dict) and a["segment"] for a in answers):
        return []
    try:
        return _load_personas(state)
    except Exception as exc:  # noqa: BLE001
        degraded.append(
            f"analytics: персоны не прочитаны ({type(exc).__name__}: {exc}); "
            f"посегментного разреза в отчёте не будет"
        )
        return []


# ─── Проверка ответов (#19) ──────────────────────────────────────────────────


def qa(state: PipelineState) -> dict[str, Any]:
    """
    Проверка ответов персон: правила + судья (#19).

    Материалом для проверки заземления берётся КОМПАКТНЫЙ пакет — тот самый,
    который видела персона (#18). Полный пакет дал бы QA больше знания о ролике,
    чем было у отвечавшего: деталь, отсутствующая в компактной форме, для
    персоны выдумана, даже если в полной форме она есть.

    Без ключа провайдера прогон не падает, а идёт одними правилами и говорит об
    этом в `degraded`. Отказ был бы хуже: правила ловят таймкоды за пределами
    ролика и внутренние противоречия — то есть большую часть подсаженных
    дефектов, — и терять их из-за отсутствующего ключа незачем.
    """
    from ..config import ConfigError, QaConfig
    from ..qa.run import run_qa

    answers = state.get("persona_answers") or []
    if not answers:
        # ValueError, а не StageNotImplemented: этап написан, входа нет. Разница
        # не косметическая — по StageNotImplemented читающий лог пойдёт искать
        # ненаписанную задачу вместо отказавшего evaluate_personas.
        raise ValueError(
            "проверять нечего: persona_answers пуст. Узел evaluate_personas не дал "
            "ни одного ответа — смотреть надо его отказ, а не этот"
        )

    degraded: list[str] = []
    judge = None
    try:
        from ..qa.judge import QwenJudgeClient

        judge = QwenJudgeClient()
    except ConfigError as exc:
        degraded.append(f"qa: судья не поднят ({exc}); проверены только правила")

    try:
        policy = QaConfig.from_env()
    except ConfigError as exc:
        policy = None
        degraded.append(f"qa: политика эскалации не прочитана ({exc}); эскалации нет")

    templates: dict[str, str] = {}
    for key in ("qa.consistency", "qa.grounding", "qa.diversity"):
        template, why = _prompt(key, state)
        templates[key] = template
        if why:
            degraded.append(why)

    outcome = run_qa(
        answers=answers,
        pack=state.get("content_pack_compact") or state.get("content_pack_full") or {},
        personas=_load_personas(state),
        survey=state.get("survey") or {},
        judge=judge,
        policy=policy,
        templates=templates,
        artifact_path=workdir(state) / "qa_report.json",
    )

    update: dict[str, Any] = {"qa_flags": outcome.flagged}
    degraded.extend(outcome.degraded)
    if outcome.failures:
        degraded.append(f"qa: отказов судьи {outcome.failures}")
    if degraded:
        update["degraded"] = degraded
    return update


# ─── Аналитика и отчёт (#20) ─────────────────────────────────────────────────


def analytics(state: PipelineState) -> dict[str, Any]:
    """
    Агрегат, точки риска и групповой синтез (#20).

    Числовая часть считается кодом и от модели не зависит — поэтому без ключа
    провайдера узел не падает, а отдаёт отчёт без нарратива и говорит об этом в
    `degraded`. Отказ здесь стоил бы всего прогона: транскрипция, разбор кадров
    и пятьсот ответов персон уже оплачены, а не хватает только текста поверх
    посчитанных чисел.

    `qa_flags` из #19 передаются дальше: ответы, помеченные на перегенерацию, в
    агрегат не идут. Отчёт, построенный на ответах, которые сам же забраковал,
    противоречит себе.
    """
    from ..analytics.report import build_report
    from ..config import ConfigError

    answers = state.get("persona_answers") or []
    if not answers:
        raise ValueError(
            "считать нечего: persona_answers пуст. Узел evaluate_personas не дал "
            "ни одного ответа — смотреть надо его отказ, а не этот"
        )

    degraded: list[str] = []
    model = None
    try:
        from ..analytics.report import QwenAnalystClient

        model = QwenAnalystClient()
    except ConfigError as exc:
        degraded.append(f"analytics: аналитик не поднят ({exc}); собран только агрегат")

    template, why = _prompt("analytics.report", state)
    if why:
        degraded.append(why)

    report = build_report(
        answers=answers,
        pack=state.get("content_pack_compact") or state.get("content_pack_full") or {},
        survey=state.get("survey") or {},
        qa_flags=state.get("qa_flags") or [],
        model=model,
        template=template,
        replication_count=int(state.get("replication_count") or 1),
        artifact_path=workdir(state) / "report.json",
        asked=state.get("survey_asked") or [],
        # Запасной источник среза для посегментного разреза. Ответы нового
        # прогона несут срез сами, и тогда реестр не читается вовсе.
        personas=_personas_for_segments(state, degraded),
    )

    # Отчёт обязан покинуть процесс воркера, иначе интерфейсу его читать
    # неоткуда: состояние графа живёт в чекпоинтере, а report.json — в локальном
    # каталоге контейнера. Отказ записи не роняет прогон: числа уже посчитаны, и
    # терять их из-за недоступной Mongo незачем — но и молчать нельзя, иначе
    # «отчёт не открывается» будет выглядеть как дефект интерфейса.
    try:
        from ..analytics.store import save_report
        from ..mongo import mongo_db

        save_report(
            mongo_db(),
            tenant_id=state["tenant_id"],
            task_id=str(state["task_id"]),
            report=report,
            answers=answers,
            qa_flags=state.get("qa_flags") or [],
        )
    except Exception as exc:  # noqa: BLE001
        degraded.append(
            f"analytics: отчёт не сохранён ({type(exc).__name__}: {exc}); "
            f"интерфейс его не покажет"
        )

    # Статус прогона здесь не выставляется: REPORT_READY ставит tasks.py после
    # того, как граф дошёл до конца. Два места, пишущих один статус, рано или
    # поздно разойдутся, и «отчёт готов» появилось бы раньше, чем отчёт записан.
    update: dict[str, Any] = {"report": report}
    degraded.extend(report.get("degraded") or [])
    if degraded:
        update["degraded"] = degraded
    return update


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
