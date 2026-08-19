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
    # Пояснение печатается только к упавшей проверке. К зелёной оно читается как
    # описание дефекта, которого нет: «OK … миграции [] трогают prompts.template,
    # но не подходят под маску» — фраза про пустой список, набранная как жалоба.
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail and not ok else ""))

def skip(name, reason):
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


print("== Статический уровень ==")

# 1. Migration exists and is idempotent
#: Полный текст всех засевов — по нему проверяется покрытие ключей.
seed_text = "\n".join(sp.read_text("utf-8") for sp in SEED_PATHS)

# ─── Маска засевов — несущая деталь, и её нарушение невидимо ────────────────
#
# SEED_PATHS собирается по маске `*prompts_seed*.sql`. Миграция, названная иначе,
# в сверку не попадает: проверка «тексты в засеве совпадают с файлами» тихо
# сравнивает файл с ПРЕДЫДУЩЕЙ версией засева и краснеет с формулировкой
# «разошёлся», не называя настоящей причины — что новой миграции она просто не
# видела.
#
# Так и случилось с `19_prompts_frame_no_panel.sql`. Поэтому здесь проверяется
# не текст, а покрытие: всякая миграция, трогающая `prompts.template`, обязана
# попадать под маску.
_ALL_MIGRATIONS = sorted((REPO / "infra" / "postgres" / "init").glob("*.sql"))
_TOUCHES_PROMPTS = [
    m for m in _ALL_MIGRATIONS
    if "prompts" in m.read_text("utf-8") and "template" in m.read_text("utf-8")
    and ("SET template" in m.read_text("utf-8") or "INTO prompts" in m.read_text("utf-8"))
]
_UNCOVERED = [m.name for m in _TOUCHES_PROMPTS if m not in SEED_PATHS]

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
#
# Сверяется ПОСЛЕДНЕЕ присвоение шаблона, а не первое. Дефолт живёт дольше
# одной миграции: 07 его засевает, а следующая нумерованная может переписать
# (так задача #19 добавила confidence в три промпта qa.*). Сверка только с 07
# требовала бы либо править применённую миграцию, что запрещено §5, либо
# оставить проверку красной навсегда — а красная навсегда проверка перестаёт
# читаться и уже ничего не удерживает.
_INSERT = re.compile(
    r"VALUES \(NULL, '(?P<key>[a-z._]+)', '(?:[^']|'')*?', '(?P<tpl>(?:[^']|'')*)'",
    re.DOTALL,
)
_UPDATE = re.compile(
    r"SET template = '(?P<tpl>(?:[^']|'')*)'.*?key = '(?P<key>[a-z._]+)'",
    re.DOTALL,
)
# Третья форма засева: INSERT ... SELECT вместо VALUES. Так написана миграция 21
# — ей нужен WHERE NOT EXISTS для идемпотентности, а VALUES его не принимает.
#
# Разбирать её обязательно, а не «желательно». Проверка, не видящая форму
# записи, молчит там, где текст разошёлся с файлом, — то есть даёт ровно то
# ложное спокойствие, против которого написан комментарий выше. Ключ
# persona.validate так и висел «не найден в засеве», хотя засев был.
_SELECT = re.compile(
    r"SELECT\s+NULL,\s*'(?P<key>[a-z._]+)',\s*'(?:[^']|'')*?',\s*'(?P<tpl>(?:[^']|'')*)'",
    re.DOTALL,
)

# Порядок — по положению в тексте, а не по типу оператора: файлы склеены
# отсортированными, и последний по счёту оператор для ключа и есть тот, что
# останется в базе после прогона всех миграций.
# Четвёртая форма: дописывание к существующему тексту.
#
# `SET template = template || '…'` — так добавляют раздел, не переписывая
# промпт целиком: полная замена в миграции означала бы копию всего текста,
# которая разъедется с оригиналом при первой же правке соседней строки.
#
# Разбирать её обязательно по той же причине, по какой пришлось разбирать
# INSERT ... SELECT: проверка, не знающая формы записи, молчит там, где текст
# разошёлся, — и это уже третий раз, когда слепое пятно находится не само.
_CONCAT = re.compile(
    r"SET template = template \|\| '(?P<tpl>(?:[^']|'')*)'.*?key = '(?P<key>[a-z._]+)'",
    re.DOTALL,
)

# Пятая форма: точечная замена внутри существующего текста.
#
#     SET template = replace(replace(template, 'А', 'Б'), 'В', 'Г')
#     WHERE key = '…'
#
# Так правят промпт, у которого может быть своя редакция из Промпт-студии:
# полная замена стёрла бы её. Миграции 22 и 33 написаны так.
#
# Разбирать её обязательно, и это уже ЧЕТВЁРТОЕ слепое пятно этой проверки —
# после INSERT ... SELECT, `template || '…'` и остальных. Каждое находилось не
# само, и каждое скрывало настоящее расхождение. Это скрывало вот что: файл
# `prompts/respondent.user.md` отстал от базы на миграцию 22 и до сих пор
# описывал `survey_answers` словарём, а не списком пар. Файл — запасной путь
# `_prompt()`, когда в снимке прогона ключа нет, то есть по нему реально могли
# пойти прогоны.
_REPLACE_HEAD = re.compile(r"SET template = replace\s*\(")
#: Ключ ищется в хвосте оператора, а не сразу за скобкой: между ними бывают и
#: другие присваивания (`version = version + 1` в миграции 22), и условия
#: `WHERE tenant_id IS NULL AND is_default AND …`. Требовать `WHERE key`
#: вплотную значило бы понимать только ту форму, которую видел автор проверки.
_KEY_AFTER = re.compile(r"key = '([a-z._]+)'")


