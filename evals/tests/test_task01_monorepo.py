#!/usr/bin/env python3
"""
CDD-тест задачи #1 — «Инфраструктура и монорепо (Docker)».

Красный до реализации, зелёный после. Проверяет ровно то, что записано в
`acceptance` задачи #1 в evals/state/tasks.json, и ничего сверх того.

Запуск (stdlib-only, как и check.py):
    python evals/tests/test_task01_monorepo.py

Exit 0 = green. Exit 1 = red, с перечнем невыполненных условий.

Что НЕ проверяется здесь: поднятие docker compose и healthchecks — это метрика
`compose_health` в check.py, она требует запущенного демона и живёт в среде
пользователя. Здесь — только статически проверяемый контракт раскладки и
валидность конфигурации.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

failures: list[str] = []
notes: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {detail}"))
    if not ok:
        failures.append(name)


def skip(name: str, reason: str) -> None:
    print(f"  SKIP  {name}  -> {reason}")
    notes.append(f"{name}: {reason}")


# ── 1. Раскладка монорепо (Decision Log #4) ──────────────────────────────
print("== раскладка монорепо ==")

REQUIRED_DIRS = [
    "apps/web",
    "services/agent-core",
    "packages/shared",
    "infra",
    "evals",
    "data/grounding",
    "prompts",
    "docs",
]
for d in REQUIRED_DIRS:
    check(f"каталог {d}", (ROOT / d).is_dir(), "не найден")

check(
    "apps/web — это перенесённый Next.js (есть package.json)",
    (ROOT / "apps/web/package.json").is_file(),
    "apps/web/package.json отсутствует",
)
check(
    "старый agora-unified/ больше не существует в корне",
    not (ROOT / "agora-unified").exists(),
    "agora-unified всё ещё на месте — перенос не выполнен или выполнен копированием",
)

# ── 2. Артефакты, которые обязаны были переехать без потерь ──────────────
print("== перенос артефактов ==")

check(
    "верификатор на месте: evals/check.py",
    (ROOT / "evals/check.py").is_file(),
    "не найден",
)
check(
    "граф задач на месте: evals/state/tasks.json",
    (ROOT / "evals/state/tasks.json").is_file(),
    "не найден",
)
check(
    "фикстура short_60s.mp4 на месте",
    (ROOT / "evals/fixtures/short_60s.mp4").is_file(),
    "не найдена",
)

corpus = ROOT / "data/grounding/unified_respondent_sessions.json"
if corpus.is_file():
    try:
        data = json.loads(corpus.read_text(encoding="utf-8"))
        check(
            "grounding-корпус переехал целиком (165 записей)",
            isinstance(data, list) and len(data) == 165,
            f"записей: {len(data) if isinstance(data, list) else 'не список'}",
        )
    except Exception as e:  # noqa: BLE001
        check("grounding-корпус читается как JSON", False, str(e)[:120])
else:
    check("grounding-корпус на месте", False, f"{corpus} не найден")

prompts_dir = ROOT / "prompts"
if prompts_dir.is_dir():
    keys = sorted(p.stem for p in prompts_dir.glob("*.md"))
    # На момент переезда монорепо ключей было 13, и проверка стояла на равенстве.
    # Равенство здесь неверно по смыслу: задача #1 сторожит ПОТЕРЮ при переносе,
    # а появление новых промптов — штатная работа Промпт-студии (#26), ради
    # которой она и сделана. Равенство превращало каждый новый промпт в красный
    # тест чужой задачи, то есть подталкивало править проверку вместо разбора.
    # Порог снизу ловит ровно то, что должен: пропажу.
    MIGRATED = 13
    check(
        f"реестр промптов переехал целиком (не меньше {MIGRATED} ключей)",
        len(keys) >= MIGRATED,
        f"найдено {len(keys)}: {keys}",
    )
else:
    check("реестр промптов на месте", False, "prompts/ не найден")

# ── 3. Гигиена секретов ──────────────────────────────────────────────────
print("== гигиена секретов ==")

check(
    "env.env с живым ключом убран из-под будущего git",
    not (ROOT / "env.env").exists(),
    "env.env всё ещё в корне репозитория",
)
check(
    "корневой .gitignore существует",
    (ROOT / ".gitignore").is_file(),
    "не найден",
)
if (ROOT / ".gitignore").is_file():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    check(
        ".gitignore закрывает .env-файлы, но пропускает .env.example",
        (".env" in gi) and ("!.env.example" in gi or "!*.env.example" in gi),
        "нет правил для .env / нет исключения для .env.example",
    )

# ── 4. Контракт сборки: worker ───────────────────────────────────────────
print("== services/agent-core ==")

core = ROOT / "services/agent-core"
check(
    "есть pyproject.toml",
    (core / "pyproject.toml").is_file(),
    "не найден",
)
check(
    "есть пакет agent_core",
    (core / "agent_core" / "__init__.py").is_file(),
    "не найден",
)
check(
    "есть хотя бы один тест",
    any(core.glob("tests/test_*.py")) if core.is_dir() else False,
    "tests/test_*.py не найдены",
)

# ── 5. Контракт TS↔Python: canonical JSON Schema ─────────────────────────
print("== packages/shared ==")

check(
    "есть каталог схем packages/shared/schemas",
    (ROOT / "packages/shared/schemas").is_dir(),
    "не найден",
)

# ── 6. Docker Compose ────────────────────────────────────────────────────
print("== docker compose ==")

compose = ROOT / "infra/docker-compose.yml"
check("infra/docker-compose.yml существует", compose.is_file(), "не найден")

if compose.is_file():
    raw = compose.read_text(encoding="utf-8")
    # Проверяем наличие сервисов текстово — без PyYAML, чтобы тест остался stdlib-only.
    for svc in ["postgres", "mongo", "valkey", "web", "worker"]:
        check(f"сервис {svc} объявлен", f"{svc}:" in raw, "нет в compose")
    check(
        "у инфраструктурных сервисов есть healthcheck",
        raw.count("healthcheck:") >= 3,
        f"healthcheck встречается {raw.count('healthcheck:')} раз, ожидалось >= 3",
    )
    check(
        "версии зафиксированы (Postgres 18 / Mongo 8 / Valkey 9.1)",
        "postgres:18" in raw and "mongo:8" in raw and "valkey/valkey:9.1" in raw,
        "образы не соответствуют PRD §15",
    )
    check(
        "секреты берутся из env, а не зашиты",
        "${" in raw,
        "нет подстановок ${...} — вероятно, значения захардкожены",
    )

    if shutil.which("docker"):
        try:
            # compose.yml объявляет секреты через ${VAR:?...} (раздел 5 CLAUDE.md —
            # секреты только из env, не захардкожены). `config` не поднимает
            # контейнеры и не читает эти значения содержательно — ему достаточно,
            # что переменная существует. Без .env.local (как на GitHub Actions)
            # интерполяция падает на первой обязательной переменной, и валидный
            # compose выглядит как невалидный. Плейсхолдеры здесь — не секреты.
            dummy_required = {
                "POSTGRES_PASSWORD": "ci-placeholder",
                "AGORA_APP_PASSWORD": "ci-placeholder",
                "AGORA_SHARE_PASSWORD": "ci-placeholder",
                "MONGO_PASSWORD": "ci-placeholder",
                "AUTH_SECRET": "ci-placeholder",
                "MONGODB_URL": "mongodb://ci:ci@localhost:27017/ci",
                "VALKEY_URL": "redis://localhost:6379",
                "OPENAI_API_KEY": "ci-placeholder",
            }
            r = subprocess.run(
                ["docker", "compose", "-f", str(compose), "config", "--quiet"],
                capture_output=True, text=True, timeout=120,
                cwd=ROOT, env={**os.environ, **dummy_required, "COMPOSE_PROJECT_NAME": "agora"},
            )
            check(
                "docker compose config валиден",
                r.returncode == 0,
                (r.stderr or "")[-200:],
            )
        except Exception as e:  # noqa: BLE001
            check("docker compose config валиден", False, str(e)[:150])
    else:
        skip("docker compose config валиден", "docker CLI недоступен в этой среде")

# ── 7. Верификатор запускается из нового корня ───────────────────────────
print("== верификатор из нового корня ==")

if (ROOT / "evals/check.py").is_file():
    try:
        r = subprocess.run(
            [sys.executable, "evals/check.py"],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        # exit 1 ожидаем и это нормально: подсистемы ещё не построены.
        # Важно, что скрипт отработал и выдал разбираемый JSON.
        parsed = None
        try:
            parsed = json.loads(r.stdout)
        except Exception:  # noqa: BLE001
            pass
        check(
            "check.py отрабатывает из корня монорепо и печатает JSON",
            parsed is not None and r.returncode in (0, 1),
            f"exit {r.returncode}, stdout не JSON: {(r.stdout or '')[:120]}",
        )
        if parsed:
            names = {x["name"] for x in parsed.get("results", [])}
            check(
                "check.py видит граф задач по новому пути",
                any(
                    x["name"] == "tasks_done" and x["status"] != "skip"
                    for x in parsed["results"]
                ),
                "tasks_done = skip, значит tasks.json не найден по новому пути",
            )
            check(
                "check.py видит grounding-корпус по новому пути",
                not any(
                    x["name"] == "persona_grounding"
                    and "dataset not found" in (x.get("detail") or "")
                    for x in parsed["results"]
                ),
                "persona_grounding не нашёл датасет",
            )
            # Раньше здесь стояло len(names) == 15. Добавление метрики
            # (schema_drift, prompts_editable) ломало CDD-тест задачи #1: проверка
            # держалась за число, а не за содержание, и рост верификатора
            # выглядел как регрессия монорепо. Правильный инвариант — каждая
            # метрика, закреплённая за задачей графа полем verifies, есть в отчёте.
            graph_path = ROOT / "evals" / "state" / "tasks.json"
            owned: set[str] = set()
            if graph_path.is_file():
                graph = json.loads(graph_path.read_text(encoding="utf-8"))
                tasks = graph.get("tasks", graph) if isinstance(graph, dict) else graph
                owned = {m for t in tasks for m in (t.get("verifies") or [])}
            missing = owned - names
            check("в отчёте есть каждая метрика, закреплённая за задачей графа",
                  not missing, f"нет: {sorted(missing)}")
            check("метрик не меньше, чем закреплено за задачами",
                  len(names) >= len(owned), f"метрик {len(names)}, закреплено {len(owned)}")
    except Exception as e:  # noqa: BLE001
        check("check.py отрабатывает из корня монорепо", False, str(e)[:150])

# Вердикт общий для всех тестов — см. _harness.verdict. Прежде GREEN печатался
# при любом числе SKIP, и «проверено» не отличалось от «пропущено».
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict_lists  # noqa: E402

sys.exit(verdict_lists(failures, notes, len(oks) if "oks" in dir() else 0, "#1"))
