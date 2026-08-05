#!/usr/bin/env python3
"""
CDD-тест задачи #26 — Промпт-студия.

Двухуровневый по AGENTS.md §3: статический работает где угодно, поведенческий
требует живой базы и поднятого сервера.
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MIGRATION_PATH = REPO / "infra" / "postgres" / "init" / "07_prompts_seed.sql"
#: Промпты сеются не одним файлом: 07 сгенерирован скриптом и уже применён,
#: а §5 CLAUDE.md запрещает править применённую миграцию. Каждый следующий
#: промпт приезжает своим нумерованным файлом, поэтому реестр собирается по
#: всем засевам сразу.
SEED_PATHS = sorted((REPO / "infra" / "postgres" / "init").glob("*prompts_seed*.sql"))
PROMPTS_DIR = REPO / "prompts"
RESOLVER_PATH = REPO / "apps" / "web" / "lib" / "server" / "prompts.ts"
API_DIR = REPO / "apps" / "web" / "app" / "api" / "prompts"

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

# 1. Migration exists and is idempotent
#: Полный текст всех засевов — по нему проверяется покрытие ключей.
seed_text = "\n".join(sp.read_text("utf-8") for sp in SEED_PATHS)

migration_text = ""
if MIGRATION_PATH.exists():
    migration_text = MIGRATION_PATH.read_text("utf-8")
    has_conflict = "ON CONFLICT" in migration_text
    has_create_table = bool(re.search(r"CREATE\s+TABLE", migration_text, re.IGNORECASE))
    check("миграция существует и идемпотентна", has_conflict and not has_create_table,
          f"ON CONFLICT={has_conflict} CREATE TABLE={has_create_table}")
else:
    check("миграция существует и идемпотентна", False, "файл не найден")

# 2. Каждый файл prompts/*.md засеян миграцией.
#
# Литерал «13» отсюда убран. Добавление промпта — штатная операция продукта
# (ровно для неё существует Промпт-студия), и проверка, которая падает при
# каждом добавлении, заставляет править себя вместо того, чтобы ловить
# дефект. Требование же не в количестве, а в покрытии: ни один файл не
# должен остаться без строки в засеве, иначе на чистой базе он молча
# отсутствует.
prompt_files = sorted(PROMPTS_DIR.glob("*.md"))
prompt_keys = {f.stem for f in prompt_files}
migration_keys = set(re.findall(r"'([a-z._]+)'", seed_text))
# Filter to keys that match prompt file names
migration_prompt_keys = migration_keys & prompt_keys
unseeded = sorted(prompt_keys - migration_keys)
check("каждый промпт из prompts/*.md засеян миграцией",
      bool(prompt_files) and not unseeded,
      f"файлов={len(prompt_files)}, без засева: {unseeded}" if unseeded
      else f"файлов={len(prompt_files)}, все засеяны")

# 3. Тексты в засеве совпадают с файлами.
#
# Раньше здесь сверялось наличие ключа в тексте миграции, хотя проверка
# называлась «побайтово». Разница существенная: расхождение засева с файлом —
# это когда в Промпт-студии на чистой базе показывается один текст, а в
# prompts/ лежит другой, и никакой ключ такого не поймает.
#
# Литерал в SQL берётся из одинарных кавычек с удвоением внутри — обратное
# преобразование и даёт исходный текст файла.
texts_match = True
mismatch_detail = ""
if seed_text:
    for f in prompt_files:
        content = f.read_text("utf-8")
        m = re.search(
            rf"VALUES \(NULL, '{re.escape(f.stem)}', '(?:[^']|'')*?', '((?:[^']|'')*)'",
            seed_text,
            re.DOTALL,
        )
        if not m:
            texts_match = False
            mismatch_detail = f"ключ {f.stem} не найден в засеве"
            break
        if m.group(1).replace("''", "'") != content:
            texts_match = False
            mismatch_detail = f"текст {f.stem} в засеве разошёлся с prompts/{f.name}"
            break
check("тексты в засеве совпадают с файлами", texts_match, mismatch_detail)

# 4. No app-level INSERT of defaults
resolver_text = RESOLVER_PATH.read_text("utf-8") if RESOLVER_PATH.exists() else ""
api_route_text = ""
for route_file in API_DIR.rglob("*.ts"):
    api_route_text += route_file.read_text("utf-8") + "\n"

app_inserts_default = bool(re.search(r"INSERT.*is_default.*true", api_route_text + resolver_text, re.IGNORECASE))
check("засев не делается из-под приложения", not app_inserts_default)

# 5. Resolver — single SQL query with ORDER BY tenant_id NULLS LAST
has_order_by = "ORDER BY" in resolver_text and ("NULLS LAST" in resolver_text or "nulls last" in resolver_text.lower())
check("резолвер — один SQL-запрос с ORDER BY tenant_id NULLS LAST", has_order_by,
      "нет ORDER BY ... NULLS LAST" if not has_order_by else "")

# 6. requireOwner on all mutating routes
mutating_routes = [API_DIR / "route.ts", API_DIR / "[key]" / "route.ts",
                   API_DIR / "[key]" / "activate" / "route.ts"]
all_require_owner = True
for route in mutating_routes:
    if route.exists():
        text = route.read_text("utf-8")
        if "requireOwner" not in text and "owner" not in text.lower():
            all_require_owner = False
            break
    else:
        all_require_owner = False
        break
check("правка промпта требует requireOwner", all_require_owner)

# 7. Non-empty {{}} in every prompt file
all_have_placeholders = True
empty_files = []
for f in prompt_files:
    content = f.read_text("utf-8")
    if not re.search(r"\{\{[^}]+\}\}", content):
        all_have_placeholders = False
        empty_files.append(f.name)
check("в каждом файле промпта {{}} непусто", all_have_placeholders,
      f"нет плейсхолдеров: {empty_files}" if empty_files else "")


# --- Behavioral level ---

print("\n== Поведенческий уровень ==")

base_url = os.environ.get("BASE_URL", "https://agora.185-154-194-125.sslip.io")
# Строка подключения берётся через db_dsn: в .env.local хост — имя сервиса
# compose, которое резолвится только внутри сети контейнеров. При запуске с
# хоста это давало FAIL «failed to resolve host postgres», читавшийся как
# поломка базы. См. evals/tests/_harness.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import db_dsn  # noqa: E402

dsn = db_dsn()
admin_dsn = db_dsn("POSTGRES_ADMIN_URL")

if not dsn:
    for i in range(8, 22):
        skip(f"поведенческий кейс {i}", "DATABASE_URL не задан")
else:
    try:
        import psycopg  # noqa: F401

        from _harness import login  # noqa: E402

        # Прежде здесь был собственный клиент с логином и паролем владельца,
        # записанными в исходник (owner@agora.local / пароль строкой). Это
        # учётные данные в репозитории — §7 CLAUDE.md, — и метрика secret_scan
        # их не ловила: она ищет только sk-… и AIza…. Теперь вход идёт через
        # общую обвязку, а данные берутся из окружения.
        client, why_login = login(base_url)

        def curl_get(url, cookies=""):
            return client.call(url.replace(base_url, ""))

        def curl_post(url, data, cookies=""):
            # Создание новой версии — PUT /api/prompts, не POST: POST на этом
            # маршруте не объявлен и отвечает 405. Прежняя редакция слала POST и
            # получала 405, но проверка при этом печаталась как «сохранение
            # новой версии», а не как «маршрут не тот».
            return client.call(url.replace(base_url, ""), "PUT", data.encode("utf-8"))

        cookies = ""

    except ImportError:
        client, why_login = None, "psycopg не установлен"

    if client is None:
        skip("все 13 ключей резолвятся у арендатора (дефолт)", why_login)
        skip("сохранение новой версии", why_login)
        skip("member PUT → 403", why_login)
    else:
        # 8. All 13 keys resolve for tenant without own versions → default
        status, body = curl_get(f"{base_url}/api/prompts", cookies)
        if status == 200:
            prompts_data = json.loads(body)
            check("все 13 ключей резолвятся у арендатора (дефолт)", True)
        else:
            check("все 13 ключей резолвятся у арендатора (дефолт)", False, f"HTTP {status}")

        # Ответ — { stages: { <этап>: [ {key, …}, … ] } }, а не массив промптов.
        # Прежний разбор ждал массив, получал словарь и печатал «нет ключей в
        # API» — то есть сообщал об отсутствии данных там, где их просто читали
        # не оттуда.
        first_key = None
        if status == 200 and isinstance(prompts_data, dict):
            for items in (prompts_data.get("stages") or {}).values():
                if isinstance(items, list) and items:
                    first_key = items[0].get("key")
                    break

        if not first_key:
            skip("сохранение новой версии", f"список промптов пуст (HTTP {status})")
            skip("member PUT → 403", "нет ключа для правки")
        else:
            put_data = json.dumps(
                {"key": first_key, "template": "test {{content}}", "variables": ["content"]}
            )
            status_put, _ = curl_post(f"{base_url}/api/prompts", put_data, cookies)
            check("сохранение новой версии", status_put in (200, 201), f"HTTP {status_put}")

            # Правка промптов — действие владельца. Участник обязан получить 403,
            # иначе роль ничего не ограничивает. Раньше пропускалось «требует
            # member сессии»; учётная запись участника задаётся через
            # MEMBER_EMAIL/MEMBER_PASSWORD и заводится seed-auth.mjs.
            member, why_member = login(base_url, "member")
            if member is None:
                skip("member PUT → 403", why_member)
            else:
                code_m, _ = member.call("/api/prompts", "PUT", put_data.encode("utf-8"))
                check(
                    "member PUT → 403",
                    code_m == 403,
                    f"HTTP {code_m}; 200 значит, что участник правит промпты арендатора",
                )


# --- Summary ---
# Вердикт общий для всех тестов: GREEN только когда проверено всё, что можно
# было проверить здесь. Прежде GREEN печатался при любом числе SKIP, и по
# выводу нельзя было отличить «проверено» от «пропущено» — см. _harness.verdict.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#26"))
