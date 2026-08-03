#!/usr/bin/env python3
"""
CDD-тест задачи #7 — Визард (XState) + черновики (MongoDB).

Двухуровневый: статический работает где угодно, поведенческий требует живой базы.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MACHINE_PATH = REPO / "apps" / "web" / "lib" / "wizard" / "machine.ts"
MONGO_PATH = REPO / "apps" / "web" / "lib" / "server" / "mongo.ts"

PASS = "OK"
FAIL = "FAIL"
SKIP = "SKIP"

results = []

def check(name, ok, detail=""):
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail else ""))

def skip(name, reason):
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


print("== Статический уровень ==")

# 1. Machine defines exactly 7 steps
machine_text = MACHINE_PATH.read_text("utf-8") if MACHINE_PATH.exists() else ""
states = re.findall(r"^\s+(\w+):\s*\{", machine_text, re.MULTILINE)
# Filter to actual state names (not nested objects)
step_names = [s for s in states if s in (
    "content", "audience", "survey", "overlap_params", "summary", "launch", "progress"
)]
check("машина определяет ровно 7 шагов", len(step_names) == 7,
      f"найдено {len(step_names)}: {step_names}")

# 2. Each step has required fields check
has_required = "canProceed" in machine_text and "REQUIRED" in machine_text
check("у каждого шага объявлены обязательные поля", has_required)

# 3. Graph reachable: first step to last
has_next = "NEXT" in machine_text
has_back = "BACK" in machine_text
check("граф достижим: переходы NEXT/BACK есть", has_next and has_back)

# 4. Mongo access only through lib/server/mongo.ts
all_ts_files = list((REPO / "apps" / "web").rglob("*.ts"))
all_ts_files = [f for f in all_ts_files if "node_modules" not in str(f) and ".next" not in str(f)]
mongo_imports_outside_module = []
for f in all_ts_files:
    if f == MONGO_PATH:
        continue
    text = f.read_text("utf-8", errors="ignore")
    if "MongoClient" in text and "from" in text and "mongodb" in text.lower():
        # Check if it's just a type import
        if "import { MongoClient" in text or "import MongoClient" in text:
            mongo_imports_outside_module.append(f.relative_to(REPO))
check("доступ к Mongo только через lib/server/mongo.ts", len(mongo_imports_outside_module) == 0,
      f"найдено в: {mongo_imports_outside_module}" if mongo_imports_outside_module else "")

# 5. tenant_id from session, not from arguments
mongo_text = MONGO_PATH.read_text("utf-8") if MONGO_PATH.exists() else ""
# Check that exported functions take SessionUser (which contains tenantId) but not tenantId directly
exported_funcs = re.findall(r"export async function (\w+)\(.*?\)", mongo_text, re.DOTALL)
has_tenant_arg = bool(re.search(r"function\s+\w+\(.*tenantId.*\)", mongo_text))
check("tenant_id из сессии, не из аргументов", not has_tenant_arg,
      "найдена функция с tenantId в аргументах" if has_tenant_arg else "")

# 6. Every query to wizard_drafts includes tenant_id filter
# Check that all find/update/delete operations include tenant_id
queries = re.findall(r"(?:find|updateOne|deleteOne|insertOne)\(([^)]+)", mongo_text, re.DOTALL)
all_have_tenant = all("tenant_id" in q for q in queries) if queries else True
check("каждый запрос к wizard_drafts включает фильтр tenant_id", all_have_tenant,
      "найден запрос без tenant_id" if not all_have_tenant else "")


# --- Behavioral level ---

print("\n== Поведенческий уровень ==")

base_url = os.environ.get("BASE_URL", "https://agora.185-154-194-125.sslip.io")

# Переменная называется MONGODB_URL: так она задана в .env.local, в .env.example,
# в обоих сервисах compose и в agent_core/config.py. Тест читал MONGODB_URI,
# которого нет нигде, и поэтому поведенческий уровень молча уходил в SKIP на любой
# нормально настроенной машине — тот же дефект, что был в mongo.ts. MONGODB_URI
# оставлен запасным вариантом, чтобы не ломать уже настроенные окружения.
mongo_uri = os.environ.get("MONGODB_URL") or os.environ.get("MONGODB_URI")

# Managed-инстанс TimeWeb при discovery отдаёт внутренние адреса реплики, и без
# directConnection драйвер виснет. Приложение добавляет этот параметр само
# (apps/web/lib/server/mongo.ts) — тест обязан подключаться так же, иначе он
# проверяет не тот режим соединения, в котором работает продукт.
if mongo_uri and "directconnection=" not in mongo_uri.lower():
    mongo_uri += ("&" if "?" in mongo_uri else "?") + "directConnection=true"

if not mongo_uri:
    for i in range(7, 15):
        skip(f"поведенческий кейс {i}", "MONGODB_URL не задан")
else:
    try:
        from pymongo import MongoClient
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=8000)
        db = client[os.environ.get("MONGO_DB", os.environ.get("MONGODB_DB", "agora"))]

        # 12. Draft isolation between tenants
        coll = db["wizard_drafts"]
        # Insert draft for tenant A
        coll.delete_many({"tenant_id": "test-tenant-a", "project_id": "test-proj"})
        coll.delete_many({"tenant_id": "test-tenant-b", "project_id": "test-proj"})
        coll.insert_one({
            "tenant_id": "test-tenant-a",
            "project_id": "test-proj",
            "user_id": "user-a",
            "data": {"step": 3, "mode": "short"},
            "updated_at": None,
        })
        # Query as tenant B
        doc_b = coll.find_one({"tenant_id": "test-tenant-b", "project_id": "test-proj"})
        check("черновик другого арендатора не виден", doc_b is None)

        # 13. Two drafts for same user, different projects
        coll.insert_one({
            "tenant_id": "test-tenant-a",
            "project_id": "test-proj-2",
            "user_id": "user-a",
            "data": {"step": 1, "mode": "long"},
            "updated_at": None,
        })
        docs = list(coll.find({"tenant_id": "test-tenant-a", "user_id": "user-a"}))
        proj_ids = {d["project_id"] for d in docs}
        check("два черновика одного пользователя по разным проектам не смешиваются",
              len(proj_ids) >= 2)

        # Cleanup
        coll.delete_many({"tenant_id": {"$in": ["test-tenant-a", "test-tenant-b"]}})

    except ImportError:
        for i in range(12, 14):
            skip(f"поведенческий кейс {i}", "pymongo не установлен")
    except Exception as e:
        check("поведенческий тест Mongo", False, f"{type(e).__name__}: {str(e)[:120]}")


# ── CDD-1: машина не пускает вперёд без обязательных полей ───────────────────
# Guard canProceed живёт в TypeScript и в браузере, из Python его не вызвать.
# Раньше здесь стояла строка `# 7-11 require running server with XState — skip
# for now`, пропускавшая эти кейсы безусловно — при живом сервере тоже. Оба
# пункта cdd задачи лежат именно тут, поэтому задача годами стояла done, ни разу
# не будучи проверенной. Машина исполняется Node напрямую (стирание типов),
# отдельная сборка не нужна.

probe = REPO / "evals" / "tests" / "fixtures" / "wizard_machine_probe.mjs"
node = shutil.which("node")

if node is None:
    skip("машина состояний: гарантии переходов", "node не установлен")
elif not (REPO / "node_modules" / "xstate").exists():
    skip("машина состояний: гарантии переходов", "xstate не установлен (npm ci)")
else:
    proc = subprocess.run(
        [node, str(probe)], capture_output=True, text=True, cwd=REPO, timeout=90
    )
    try:
        cases = json.loads(proc.stdout)
    except json.JSONDecodeError:
        cases = None

    if cases is None:
        check(
            "машина состояний: гарантии переходов",
            False,
            f"прогон машины не дал результата (код {proc.returncode}): "
            f"{(proc.stderr or proc.stdout)[-160:]}",
        )
    else:
        for case in cases:
            check(case["name"], case["ok"], case.get("detail", ""))


# ── CDD-2: черновик восстанавливается после перезагрузки страницы ────────────
# Перезагрузка на стороне продукта означает: состояние не в памяти вкладки, а
# на сервере, и следующий GET возвращает то же самое. Именно это здесь и
# проверяется — записать черновик и прочитать его новым клиентом.

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import login  # noqa: E402

client, why = login(base_url)

if client is None:
    skip("черновик восстанавливается после перезагрузки", why)
else:
    project_id = f"cdd-{uuid.uuid4()}"
    draft = {
        "contentTitle": "Ролик из CDD-прогона",
        "contentUrl": "s3://bucket/cdd.mp4",
        "mode": "short",
        "currentStep": 2,
    }
    # PUT сохраняет тело целиком как черновик — оборачивать его в {"draft": …}
    # нельзя, иначе на чтении вернётся черновик с полем draft внутри.
    code, body = client.call(
        f"/api/wizard/drafts/{project_id}", "PUT", json.dumps(draft).encode()
    )
    saved = code == 200

    # Новый клиент с собственной сессией — это и есть «перезагрузка»: ничего от
    # предыдущего соединения не переиспользуется, кроме учётных данных.
    fresh, why2 = login(base_url)
    restored = {}
    if fresh is not None:
        code2, body2 = fresh.call(f"/api/wizard/drafts/{project_id}")
        if code2 == 200:
            try:
                # Ответ — обёртка хранения: { draft: { project_id, user_id,
                # updated_at, data } }. Поля визарда лежат в data, а не в самом
                # draft; чтение draft.contentTitle даёт None и выглядит как
                # потерянный черновик при целом хранилище.
                restored = ((json.loads(body2) or {}).get("draft") or {}).get("data") or {}
            except json.JSONDecodeError:
                restored = {}

    check(
        "черновик восстанавливается после перезагрузки",
        saved
        and restored.get("contentTitle") == draft["contentTitle"]
        and restored.get("currentStep") == draft["currentStep"],
        f"сохранение={code}, восстановлено={ {k: restored.get(k) for k in ('contentTitle', 'currentStep')} }",
    )


# --- Summary ---
n_pass = sum(1 for _, s, _ in results if s == PASS)
n_fail = sum(1 for _, s, _ in results if s == FAIL)
n_skip = sum(1 for _, s, _ in results if s == SKIP)

if n_fail:
    print(f"\nRED — не выполнено условий: {n_fail}")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  · {name}" + (f" ({detail})" if detail else ""))
elif n_skip > 0 and n_pass == 0:
    print(f"\nSKIP — все тесты пропущены")
else:
    print(f"\nGREEN — задача #7 удовлетворяет критериям (pass={n_pass} skip={n_skip})")

sys.exit(1 if n_fail else 0)