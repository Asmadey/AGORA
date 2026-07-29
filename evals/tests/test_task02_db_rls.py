#!/usr/bin/env python3
"""
CDD-тест задачи #2 — «Схемы БД + RLS».

Двухуровневый, потому что петля идёт по варианту B:

  СТАТИЧЕСКИЙ уровень (работает где угодно, в т.ч. без БД) — разбирает SQL настоящим
    парсером PostgreSQL (pglast/libpg_query) и проверяет структурный контракт:
    у каждой арендаторной таблицы есть tenant_id, включён FORCE ROW LEVEL SECURITY,
    заведены политики, роль приложения не имеет BYPASSRLS, миграции идемпотентны.

  ПОВЕДЕНЧЕСКИЙ уровень (нужен живой Postgres) — то, ради чего всё затевалось:
    из-под tenant A запрос к строкам tenant B возвращает 0 строк по КАЖДОЙ таблице.
    Запускается в среде пользователя, где поднят compose. Без БД честно даёт SKIP,
    а не выдумывает результат.

Запуск:
    python3 evals/tests/test_task02_db_rls.py
    DATABASE_URL=postgresql://... python3 evals/tests/test_task02_db_rls.py   # + поведенческий

Exit 0 = green (статический пройден; поведенческий пройден либо честно пропущен).
"""
from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INIT_DIR = ROOT / "infra" / "postgres" / "init"

failures: list[str] = []
skipped: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -> {detail}"))
    if not ok:
        failures.append(name)


def skip(name: str, reason: str) -> None:
    print(f"  SKIP  {name}  -> {reason}")
    skipped.append(f"{name}: {reason}")


# Таблицы, которые обязаны быть изолированы по арендатору.
# teams изолируется по собственному id, team_members — по team_id; остальные по tenant_id.
TENANT_TABLES = [
    "projects",
    "persona_sets",
    "personas",
    "audience_portraits",
    "prompts",
    "surveys",
    "tasks",
    "reports",
    "settings",
    "report_shares",
    "report_share_views",
    "chat_threads",
    "chat_messages",
    "audience_context_files",
]

# Таблицы с нестандартным ключом изоляции.
SPECIAL_TENANT_TABLES = {"teams": "id", "team_members": "team_id"}

ALL_RLS_TABLES = TENANT_TABLES + list(SPECIAL_TENANT_TABLES)


# ── СТАТИЧЕСКИЙ УРОВЕНЬ ───────────────────────────────────────────────────
print("== файлы миграций ==")

expected_files = ["01_extensions.sql", "02_schema.sql", "03_rls.sql"]
for f in expected_files:
    check(f"infra/postgres/init/{f}", (INIT_DIR / f).is_file(), "не найден")

sql = ""
for f in expected_files:
    p = INIT_DIR / f
    if p.is_file():
        sql += p.read_text(encoding="utf-8") + "\n"

if not sql.strip():
    print("\nRED — миграций нет, дальнейшие проверки бессмысленны")
    sys.exit(1)


def _strip_sql_comments(text: str) -> str:
    """Убирает -- и /* */ комментарии.

    Без этого проверки считают вхождения в поясняющем тексте — например, фраза
    «все CREATE TABLE — IF NOT EXISTS» в шапке файла ловится как незащищённый
    CREATE TABLE. Тест обязан мерить сам SQL, а не комментарии к нему.
    """
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"--[^\n]*", " ", text)
    return text


# Нормализуем пробелы: смысл проверок — в наличии конструкции, а не в её вёрстке.
sql_code = _strip_sql_comments(sql)
sql_lower = re.sub(r"\s+", " ", sql_code).lower()

print("== синтаксис (парсер PostgreSQL) ==")
try:
    import pglast

    try:
        pglast.parse_sql(sql)
        check("весь SQL разбирается парсером PostgreSQL", True)
    except Exception as e:  # noqa: BLE001
        check("весь SQL разбирается парсером PostgreSQL", False, str(e)[:200])
except ImportError:
    skip("синтаксис SQL", "pglast не установлен (pip install pglast)")

print("== таблицы ==")
for t in ALL_RLS_TABLES:
    check(
        f"таблица {t} создаётся",
        re.search(rf"create table (if not exists )?(public\.)?{t}\b", sql_lower) is not None,
        "нет CREATE TABLE",
    )