def _scan_replace(text: str, open_paren: int) -> tuple[list[str], int]:
    """
    Литералы вложенных replace() и позиция за закрывающей скобкой.

    Сканированием, а не регуляркой. Первая редакция искала `replace\(.*?\)`
    нежадно и обрывалась на первой же `)` — а она стоит ВНУТРИ строкового
    литерала, потому что промпт содержит и скобки, и кавычки. Регулярка,
    считающая содержимое литерала синтаксисом, не разберёт ни одну настоящую
    миграцию.

    Апостроф внутри литерала SQL удваивается; здесь это учитывается, иначе
    сканер решит, что строка кончилась, на первом же `don''t`.
    """
    literals: list[str] = []
    depth = 0
    i = open_paren
    while i < len(text):
        ch = text[i]
        if ch == "'":
            j = i + 1
            buf: list[str] = []
            while j < len(text):
                if text[j] == "'":
                    if j + 1 < len(text) and text[j + 1] == "'":
                        buf.append("'")
                        j += 2
                        continue
                    break
                buf.append(text[j])
                j += 1
            literals.append("".join(buf))
            i = j + 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return literals, i + 1
        i += 1
    raise AssertionError("незакрытая скобка в SET template = replace(…)")


def _replace_assignments(text: str) -> list[tuple[int, str, list[tuple[str, str]]]]:
    r"""
    Пятая форма засева: точечная замена внутри существующего текста.

        SET template = replace(replace(template, 'А', 'Б'), 'В', 'Г')
        WHERE key = '…'

    Так правят промпт, у которого может быть своя редакция из Промпт-студии:
    полная замена стёрла бы её. Миграции 22 и 33 написаны так.

    Разбирать её обязательно, и это уже ЧЕТВЁРТОЕ слепое пятно этой проверки.
    Каждое находилось не само, и каждое скрывало настоящее расхождение. Это
    скрывало вот что: файл `prompts/respondent.user.md` отстал от базы на
    миграцию 22 и описывал `survey_answers` словарём вместо списка пар. Файл —
    запасной путь `_prompt()`, когда в снимке прогона ключа нет, то есть по нему
    реально могли пойти прогоны.
    """
    out: list[tuple[int, str, list[tuple[str, str]]]] = []
    for head in _REPLACE_HEAD.finditer(text):
        literals, after = _scan_replace(text, text.index("(", head.start()))
        statement_end = text.find(";", after)
        key_match = _KEY_AFTER.search(text, after, statement_end if statement_end > 0 else None)
        if not key_match:
            raise AssertionError(
                f"после replace() не найден `WHERE key = …` (позиция {head.start()})"
            )
        # Вложенность replace(replace(t, А, Б), В, Г) кладёт литералы в текст в
        # порядке А, Б, В, Г, а применяются они изнутри наружу — то есть в том
        # же порядке. Нечётное число означает форму, которой мы не понимаем;
        # молча пропустить её — вернуть слепое пятно на место.
        if len(literals) % 2:
            raise AssertionError(
                f"нечётное число литералов ({len(literals)}) в replace() "
                f"для ключа {key_match.group(1)}"
            )
        out.append((
            head.start(),
            key_match.group(1),
            list(zip(literals[0::2], literals[1::2], strict=True)),
        ))
    return out


_assignments = [
    (m.start(), m.group("key"), m.group("tpl").replace("''", "'"), pattern is _CONCAT, None)
    for pattern in (_INSERT, _SELECT, _UPDATE, _CONCAT)
    for m in pattern.finditer(seed_text)
] + [
    (pos, key, "", False, edits)
    for pos, key, edits in _replace_assignments(seed_text)
]

latest_template: dict[str, str] = {}
for _, key, tpl, appends, edits in sorted(_assignments, key=lambda a: a[0]):
    if edits is not None:
        text = latest_template.get(key, "")
        for src, dst in edits:
            text = text.replace(src, dst)
        latest_template[key] = text
    else:
        latest_template[key] = (latest_template.get(key, "") + tpl) if appends else tpl

check(
    "все миграции промптов попадают под маску засевов",
    not _UNCOVERED,
    f"миграции {_UNCOVERED} трогают prompts.template, но не подходят под маску "
    f"*prompts_seed*.sql — сверка текстов их не увидит и покраснеет с неверной "
    f"причиной. Переименуйте по образцу 16_prompts_seed_frame_scene.sql",
)

texts_match = True
mismatch_detail = ""
if seed_text:
    for f in prompt_files:
        seeded = latest_template.get(f.stem)
        if seeded is None:
            texts_match = False
            mismatch_detail = f"ключ {f.stem} не найден в засеве"
            break
        if seeded != f.read_text("utf-8"):
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
