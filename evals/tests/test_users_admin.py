#!/usr/bin/env python3
"""
Управление пользователями: владелец может, участник — нет (этап Ж).

─── Что здесь проверяется ────────────────────────────────────────────────────
Разделение ролей ломается тихо. Маршрут, который заводит пользователя без
проверки роли, работает совершенно правильно с точки зрения любого сценария:
пользователь создаётся, в команду попадает, входит. Отличить такую сборку от
исправной можно, только зайдя участником и попробовав то, чего ему нельзя, —
то есть сделав ровно то, чего никто не делает при проверке своей работы.

Ровно то же с последним владельцем. Команда без владельца выглядит нормально,
пока кому-нибудь не понадобится завести пользователя, сменить настройки или
удалить исследование: все эти действия требуют роли, которой больше ни у кого
нет, и вернуть её изнутри продукта нельзя.

Поэтому оба свойства проверяются здесь, а не остаются на внимательность.

─── Два уровня ───────────────────────────────────────────────────────────────
Статический — по исходникам: маршрут обязан звать `requireOwner`, а не
`requireSession`, и обязан отказывать последнему владельцу. Работает где угодно.

Поведенческий — на живом сервере с двумя учётными записями. Без BASE_URL и
учётных данных уходит в SKIP, а не выдумывает результат.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail and not ok else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


def read(p: Path) -> str:
    return p.read_text("utf-8") if p.exists() else ""


print("== Статический уровень ==")

route = read(WEB / "app" / "api" / "users" / "route.ts")
one = read(WEB / "app" / "api" / "users" / "[id]" / "route.ts")
lib = read(WEB / "lib" / "server" / "users.ts")

check("маршрут /api/users существует", bool(route))
check("маршрут /api/users/[id] существует", bool(one))

# POST обязан требовать владельца. requireSession здесь недостаточно: участник,
# который может добавить себе второго владельца, обходит разделение ролей.
post_block = route.split("export async function POST", 1)[-1]
check(
    "заведение пользователя требует прав владельца",
    "requireOwner" in post_block,
    "POST /api/users не зовёт requireOwner — участник сможет завести владельца "
    "и получить владельческие права в обход роли",
)

check(
    "удаление участника требует прав владельца",
    "requireOwner" in one,
    "DELETE /api/users/[id] не зовёт requireOwner",
)

# Чтение списка — не владельческое действие: состав команды не секрет для тех,
# кто в ней состоит. Проверка от обратного: если и GET требует владельца, это
# ошибка в другую сторону, и участник не увидит, с кем работает.
get_block = route.split("export async function GET", 1)[-1].split("export async function POST")[0]
check(
    "список участников виден любому участнику",
    "requireSession" in get_block and "requireOwner" not in get_block,
    "GET /api/users закрыт от участников — состав своей команды они видеть должны",
)

check(
    "последний владелец не удаляется",
    "LastOwnerError" in lib and "owners" in lib,
    "в lib/server/users.ts нет проверки на последнего владельца: команда может "
    "остаться без роли, которую изнутри продукта не вернуть",
)

check(
    "удаляется членство, а не пользователь",
    "DELETE FROM team_members" in lib and "DELETE FROM users" not in lib,
    "удаление трогает таблицу users — человек вылетит из всех своих команд сразу",
)

# Пароль существующего пользователя не переписывается: users глобальна, и смена
# пароля при добавлении в чужую команду была бы способом отобрать доступ.
check(
    "существующему пользователю не меняется пароль",
    "ON CONFLICT (email) DO NOTHING" in lib,
    "добавление в команду перезаписывает пароль существующего пользователя — "
    "это способ отобрать чужой доступ",
)

check(
    "argon2 берётся из WebAssembly, а не из нативного модуля",
    "hash-wasm" in lib,
    "нативные npm-модули в apps/web запрещены (§6 CLAUDE.md): собранный под "
    "Linux пакет ломает запуск на macOS",
)

# Пароль не должен возвращаться наружу ни в каком виде.
check(
    "пароль не возвращается в ответе",
    "password" not in route.split("return Response.json")[-1],
    "в ответе фигурирует пароль — §6-бис: всё, что попало в переписку или логи, "
    "считается скомпрометированным",
)


# ─── Колонки в SQL против схемы ──────────────────────────────────────────────
#
# Раздел «Пользователи» падал целиком: `listMembers` просил `m.created_at`, а в
# `team_members` колонка называется `joined_at`. Наружу это выходило как
# «An error occurred in the Server Components render» с одним лишь digest —
# сообщение Next.js прячет в проде намеренно, чтобы не выдать устройство базы.
#
# Ни одна из проверок выше этого не поймала, и не могла: все они читают, ЧТО
# делает код, и ни одна не сверяет его с тем, что есть в базе. Тот же промах
# сидел вторым экземпляром в `addMember` — то есть заведение пользователя тоже
# было сломано, просто до него не доходили: страница со списком падала раньше.
#
# Поэтому проверка не про `created_at`, а про класс: каждая колонка, которую SQL
# просит у таблицы, обязана в этой таблице быть. Точечная проверка на одно имя
# закрыла бы ровно один случай из двух, уже случившихся.


def table_columns(sql: str, table: str) -> set[str]:
    """Колонки таблицы из CREATE TABLE. Пустое множество — таблица не найдена."""
    import re

    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {table}\s*\((.*?)\n\);", sql, re.S
    )
    if not match:
        return set()
    columns = set()
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith(("--", "CONSTRAINT", "PRIMARY KEY", "UNIQUE", "CHECK", "FOREIGN")):
            continue
        name = line.split()[0]
        if name.isidentifier():
            columns.add(name)
    return columns


schema_sql = read(REPO / "infra" / "postgres" / "init" / "02_schema.sql")

# Псевдонимы, которыми пользуется users.ts: `FROM team_members m JOIN users u`.
ALIASES = {"m": "team_members", "u": "users", "o": "team_members"}

unknown: list[str] = []
for alias, table in ALIASES.items():
    columns = table_columns(schema_sql, table)
    if not columns:
        unknown.append(f"таблица {table} не найдена в 02_schema.sql")
        continue
    import re as _re

    for referenced in sorted(set(_re.findall(rf"\b{alias}\.([a-z_]+)\b", lib))):
        if referenced not in columns:
            unknown.append(f"{alias}.{referenced} — в таблице {table} такой колонки нет")

check(
    "каждая колонка в SQL есть в схеме",
    not unknown,
    "; ".join(unknown),
)


print("== Поведенческий уровень ==")

base = os.environ.get("BASE_URL") or os.environ.get("E2E_BASE_URL")
member_email = os.environ.get("E2E_MEMBER_EMAIL")
member_password = os.environ.get("E2E_MEMBER_PASSWORD")

CASES = (
    "участник получает 403 на заведение пользователя",
    "владелец заводит пользователя",
)

if not base:
    for case in CASES:
        skip(case, "нет поднятого сервера (BASE_URL/E2E_BASE_URL не задан)")
elif not (member_email and member_password):
    for case in CASES:
        skip(case, "нет учётной записи участника (E2E_MEMBER_EMAIL/E2E_MEMBER_PASSWORD)")
else:
    # Живой уровень требует сессии Auth.js: вход идёт формой с CSRF-токеном, и
    # воспроизводить его здесь — отдельная задача. Он написан в evals/e2e_run.py,
    # где такой вход уже есть; здесь честный SKIP вместо половинчатой проверки.
    for case in CASES:
        skip(case, "вход выполняется сценарием evals/e2e_run.py — запускайте оттуда")


print()
n_fail = sum(1 for _, s, _ in results if s == FAIL)
n_skip = sum(1 for _, s, _ in results if s == SKIP)
print(f"Итог: OK={len(results) - n_fail - n_skip} FAIL={n_fail} SKIP={n_skip}")
if n_fail:
    print("\nНевыполненные условия:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  · {name}" + (f" — {detail}" if detail else ""))
sys.exit(1 if n_fail else 0)
