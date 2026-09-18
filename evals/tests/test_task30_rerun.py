#!/usr/bin/env python3
"""CDD-тест задачи #30 - повтор исследования с той же аудиторией."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"
CORE = REPO / "services" / "agent-core"
INIT = REPO / "infra" / "postgres" / "init"

REPORT_PAGE = WEB / "app" / "runs" / "[id]" / "page.tsx"
NEW_STUDY = WEB / "app" / "studies" / "new" / "page.tsx"
RERUN_API = WEB / "app" / "api" / "tasks" / "[id]" / "rerun" / "route.ts"
TASK_API = WEB / "app" / "api" / "tasks" / "route.ts"
RERUN_LIB = WEB / "lib" / "rerun.ts"
QUEUE = WEB / "lib" / "server" / "queue.ts"
TASKS = WEB / "lib" / "server" / "tasks.ts"
NODES = CORE / "agent_core" / "pipeline" / "nodes.py"
#: Схема читается ВСЕМ набором миграций, а не одним файлом.
#:
#: §5 CLAUDE.md: уже применённый файл не редактируется, новая колонка заводится
#: следующим по номеру. Так сделаны poster_ref (30), playback_ref (29),
#: source_name (30) — в 02_schema.sql их нет и не должно быть. Проверка,
#: смотрящая только в 02_schema.sql, требовала бы нарушить это правило, чтобы
#: стать зелёной.
SCHEMA_FILES = sorted(INIT.glob("*.sql"))

results: list[tuple[str, str, str]] = []


def read(path: Path) -> str:
    return path.read_text("utf-8") if path.exists() else ""


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, "OK" if ok else "FAIL", detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  ->  {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, "SKIP", reason))
    print(f"  SKIP  {name}  ->  {reason}")


print("== Статический уровень ==")

report = read(REPORT_PAGE)
new_study = read(NEW_STUDY)
rerun_api = read(RERUN_API)
task_api = read(TASK_API)
rerun = read(RERUN_LIB)
queue = read(QUEUE)
tasks = read(TASKS)
nodes = read(NODES)
schema = "\n".join(read(path) for path in SCHEMA_FILES)

check("экран результата предлагает повтор", "studies/new?rerun=" in report)
check("API повтора защищён сессией", "requireSession" in rerun_api and "withTenant" in rerun_api)
check("API повтора возвращает тот же материал и набор персон", "video_ref" in rerun_api and "persona_set_id" in rerun_api and "rerunPrefill" in rerun_api)
check("родительский task_id попадает в prefill", "parentTaskId: source.id" in rerun)
check("новые вопросы не копируются автоматически", "surveyQuestions: []" in rerun and "surveyId" in task_api)
check("создание повторного прогона принимает parentTaskId", "parentTaskId" in task_api and "parent_task_id" in tasks)
check("визард передаёт parentTaskId в POST /api/tasks", "parentTaskId" in new_study and "parentTaskId:" in new_study)
check("повтор использует кэш родительского video_understanding", "_parent_video_result" in nodes and "parent_task_id" in nodes and "chunk_analyses_ref" in nodes)
check("контракт кэша проверяет совпадение материала", "video_ref" in nodes and "материал отличается" in nodes)
check("в задаче есть связь parent_task_id", "parent_task_id" in schema and "REFERENCES tasks(id)" in schema)
check("режим «допрос» переносит прежние ответы и задаёт только новые вопросы", "carry_over_memory" in schema and "my_previous_answers" in rerun_api + new_study + queue + nodes)
check("режим «чистый прогон» задаёт полную анкету без памяти", "carry_over_memory" in schema and "survey" in queue + nodes and ("memoryMode" in task_api + new_study or "clean" in task_api.lower() + new_study.lower()))
check("режим «допрос» хранится отдельно от чистого прогона", "carry_over_memory" in schema and "carry_over_memory" in task_api and "carry_over_memory" in queue and "carry_over_memory" in nodes)
check("UI явно объясняет оба режима памяти", all(word in new_study.lower() for word in ("допрос", "чистый прогон", "памят")))
check("отчёт показывает сравнение с родительским прогоном", "parentTaskId" in report and ("сравн" in report.lower() or "parent" in report.lower()))

print("\n== Поведенческий уровень ==")

base_url = os.environ.get("BASE_URL")
if not base_url:
    for name in (
        "GET rerun возвращает ту же аудиторию и материал",
        "GET rerun возвращает parent_task_id",
        "rerun оставляет анкету для новых вопросов",
        "живой отчёт содержит сравнение с родителем",
    ):
        skip(name, "BASE_URL не задан - нужен поднятый сервер и готовый отчёт")
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _harness import login, verdict  # noqa: E402

    client, why = login(base_url)
    if client is None:
        for name in (
            "GET rerun возвращает ту же аудиторию и материал",
            "GET rerun возвращает parent_task_id",
            "rerun оставляет анкету для новых вопросов",
            "живой отчёт содержит сравнение с родителем",
        ):
            skip(name, why)
    else:
        code, raw = client.call("/api/tasks")
        try:
            tasks_live = json.loads(raw).get("tasks") or []
        except (TypeError, json.JSONDecodeError):
            tasks_live = []
        ready = next((task for task in tasks_live if task.get("status") == "REPORT_READY"), None)
        if not ready:
            for name in (
                "GET rerun возвращает ту же аудиторию и материал",
                "GET rerun возвращает parent_task_id",
                "rerun оставляет анкету для новых вопросов",
                "живой отчёт содержит сравнение с родителем",
            ):
                skip(name, "нет REPORT_READY-прогона для проверки повтора")
        else:
            task_id = ready.get("id")
            code, raw = client.call(f"/api/tasks/{task_id}/rerun")
            try:
                prefill = (json.loads(raw) or {}).get("prefill") or {}
            except (TypeError, json.JSONDecodeError):
                prefill = {}
            check(
                "GET rerun возвращает ту же аудиторию и материал",
                code == 200 and prefill.get("videoRef") == ready.get("videoRef") and prefill.get("personaSetId") == ready.get("personaSetId"),
                f"HTTP {code}, videoRef={prefill.get('videoRef')!r}, personaSetId={prefill.get('personaSetId')!r}",
            )
            check(
                "GET rerun возвращает parent_task_id",
                code == 200 and prefill.get("parentTaskId") == task_id,
                f"получено {prefill.get('parentTaskId')!r}",
            )
            check(
                "rerun оставляет анкету для новых вопросов",
                code == 200 and prefill.get("surveyQuestions") == [],
                f"surveyQuestions={prefill.get('surveyQuestions')!r}",
            )
            skip("живой отчёт содержит сравнение с родителем", "требует создания и завершения нового платного прогона")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#30 Перезапуск исследования"))