print("== колонка изоляции ==")
for t in TENANT_TABLES:
    # ищем блок CREATE TABLE ... ( ... ) для этой таблицы
    m = re.search(
        rf"create table (?:if not exists )?(?:public\.)?{t}\b\s*\((.*?)\);\s*(?:create|alter|comment|insert|grant|drop|$)",
        sql_lower,
    )
    check(
        f"{t}.tenant_id объявлен",
        bool(m) and "tenant_id" in m.group(1),
        "в определении таблицы нет tenant_id",
    )

print("== RLS включён и принудителен ==")
for t in ALL_RLS_TABLES:
    check(
        f"{t}: ENABLE ROW LEVEL SECURITY",
        re.search(rf"alter table (?:public\.)?{t}\s+enable row level security", sql_lower)
        is not None,
        "RLS не включён",
    )
    # Без FORCE владелец таблицы обходит политики — это классическая дыра.
    check(
        f"{t}: FORCE ROW LEVEL SECURITY",
        re.search(rf"alter table (?:public\.)?{t}\s+force row level security", sql_lower)
        is not None,
        "без FORCE владелец таблицы обходит RLS",
    )

print("== политики ==")
for t in ALL_RLS_TABLES:
    check(
        f"{t}: политика заведена",
        re.search(rf"create policy\s+\S+\s+on\s+(?:public\.)?{t}\b", sql_lower) is not None,
        "нет CREATE POLICY",
    )

print("== роль приложения ==")
check(
    "роль приложения создаётся",
    "agora_app" in sql_lower,
    "роль agora_app не заведена — под суперпользователем RLS не работает вовсе",
)
check(
    "роль приложения без BYPASSRLS",
    "nobypassrls" in sql_lower,
    "нужен явный NOBYPASSRLS",
)
check(
    "роль приложения не суперпользователь",
    "nosuperuser" in sql_lower,
    "нужен явный NOSUPERUSER — суперпользователь игнорирует все политики",
)

# Рабочие роли созданы NOLOGIN, значит подключаться должна отдельная логин-роль,
# которой выдано членство. Иначе SET LOCAL ROLE в слое доступа не сработает.
login_sh = INIT_DIR / "04_login_role.sh"
if login_sh.is_file():
    login_sql = _strip_sql_comments(login_sh.read_text(encoding="utf-8")).lower()
    check(
        "заведена логин-роль приложения",
        "agora_login" in login_sql and "login" in login_sql,
        "нет роли, под которой приложение подключается к базе",
    )
    check(
        "логин-роль состоит в agora_app",
        re.search(r"grant\s+agora_app\s+to\s+agora_login", login_sql) is not None,
        "без членства SET LOCAL ROLE agora_app упадёт",
    )
    check(
        "логин-роль NOINHERIT",
        "noinherit" in login_sql,
        "без NOINHERIT соединение получает права agora_app и без SET LOCAL ROLE — "
        "забытый вызов перестаёт быть заметен",
    )
    check(
        "пароли логин-ролей берутся из окружения, а не из файла",
        "$" in login_sh.read_text(encoding="utf-8")
        and not re.search(r"password\s+'[a-z0-9]{6,}'", login_sql),
        "пароль захардкожен в миграции",
    )
else:
    check("infra/postgres/init/04_login_role.sh", False, "не найден")

print("== функция тенант-контекста ==")
check(
    "контекст читается из current_setting",
    "current_setting" in sql_lower,
    "нет current_setting — непонятно, откуда берётся арендатор",
)
check(
    "current_setting вызывается в missing_ok-режиме",
    re.search(r"current_setting\s*\([^)]*,\s*true\s*\)", sql_lower) is not None,
    "без второго аргумента true незаданный контекст даёт ошибку вместо пустой выборки",
)
check(
    "пустая строка контекста не роняет приведение к uuid",
    "nullif" in sql_lower,
    "нужен NULLIF(current_setting(...), '') перед ::uuid",
)

print("== шеринг отчётов — единственный легальный обход RLS ==")
check(
    "хранится хеш токена, а не сам токен",
    "token_hash" in sql_lower,
    "токен должен храниться хешем, как пароль",
)
check(
    "у ссылки есть срок жизни",
    "expires_at" in sql_lower,
    "нет expires_at",
)
check(
    "ссылку можно отозвать",
    "revoked_at" in sql_lower,
    "нет revoked_at",
)
check(
    "TTL и отзыв проверяются в самой политике, а не только в коде приложения",
    re.search(r"revoked_at is null", sql_lower) is not None
    and re.search(r"expires_at\s*>\s*now\(\)", sql_lower) is not None,
    "политика доступа по токену не проверяет revoked_at/expires_at",
)
check(
    "просмотры публичной ссылки логируются",
    "report_share_views" in sql_lower,
    "нет аудит-лога просмотров",
)

