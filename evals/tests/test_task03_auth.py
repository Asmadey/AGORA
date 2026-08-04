#!/usr/bin/env python3
"""
CDD-тест задачи #3 — «Auth и мультиарендность».

Контракт из графа задач (evals/state/tasks.json, id=3):
    неаутентифицированный запрос к защищённому маршруту → 401;
    member не может выполнить owner-действие → 403;
    сессия проставляет tenant_id в RLS-контекст.

Структура повторяет тест задачи #2: два уровня.

  СТАТИЧЕСКИЙ — работает без БД и без поднятого сервера. Проверяет то, что можно
    проверить по исходникам и по чему легче всего ошибиться необратимо: чем хешируется
    пароль, как tenant_id попадает в SQL (параметром или конкатенацией), какие роуты
    остаются открытыми, откуда берётся секрет сессии.

  ПОВЕДЕНЧЕСКИЙ — нужен живой сервер (BASE_URL) и живой Postgres (DATABASE_URL).
    Проверяет ровно три пункта CDD. Без среды — честный SKIP.

Запуск:
    python3 evals/tests/test_task03_auth.py
    BASE_URL=http://localhost:3000 DATABASE_URL=postgresql://... python3 evals/tests/test_task03_auth.py

Exit 0 = green.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web"
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


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


# ── СТАТИЧЕСКИЙ УРОВЕНЬ ───────────────────────────────────────────────────
print("== миграция аутентификации ==")

auth_sql_path = INIT_DIR / "05_auth.sql"
auth_sql = read(auth_sql_path)
auth_lower = auth_sql.lower()

check("infra/postgres/init/05_auth.sql", bool(auth_sql), "не найден")
check(
    "у пользователя есть поле для хеша пароля",
    "password_hash" in auth_lower,
    "нет колонки password_hash",
)
check(
    "миграция идемпотентна",
    "create table" not in auth_lower or "create table if not exists" in auth_lower,
    "CREATE TABLE без IF NOT EXISTS",
)

# Логин обязан прочитать users и team_members ДО того, как известен арендатор,
# а team_members закрыт политикой по team_id. Единственный честный способ —
# функция SECURITY DEFINER с узким контрактом, а не отключение RLS.
print("== чтение членства до установки тенант-контекста ==")
check(
    "доступ к членству идёт через SECURITY DEFINER",
    "security definer" in auth_lower,
    "иначе логин либо упрётся в RLS, либо потребует снять политику с team_members",
)
definer_bodies = re.findall(
    r"create\s+or\s+replace\s+function.*?security\s+definer(.*?)\$\$", auth_lower, re.S
)
check(
    "у SECURITY DEFINER зафиксирован search_path",
    bool(definer_bodies) and all("set search_path" in b for b in definer_bodies),
    "без SET search_path функция исполняется по пути вызывающего — подмена таблицы",
)
check(
    "право на исполнение выдано только роли приложения",
    "grant execute" in auth_lower and "to public" not in auth_lower,
    "GRANT EXECUTE ... TO PUBLIC открывает обход RLS всем",
)

print("== хеширование пароля ==")
pkg = json.loads(read(WEB / "package.json") or "{}")
deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
check("next-auth в зависимостях apps/web", "next-auth" in deps, "Auth.js не подключён")
check("драйвер pg в зависимостях apps/web", "pg" in deps, "нет клиента Postgres")

server_dir = WEB / "lib" / "server"
server_src = "\n".join(read(p) for p in server_dir.rglob("*.ts")) if server_dir.is_dir() else ""
check("apps/web/lib/server существует", bool(server_src), "серверный слой не найден")
check(
    "пароль хешируется argon2id",
    "argon2" in server_src.lower(),
    "argon2id — требование к хранению паролей; sha/md5/plain недопустимы",
)
# Каталог node_modules общий для macOS разработчика, Linux помощника и alpine
# воркера. Нативный модуль ставится под одну платформу и ломает запуск на
# остальных — ровно это уже произошло с @node-rs/argon2.
NATIVE_PACKAGES = ["@node-rs/argon2", "argon2", "bcrypt", "@napi-rs/argon2"]
check(
    "реализация хеша не привязана к платформе",
    not any(p in deps for p in NATIVE_PACKAGES),
    f"нативный модуль в зависимостях: {[p for p in NATIVE_PACKAGES if p in deps]}",
)
check(
    "пароль не сравнивается обычным равенством",
    # \s* умеет отступать назад, поэтому исключение стоит внутри самого lookahead:
    # иначе `typeof x.password === "string"` пролезает как совпадение.
    not re.search(r"password\s*===(?!\s*\"string\")", server_src)
    and not re.search(r"===\s*\w*password_?hash", server_src, re.I),
    "прямое сравнение пароля с хранимым значением",
)
check(
    "несуществующий адрес не выдаёт себя временем ответа",
    "DUMMY_HASH" in server_src or re.search(r"dummy|фиктив", server_src, re.I) is not None,
    "без сравнения с фиктивным хешем скорость отказа отвечает на вопрос «есть ли такой пользователь»",
)

print("== tenant_id попадает в RLS-контекст ==")
check(
    "используется set_config, а не SET LOCAL со склейкой строк",
    "set_config(" in server_src,
    "SET LOCAL не принимает параметры запроса; склейка строки = SQL-инъекция арендатором",
)
check(
    "set_config вызывается в local-режиме",
    re.search(r"set_config\([^)]*true\s*\)", server_src) is not None,
    "третий аргумент true = действие до конца транзакции; иначе контекст течёт между запросами",
)
check(
    "tenant_id передаётся параметром запроса",
    re.search(r"set_config\(\s*'app\.tenant_id'\s*,\s*\$1", server_src) is not None,
    "значение должно уезжать плейсхолдером, а не в тексте SQL",
)
check(
    "перед работой берётся роль приложения",
    re.search(r"set\s+local\s+role\s+agora_app", server_src, re.I) is not None,
    "agora_login задан NOINHERIT: без SET LOCAL ROLE прав на таблицы нет",
)
check(
    "тенант-контекст живёт внутри транзакции",
    "BEGIN" in server_src.upper() and "ROLLBACK" in server_src.upper(),
    "без явной транзакции SET LOCAL бессмысленен, а ошибка оставит контекст на соединении пула",
)

print("== защита маршрутов ==")
mw = read(WEB / "middleware.ts")
auth_config = read(server_dir / "auth.config.ts")
routing_src = mw + "\n" + auth_config  # список открытых путей вынесен в edge-safe конфиг
check(
    "захардкоженной пары логин/пароль не осталось",
    "admin" not in mw.lower(),
    "basic-auth заглушка должна уйти вместе с задачей #3",
)
check(
    "middleware опирается на сессию Auth.js",
    "next-auth" in mw and "BASIC_AUTH" not in mw and "atob(" not in mw,
    "маршруты всё ещё закрыты basic-auth заглушкой, а не аутентификацией",
)
check(
    "правило по умолчанию — закрыто",
    "PUBLIC_PATHS" in routing_src,
    "нет явного списка исключений: новый маршрут рискует оказаться открытым",
)
for open_route in ["/login", "/api/auth", "/api/health"]:
    check(
        f"маршрут {open_route} остаётся открытым",
        open_route in routing_src,
        "иначе вход и healthcheck закольцуются на самих себя",
    )
check(
    "неаутентифицированный запрос к /api получает 401, а не форму входа",
    "401" in auth_config,
    "перенаправление API-запроса на /login отдаёт клиенту HTML со статусом 200",
)

guard_src = read(server_dir / "guard.ts")
check("apps/web/lib/server/guard.ts", bool(guard_src), "нет общего места, где решается 401/403")
check("guard отдаёт 401", "401" in guard_src, "не найден код 401")
check("guard отдаёт 403", "403" in guard_src, "не найден код 403")
check(
    "owner-действия отделены от member",
    "owner" in guard_src and "member" in guard_src.lower(),
    "роли не различаются",
)

print("== сессия ==")
auth_ts = read(server_dir / "auth.ts")
check(
    "сессия несёт tenantId",
    "tenantId" in auth_ts,
    "без арендатора в сессии нечего проставлять в RLS",
)
check("сессия несёт роль", "role" in auth_ts, "без роли нельзя отличить owner от member")
check(
    "секрет сессии объявлен в примере окружения",
    "AUTH_SECRET" in read(WEB / ".env.example"),
    "AUTH_SECRET не описан в .env.example — при развёртывании его забудут",
)
check(
    "секрет не захардкожен",
    not re.search(r"secret\s*:\s*[\"'][A-Za-z0-9+/=]{16,}[\"']", auth_ts + auth_config),
    "в коде найдена строка, похожая на секрет",
)
check(
    "self-host за прокси учтён",
    "trustHost" in auth_config,
    "без trustHost Auth.js отвергает запросы за обратным прокси",
)

print("== настройки переехали из памяти процесса в базу ==")
settings_route = read(WEB / "app" / "api" / "settings" / "route.ts")
check(
    "хранилище в памяти убрано",
    not re.search(r"^let\s+stored", settings_route, re.M),
    "настройки всё ещё живут в переменной модуля",
)
check(
    "роут ходит в базу под арендатором",
    "withTenant" in settings_route,
    "нет вызова тенант-скоупленного доступа",
)
check(
    "запись настроек — действие owner",
    "requireOwner" in settings_route,
    "member не должен менять настройки арендатора",
)


# ── ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ ─────────────────────────────────────────────────
print("== CDD: 401 / 403 / tenant в RLS-контексте (живая среда) ==")

base_url = os.environ.get("BASE_URL")
# Строка подключения берётся через db_dsn: в .env.local хост — имя сервиса
# compose, которое резолвится только внутри сети контейнеров. При запуске с
# хоста это давало FAIL «failed to resolve host postgres», читавшийся как
# поломка базы. См. evals/tests/_harness.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import db_dsn  # noqa: E402

dsn = db_dsn()

if not base_url:
    skip("401 на защищённом маршруте", "BASE_URL не задан — запустите при поднятом сервере")
    skip("403 для member на owner-действии", "BASE_URL не задан")
else:
    import http.cookiejar
    import urllib.error
    import urllib.parse
    import urllib.request

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def call(path: str, method: str = "GET", body: bytes | None = None, form: bool = False):
        """Возвращает (код, тело). Ошибки HTTP — обычный ответ, а не исключение."""
        req = urllib.request.Request(
            base_url.rstrip("/") + path,
            method=method,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
                if form
                else "application/json"
            },
        )
        try:
            with opener.open(req, timeout=15) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            # Сервер не поднят или не отвечает. Ноль вместо кода — чтобы проверка
            # честно упала с понятным текстом, а не рухнула трассировкой.
            return 0, f"нет соединения: {e.reason}"

    code, _ = call("/api/settings")
    check(
        "GET /api/settings без сессии → 401",
        code == 401,
        f"получено {code}; 200 значит утечку настроек арендатора анониму",
    )

    code, _ = call("/api/health")
    check("GET /api/health открыт → 200", code == 200, f"получено {code}")

    # ── 403: нужен настоящий вход настоящим member ──────────────────────
    member_email = os.environ.get("MEMBER_EMAIL")
    member_password = os.environ.get("MEMBER_PASSWORD")

    if not (member_email and member_password):
        skip(
            "403 для member на owner-действии",
            "не заданы MEMBER_EMAIL / MEMBER_PASSWORD; создайте участника "
            "apps/web/scripts/seed-auth.mjs --team-id <uuid> --role member",
        )
    else:
        # Auth.js защищён от CSRF двойной отправкой: токен приходит и куки,
        # и полем формы. Клиент обязан пройти тот же путь, что и браузер.
        code, payload = call("/api/auth/csrf")
        try:
            csrf = json.loads(payload)["csrfToken"]
        except Exception:  # noqa: BLE001
            csrf = None

        if not csrf:
            check("вход member через Auth.js", False, f"csrf не получен, код {code}")
        else:
            form = urllib.parse.urlencode(
                {
                    "email": member_email,
                    "password": member_password,
                    "csrfToken": csrf,
                    "callbackUrl": base_url,
                    "json": "true",
                }
            ).encode()
            code, _ = call("/api/auth/callback/credentials", "POST", form, form=True)
            names = {c.name for c in jar}
            logged_in = any("session-token" in n for n in names)
            check(
                "вход member через Auth.js",
                logged_in,
                f"куки сессии не выдана (код {code}); проверьте пароль и членство",
            )

            if logged_in:
                code, _ = call("/api/settings")
                check(
                    "member читает настройки → 200",
                    code == 200,
                    f"получено {code}: чтение должно быть доступно всей команде",
                )

                payload = json.dumps(
                    {
                        "costCap": "hard",
                        "costCapValue": 300,
                        "whisperModel": "large-v3-turbo",
                        "defaultReplication": 3,
                    }
                ).encode()
                code, _ = call("/api/settings", "PUT", payload)
                check(
                    "member меняет настройки → 403",
                    code == 403,
                    f"получено {code}: member не должен менять настройки команды",
                )

if not dsn:
    skip("сессия проставляет tenant_id в RLS-контекст", "DATABASE_URL не задан")
else:
    try:
        import psycopg
    except ImportError:
        skip(
            "сессия проставляет tenant_id в RLS-контекст",
            "psycopg не установлен (pip install 'psycopg[binary]')",
        )
    else:
        try:
            tenant = uuid.uuid4()
            with psycopg.connect(dsn, autocommit=False) as conn:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL role agora_app")
                    # Ровно тот вызов, которым пользуется lib/server/db.ts.
                    cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant),))
                    cur.execute("SELECT app.current_tenant()")
                    got = cur.fetchone()[0]
                    check(
                        "set_config('app.tenant_id', …, true) читается app.current_tenant()",
                        str(got) == str(tenant),
                        f"ожидался {tenant}, получен {got}",
                    )
                    cur.execute("SELECT set_config('app.tenant_id', '', true)")
                    cur.execute("SELECT app.current_tenant()")
                    check(
                        "пустой контекст даёт NULL (default deny)",
                        cur.fetchone()[0] is None,
                        "пустая строка не обнуляет арендатора",
                    )
                conn.rollback()
        except Exception as e:  # noqa: BLE001
            check("сессия проставляет tenant_id в RLS-контекст", False, f"{type(e).__name__}: {str(e)[:180]}")


# Вердикт общий для всех тестов — см. _harness.verdict. Прежде GREEN печатался
# при любом числе SKIP, и «проверено» не отличалось от «пропущено».
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict_lists  # noqa: E402

sys.exit(verdict_lists(failures, skipped, 0, "#3"))
