"""
Пересборка расшифровки готового прогона другим движком.

    python3 -m agent_core.maintenance.retranscribe --task <uuid> --dry-run
    python3 -m agent_core.maintenance.retranscribe --task <uuid> --apply

─── Зачем ────────────────────────────────────────────────────────────────────
Прогон 0051 расшифрован parakeet: 59 % покрытия речи и «Сот мальчишек» вместо
«Семьсот мальчишек». Пересчитывать его целиком — час на разбор кадров и двадцать
вызовов модели на персон, при том что меняется одна вещь: текст речи.

Джоба перезапускает ТОЛЬКО распознавание и пересобирает пакет тем же
`build_pack`, каким его собирает конвейер. Своей раскладкой реплик по сценам
она не пользуется намеренно: вторая реализация разошлась бы с первой молча, и
таймлайн после пересборки перестал бы совпадать с таймлайном настоящего прогона.

─── Чего джоба НЕ делает ─────────────────────────────────────────────────────
Отчёт, ответы персон и вердикты судьи остаются прежними: они посчитаны по
СТАРОМУ тексту. После пересборки экран показывает речь, которой персоны не
видели, — и это надо знать, читая такой прогон.

Поэтому операция обратима: прежний пакет целиком сохраняется в поле
`pack_before_retranscribe` того же документа, вместе с именем движка и временем.

─── Про диаризацию ───────────────────────────────────────────────────────────
Заново не гоняем: pyannote на пятидесяти минутах — это час работы, а говорящие
от смены движка ASR не меняются. Разметка восстанавливается из старых реплик
пакета, у каждой из которых уже проставлен `speaker`.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Поле, куда прячется прежний пакет. Одно, а не история: джоба задумана как
#: разовая сверка движков, а хранить в документе неограниченную цепочку версий
#: пакета — это мегабайты на каждый повтор.
BACKUP_FIELD = "pack_before_retranscribe"


def speakers_from_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Разметка говорящих из старых реплик пакета.

    Реплики без `speaker` пропускаются: подставить туда выдуманного участника
    значит приписать слова тому, кого диаризация в этом месте не нашла.
    """
    turns: list[dict[str, Any]] = []
    for line in lines or []:
        speaker = line.get("speaker")
        if not speaker:
            continue
        start, end = line.get("start"), line.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        turns.append({"start": float(start), "end": float(end), "speaker": str(speaker)})
    return turns


def rebuild_pack(
    pack: dict[str, Any],
    *,
    audio: str,
    model: str,
    engine: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """
    Новый пакет: те же сцены, новая речь.

    `engine` подставляется в тестах; в работе берётся по имени модели тем же
    выбором, что и в конвейере, — иначе джоба могла бы считать не тем движком,
    который выбран в настройках.
    """
    from ..content.pack import build_pack

    if engine is None:
        engine = _engine_for(model)

    segments = engine(audio, model=model)
    transcript = [
        {"start": float(s.start), "end": float(s.end), "text": str(s.text)}
        for s in segments
    ]
    if not transcript:
        raise ValueError(
            "расшифровка пуста: движок промолчал на всей дорожке. Это отказ, а "
            "не «речи нет» — пакет не трогаем"
        )

    rebuilt = build_pack(
        transcript=transcript,
        speakers=speakers_from_lines(pack.get("transcript") or []),
        scenes=pack.get("scenes") or [],
        duration_sec=float(pack.get("duration_sec") or 0.0),
        mode="long" if pack.get("stitched") else "short",
        title=str(pack.get("title") or "материал"),
    )
    return rebuilt.full()


def _engine_for(model: str) -> Callable[..., Any]:
    """Тот же выбор движка по имени модели, что и в конвейере."""
    import importlib

    from ..config import GIGAAM_MODELS, ONNX_MODELS

    if model in GIGAAM_MODELS:
        where = "agent_core.asr.gigaam"
    elif model in ONNX_MODELS:
        where = "agent_core.asr.parakeet"
    else:
        where = "agent_core.asr.transcribe"
    module = importlib.import_module(where)
    return lambda audio, model=model: module.transcribe(audio, model=model)


def extract_audio(video: str | Path, dest: str | Path) -> str:
    """
    Дорожка 16 кГц моно — та же форма, что готовит узел `extract_audio`.

    Своим вызовом ffmpeg, а не узлом конвейера: узел принимает состояние графа
    и пишет в рабочий каталог прогона, которого у завершённой задачи давно нет.
    """
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video),
         "-ac", "1", "-ar", "16000", str(dest)],
        check=True,
    )
    return str(dest)


def _load(task_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Документ пакета и строка задачи. Отдельно — чтобы main() читался."""
    import psycopg

    from ..db import tenant_scope
    from ..mongo import mongo_db

    db = mongo_db()
    doc = db["content_packs"].find_one({"task_id": task_id})
    if not doc:
        raise SystemExit(f"пакета материала у прогона {task_id} нет — нечего пересобирать")

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL не задан: неоткуда взять ссылку на исходный ролик")

    tenant_id = doc["tenant_id"]
    with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
        cur.execute("SELECT video_ref, seq_no FROM tasks WHERE id = %s", (task_id,))
        row = cur.fetchone()
    if not row or not row[0]:
        raise SystemExit(f"у прогона {task_id} не записан video_ref — забирать нечего")

    return doc, {"tenant_id": tenant_id, "video_ref": row[0], "seq_no": row[1]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, help="идентификатор прогона")
    parser.add_argument("--model", default=None, help="модель; по умолчанию — из каталога")
    parser.add_argument("--dry-run", action="store_true", help="посчитать и не писать")
    parser.add_argument("--apply", action="store_true", help="записать результат")
    args = parser.parse_args(argv)

    if not args.dry_run and not args.apply:
        parser.error("укажите --dry-run или --apply: молча писать в готовый прогон нельзя")

    from ..config import WHISPER_MODELS
    from ..mongo import mongo_db
    from ..storage import fetch_source

    model = args.model or WHISPER_MODELS[0]
    doc, task = _load(args.task)
    pack = doc["pack"]

    old_lines = pack.get("transcript") or []
    print(f"прогон {task['seq_no'] or args.task}: сцен {len(pack.get('scenes') or [])}, "
          f"реплик сейчас {len(old_lines)}, движок {model}")

    with tempfile.TemporaryDirectory(prefix="retranscribe-") as workdir:
        video = fetch_source(task["video_ref"], workdir=Path(workdir))
        audio = extract_audio(video, Path(workdir) / "audio.wav")
        rebuilt = rebuild_pack(pack, audio=audio, model=model)

    new_lines = rebuilt.get("transcript") or []
    words_before = sum(len(str(ln.get("text", "")).split()) for ln in old_lines)
    words_after = sum(len(str(ln.get("text", "")).split()) for ln in new_lines)
    print(f"реплик станет {len(new_lines)} (было {len(old_lines)}), "
          f"слов {words_after} (было {words_before})")

    if args.dry_run:
        print("--dry-run: ничего не записано")
        return 0

    db = mongo_db()
    db["content_packs"].update_one(
        {"tenant_id": doc["tenant_id"], "task_id": args.task},
        {"$set": {
            "pack": rebuilt,
            # Прежний пакет целиком: отчёт и ответы персон посчитаны по нему, и
            # без возможности вернуться пересборка была бы необратимой правкой
            # готового прогона.
            BACKUP_FIELD: doc["pack"],
            "retranscribed_at": datetime.now(UTC),
            "retranscribed_with": model,
        }},
    )
    print(f"записано. Прежний пакет сохранён в поле {BACKUP_FIELD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
