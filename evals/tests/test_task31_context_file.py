#!/usr/bin/env python3
"""CDD-тест задачи #31 - дополнительный контекст аудитории."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"
CORE = REPO / "services" / "agent-core"
INIT = REPO / "infra" / "postgres" / "init"

CONTEXT_LIB = WEB / "lib" / "context-file.ts"
AUDIENCE_STEP = WEB / "components" / "agora" / "AudienceStep.tsx"
STUDY_PAGE = WEB / "app" / "studies" / "new" / "page.tsx"
TASK_API = WEB / "app" / "api" / "tasks" / "route.ts"
TASKS = WEB / "lib" / "server" / "tasks.ts"
PIPELINE = CORE / "agent_core" / "pipeline" / "nodes.py"
GENERATOR = CORE / "agent_core" / "persona" / "generator.py"
PERSONA_TASKS = CORE / "agent_core" / "persona" / "tasks.py"
PROMPT = REPO / "prompts" / "persona.generate.md"
RLS = INIT / "03_rls.sql"

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

context = read(CONTEXT_LIB)
audience = read(AUDIENCE_STEP)
study = read(STUDY_PAGE)
api = read(TASK_API)
tasks = read(TASKS)
pipeline = read(PIPELINE)
generator = read(GENERATOR)
persona_tasks = read(PERSONA_TASKS)
prompt = read(PROMPT)
rls = read(RLS)

check("шаг «Аудитория» позволяет приложить файл", "type=\"file\"" in audience and "contextFile" in audience)
check("читается содержимое файла, а не только имя", ".text()" in audience and "text:" in audience)
check("файл передаётся в запуск исследования", "audienceContext" in study and "audienceContext" in api and "audienceContext" in tasks and "normalizeContext" in api)
check("пустой и слишком большой файл отклоняются", "файл пуст" in context and "CONTEXT_LIMIT_CHARS" in context)
check("форматный фильтр соответствует проверке файла", "CONTEXT_ACCEPT" in audience and "CONTEXT_EXTENSIONS" in context)
check(
    "принимаются все форматы из acceptance",
    all(ext in context + audience for ext in (".pdf", ".md", ".txt", ".xls", ".xlsx")),
)
check("файл проходит через portrait.distill", "portrait.distill" in api + tasks + pipeline + persona_tasks and "context_file" in api + tasks + pipeline + persona_tasks)
check("портрет из файла попадает в persona.generate отдельной секцией", "audienceContext" in generator and ("audience_context" in prompt or "additional" in prompt.lower()))
check("базовый генератор сохраняет grounding-распределения и калибровку", "segment_distributions" in prompt and "score_means" in generator and "grounding" in prompt.lower())
check("пустой файл имеет безопасную валидацию", "файл пуст" in context and "contextFileError" in audience)
check("таблица контекста другого арендатора закрыта RLS", "audience_context_files" in rls and "FORCE ROW LEVEL SECURITY" in rls and "tenant_id = app.current_tenant()" in rls)
check(
    "конфликт файла должен разрешаться в пользу корпуса с предупреждением",
    "конфликт" in audience.lower() + prompt.lower() + generator.lower()
    and "предупрежд" in audience.lower() + prompt.lower() + generator.lower(),
)

print("\n== Поведенческий уровень ==")

base_url = os.environ.get("BASE_URL")
if not base_url:
    for name in (
        "контекст проходит через живой запуск",
        "пустой контекст не ломает живой запуск",
        "контекст не пересекает арендаторов",
        "reference persona_grounding остаётся green с контекстом",
    ):
        skip(name, "BASE_URL не задан - нужен поднятый сервер, база и готовая аудитория")
else:
    # Эти проверки требуют завершённого платного конвейера и отдельного второго
    # арендатора. Не маскируем отсутствие такой среды под зелёный результат.
    for name in (
        "контекст проходит через живой запуск",
        "пустой контекст не ломает живой запуск",
        "контекст не пересекает арендаторов",
        "reference persona_grounding остаётся green с контекстом",
    ):
        skip(name, "нужны две изолированные команды и завершённые прогоны с корпусом")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#31 Файл дополнительного контекста"))
