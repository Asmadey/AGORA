#!/usr/bin/env python3
"""
CDD-тест задачи #12 — «Экран прогресса (SSE)».

CDD (из tasks.json):
  SSE-поток отдаёт смену узлов пайплайна;
  обрыв соединения переподключается без потери состояния;
  FAILED отображается с причиной.

Приёмка: прогресс пишется в Valkey узлами LangGraph, отдаётся через SSE
(Decision Log #3).

─── Почему «без потери состояния» проверяется снимком, а не переподключением ─
EventSource переподключается сам — это делает браузер, и проверять тут нечего.
Проверять надо другое: что при подключении сервер СРАЗУ отдаёт текущее
состояние, а не молчит до следующей смены узла.

Разница видна на реальном сценарии. Пользователь запустил исследование и закрыл
вкладку. Через десять минут вернулся. Транскрипция идёт, и до следующего
события — минуты. Поток, отдающий только новые события, всё это время показывает
пустой экран, неотличимый от зависшего прогона. Поэтому Pub/Sub не может быть
единственным источником: он ничего не помнит, и подписчик, пришедший позже,
не получит уже отправленное.

─── Почему имена ключа и канала — часть контракта ───────────────────────────
Их пишет воркер (agent_core/pipeline/progress.py), а читает веб. Совпадать они
обязаны побайтово, и разойтись могут молча: веб подпишется на канал, которого
никто не публикует, поток останется пустым, и выглядеть это будет как
«исследование не стартовало», а не как опечатка в префиксе.

─── Почему список узлов — один на воркер и веб ──────────────────────────────
Шкалу прогресса рисует веб, а порядок узлов знает граф. Продублированный в TS
список расходится с графом при первой же правке конвейера — и расхождение не
ломает ничего заметного: шкала просто показывает не тот этап. Поэтому список
лежит в packages/shared и читается обеими сторонами.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import ApiClient, live_env, login  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"
CORE = REPO / "services" / "agent-core"
SHARED_NODES = REPO / "packages" / "shared" / "pipeline" / "nodes.json"

SSE_ROUTE = WEB / "app" / "api" / "tasks" / "[id]" / "progress" / "route.ts"
PROGRESS_PAGE = WEB / "app" / "runs" / "[id]" / "progress" / "page.tsx"
PROGRESS_VIEW = WEB / "components" / "agora" / "ProgressView.tsx"
VALKEY_LIB = WEB / "lib" / "server" / "valkey.ts"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if not ok and detail else ""))


def skip(name: str, why: str) -> None:
    results.append((name, SKIP, why))
    print(f"  SKIP  {name}  →  {why}")


def read(path: Path) -> str:
    return path.read_text("utf-8") if path.exists() else ""


print("\n#12 — Экран прогресса (SSE)\n")

route_src = read(SSE_ROUTE)
page_src = read(PROGRESS_PAGE)
view_src = read(PROGRESS_VIEW)
valkey_src = read(VALKEY_LIB)

# ─── Маршрут ────────────────────────────────────────────────────────────────

print("SSE-маршрут")

check("маршрут app/api/tasks/[id]/progress существует", SSE_ROUTE.exists())
check("отдаёт text/event-stream", "text/event-stream" in route_src)
check(
    "runtime = nodejs",
    bool(re.search(r'runtime\s*=\s*"nodejs"', route_src)),
    "Edge не умеет TCP-соединение к Valkey",
)
check(
    "dynamic = force-dynamic",
    bool(re.search(r'dynamic\s*=\s*"force-dynamic"', route_src)),
    "иначе Next отдаст закешированный поток",
)
check(
    "поток закрыт сессией арендатора",
    "requireSession" in route_src,
    "без этого прогресс чужого прогона доступен по прямой ссылке",
)
check(
    "прогон проверяется на принадлежность арендатору",
    "withTenant" in route_src or "tenant" in route_src.lower(),
)

print("\nБез потери состояния")

check(
    "при подключении сразу отдаётся снимок из ключа",
    "snapshot" in route_src,
    "иначе вернувшийся пользователь видит пустой экран до следующего события",
)
check(
    "подписка на канал, а не опрос в цикле",
    "subscribe" in route_src,
)
check(
    "отписка при обрыве соединения",
    "unsubscribe" in route_src or "cancel" in route_src or "abort" in route_src.lower(),
    "иначе каждый ушедший клиент оставляет за собой соединение к Valkey",
)

# ─── Контракт с воркером ────────────────────────────────────────────────────

print("\nКонтракт с воркером")

worker_progress = read(CORE / "agent_core" / "pipeline" / "progress.py")
worker_prefix = re.search(r'_PREFIX\s*=\s*"([^"]+)"', worker_progress)
prefix = worker_prefix.group(1) if worker_prefix else None

web_progress = valkey_src + read(WEB / "lib" / "server" / "progress.ts")
check(
    "префикс ключа и канала совпадает с воркером",
    bool(prefix) and prefix in web_progress,
    f"воркер пишет в {prefix!r}, в вебе такого префикса нет",
)

check("packages/shared/pipeline/nodes.json существует", SHARED_NODES.exists())

if SHARED_NODES.exists():
    shared = json.loads(SHARED_NODES.read_text("utf-8"))
    node_names = [n["name"] if isinstance(n, dict) else n for n in shared["nodes"]]

    graph_src = read(CORE / "agent_core" / "pipeline" / "graph.py")
    check(
        "граф воркера читает список узлов из packages/shared",
        "nodes.json" in graph_src,
        "иначе шкала в интерфейсе и конвейер расходятся молча",
    )
    check(
        "веб читает тот же список",
        "nodes.json" in (view_src + page_src + read(WEB / "lib" / "pipeline-nodes.ts")),
    )
    check(
        "в списке все узлы PRD §8",
        len(node_names) == 14 and "probe_and_normalize" in node_names
        and "analytics" in node_names,
        f"узлов {len(node_names)}",
    )
else:
    for name in ("граф воркера читает список узлов из packages/shared",
                 "веб читает тот же список", "в списке все узлы PRD §8"):
        check(name, False, "нет packages/shared/pipeline/nodes.json")

# ─── Прогон доезжает до воркера ─────────────────────────────────────────────
#
# Формально это стык #11 и #13, а не #12. Но проверяется он здесь, потому что
# именно здесь виден: без постановки в очередь экран прогресса показывает QUEUED
# вечно — а это выглядит как медленная система, а не как ненаписанный вызов.
# Тот же класс разрыва, что был в цепочке «Аудитория»: каждое звено исправно,
# вместе не работает, и ни одна задача графа за него не отвечает.

print("\nЗапуск доезжает до воркера")

queue_src = read(WEB / "lib" / "server" / "queue.ts")
tasks_route = read(WEB / "app" / "api" / "tasks" / "route.ts")

check("lib/server/queue.ts существует", bool(queue_src.strip()))
check("маршрут запуска ставит прогон в очередь", "enqueuePipeline" in tasks_route)
check(
    "очередь только для созданного прогона",
    "created" in tasks_route and "enqueuePipeline" in tasks_route,
    "повторный запуск не должен слать вторую задачу: прогон платный",
)
check(
    "отказ очереди виден в ответе",
    "queueError" in tasks_route,
    "иначе прогон создан, воркер о нём не знает, и узнать это неоткуда",
)
check(
    "id celery-задачи совпадает с id прогона",
    "payload.task_id" in queue_src,
    "по нему воркер находит чекпоинт (thread_id LangGraph); разойдись они — "
    "каждый ретрай начинал бы чистый прогон",
)

# Имена заголовков протокола 2 сверяются с самим Celery, а не с моей памятью.
# Обновление Celery, изменившее имя заголовка, покраснит тест, а не сломает
# прод молча — там дефект выглядел бы как «задача не подхватывается».
try:
    from celery import Celery
except ImportError:
    skip("заголовки протокола совпадают с Celery", "celery не установлен")
else:
    reference = Celery("agora", broker="memory://").amqp.as_task_v2(
        "00000000-0000-0000-0000-000000000000", "agora.run_pipeline", args=[{}], kwargs={},
    )
    absent = [h for h in reference.headers if f"{h}:" not in queue_src]
    check(
        "заголовки протокола совпадают с Celery",
        not absent,
        "нет заголовков: " + ", ".join(absent),
    )

# ─── Экран ──────────────────────────────────────────────────────────────────

print("\nЭкран")

check("страница /runs/[id]/progress существует", PROGRESS_PAGE.exists())
check("экран подписан через EventSource", "EventSource" in view_src)
check(
    "FAILED показывается с причиной",
    "FAILED" in view_src and ("error" in view_src or "причин" in view_src.lower()),
    "статус без текста отправляет пользователя в логи воркера, куда у него нет доступа",
)
check(
    "показан не только текущий узел, но и пройденные",
    "nodes" in view_src.lower(),
    "иначе непонятно, сколько осталось",
)

env_example = read(WEB / ".env.example")
check("VALKEY_URL описан в .env.example", "VALKEY_URL" in env_example)

pkg = json.loads(read(WEB / "package.json") or "{}")
deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
check(
    "клиент Valkey объявлен в зависимостях",
    any(d in deps for d in ("redis", "ioredis")),
)
# §6 CLAUDE.md: нативные модули в apps/web запрещены — сборка в контейнере под
# другой платформой ломается молча.
check(
    "клиент Valkey без нативных модулей",
    "ioredis" in deps or "redis" in deps,
    "берите redis/ioredis (чистый JS), а не обёртки над hiredis",
)

# ─── Поведенческий уровень ──────────────────────────────────────────────────

print("\nПоведение (нужен поднятый веб)")

BEHAVIOURAL = (
    "SSE-поток отдаёт заголовок text/event-stream",
    "прогресс несуществующего прогона не отдаётся",
)

if not live_env():
    for name in BEHAVIOURAL:
        skip(name, "нет поднятого сервера (BASE_URL/E2E_BASE_URL не задан)")
else:
    base = os.environ.get("BASE_URL") or os.environ.get("E2E_BASE_URL") or ""
    client, why = login(base)
    if client is None:
        for name in BEHAVIOURAL:
            skip(name, why)
    else:
        assert isinstance(client, ApiClient)
        # Несуществующий прогон обязан ответить сразу, а не открыть пустой поток:
        # открытый SSE на чужой идентификатор — это способ узнать, что такой
        # прогон существует, не имея к нему доступа.
        status, _ = client.call("/api/tasks/00000000-0000-0000-0000-000000000000/progress")
        check(
            "прогресс несуществующего прогона не отдаётся",
            status in (403, 404),
            f"код ответа {status}",
        )
        skip(
            "SSE-поток отдаёт заголовок text/event-stream",
            "нужен запущенный прогон: проверяется вручную по TC-9.5 из docs/TEST_case.md",
        )


# ═══════════════════════════════════════════════════════════════════════════

print()
n_fail = sum(1 for _, s, _ in results if s == FAIL)
n_skip = sum(1 for _, s, _ in results if s == SKIP)
n_ok = sum(1 for _, s, _ in results if s == PASS)
print(f"Итог: OK={n_ok} FAIL={n_fail} SKIP={n_skip}")
if n_fail:
    print("\nНевыполненные условия:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  · {name}" + (f" — {detail}" if detail else ""))
sys.exit(1 if n_fail else 0)