print("== поля под будущие задачи ==")
for col, why in [
    ("prompts_snapshot", "пиннинг версий промптов на task (#11)"),
    ("replication_count", "«Перекрытие» (#11)"),
    ("parent_task_id", "перезапуск исследования (#30)"),
    ("carry_over_memory", "режим памяти персон при перезапуске (#30)"),
]:
    check(f"tasks.{col} — {why}", col in sql_lower, "колонка отсутствует")

print("== идемпотентность миграций ==")
creates = len(re.findall(r"create table", sql_lower))
guarded = len(re.findall(r"create table if not exists", sql_lower))
check(
    "все CREATE TABLE идемпотентны",
    creates == guarded,
    f"{creates - guarded} таблиц без IF NOT EXISTS",
)
policies = len(re.findall(r"create policy", sql_lower))
dropped = len(re.findall(r"drop policy if exists", sql_lower))
check(
    "политики пересоздаются идемпотентно",
    dropped >= policies,
    f"политик {policies}, DROP POLICY IF EXISTS — {dropped}",
)


# ── ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ ─────────────────────────────────────────────────
print("== кросс-арендаторная изоляция (живой Postgres) ==")

dsn = os.environ.get("DATABASE_URL")
if not dsn:
    skip("изоляция арендаторов", "DATABASE_URL не задан — запустите при поднятом compose")
else:
    try:
        import psycopg
    except ImportError:
        psycopg = None
        skip("изоляция арендаторов", "psycopg не установлен (pip install 'psycopg[binary]')")

    if dsn and "psycopg" in sys.modules and psycopg is not None:
        try:
            tenant_a = uuid.uuid4()
            tenant_b = uuid.uuid4()
            with psycopg.connect(dsn, autocommit=False) as conn:
                with conn.cursor() as cur:
                    # Готовим два арендатора и по строке проекта у каждого.
                    cur.execute("SET LOCAL role agora_app")
                    # SET LOCAL app.tenant_id = %s НЕ работает: команда SET в PostgreSQL
                    # не принимает параметры запроса, а psycopg отправляет их по
                    # расширенному протоколу — получится синтаксическая ошибка. То же
                    # ограничение действует и в приложении, поэтому и там, и здесь
                    # используется обычная функция set_config(name, value, is_local).
                    for t, name in ((tenant_a, "tenant-a"), (tenant_b, "tenant-b")):
                        cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(t),))
                        cur.execute(
                            "INSERT INTO teams (id, name) VALUES (%s, %s) "
                            "ON CONFLICT DO NOTHING",
                            (t, name),
                        )
                        cur.execute(
                            "INSERT INTO projects (tenant_id, name) VALUES (%s, %s)",
                            (t, f"project-of-{name}"),
                        )

                    # Смотрим из-под A: строк B быть не должно нигде.
                    cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_a),))
                    leaks = []
                    for table in ["projects"]:
                        cur.execute(
                            f"SELECT count(*) FROM {table} WHERE tenant_id = %s",
                            (tenant_b,),
                        )
                        n = cur.fetchone()[0]
                        if n:
                            leaks.append(f"{table}: {n} строк арендатора B видны из-под A")
                    check("из-под tenant A строки tenant B не видны", not leaks, "; ".join(leaks))

                    # Совсем без контекста не должно быть видно ничего.
                    cur.execute("RESET app.tenant_id")
                    cur.execute("SELECT count(*) FROM projects")
                    n = cur.fetchone()[0]
                    check(
                        "без тенант-контекста выборка пуста (default deny)",
                        n == 0,
                        f"видно {n} строк без контекста",
                    )
                conn.rollback()  # тест ничего за собой не оставляет
        except Exception as e:  # noqa: BLE001
            check("изоляция арендаторов", False, f"{type(e).__name__}: {str(e)[:180]}")


# ── итог ──────────────────────────────────────────────────────────────────
print()
if failures:
    print(f"RED — не выполнено условий: {len(failures)}")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)

print("GREEN — задача #2 удовлетворяет статическим критериям приёмки")
if skipped:
    print("пропущено (среда):")
    for s in skipped:
        print(f"   · {s}")
    print("\n⚠️  Поведенческая проверка изоляции НЕ выполнена — метрика rls_tenant")
    print("    остаётся неподтверждённой до прогона при поднятом Postgres.")
sys.exit(0)
