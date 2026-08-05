#!/usr/bin/env python3
"""
Спецификация OpenAPI не расходится с маршрутами.

Это не задача графа, а страховка от дефекта, который иначе не находится ничем:
документация, отставшая от кода. Отставание не ломает ни сборку, ни тесты, ни
прогон — оно ломает того, кто по этой документации пишет клиента, и обнаружится
у него, а не у нас.

─── Почему спецификация не собирается из маршрутов на лету ──────────────────
Документ, вычисляемый из кода в рантайме, всегда «совпадает» с кодом и потому
не проверяет ничего: разъехавшийся контракт переписывал бы сам себя. Здесь
наоборот — спецификация лежит исходником и ревьюится, а расхождение с кодом
ловит эта проверка.

─── Почему проверяются обе стороны ──────────────────────────────────────────
Пропущенный в спецификации маршрут — это невидимая часть API. Лишний путь в
спецификации хуже: по нему напишут вызов, который вернёт 404, и время уйдёт на
поиск ошибки в своём коде, а не в чужой документации.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import live_env, login  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"
API_DIR = WEB / "app" / "api"
SPEC_PATH = REPO / "packages" / "shared" / "openapi" / "agora.openapi.json"

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if not ok and detail else ""))


def skip(name: str, why: str) -> None:
    results.append((name, SKIP, why))
    print(f"  SKIP  {name}  →  {why}")


def to_openapi_path(route_file: Path) -> str:
    """
    app/api/persona-sets/[id]/route.ts → /api/persona-sets/{id}

    Перехватывающий сегмент Next `[...nextauth]` становится обычным параметром
    `{nextauth}`: OpenAPI не различает «один сегмент» и «хвост пути», и
    описывать его как-то иначе значило бы придумать нотацию, которую не поймёт
    ни один генератор клиентов.
    """
    rel = route_file.relative_to(WEB / "app").as_posix().removesuffix("/route.ts")
    rel = re.sub(r"\[\.\.\.([^\]]+)\]", r"{\1}", rel)
    rel = re.sub(r"\[([^\]]+)\]", r"{\1}", rel)
    return "/" + rel


print("\nOpenAPI — покрытие маршрутов\n")

# ─── Спецификация читается ──────────────────────────────────────────────────

check("packages/shared/openapi/agora.openapi.json существует", SPEC_PATH.exists())

if not SPEC_PATH.exists():
    spec: dict = {}
else:
    try:
        spec = json.loads(SPEC_PATH.read_text("utf-8"))
        check("спецификация — корректный JSON", True)
    except json.JSONDecodeError as e:
        spec = {}
        check("спецификация — корректный JSON", False, str(e)[:100])

check(
    "версия OpenAPI 3.1",
    str(spec.get("openapi", "")).startswith("3.1"),
    f"заявлено {spec.get('openapi')!r}",
)
check("объявлены серверы", bool(spec.get("servers")))
check(
    "объявлена схема аутентификации",
    "sessionCookie" in (spec.get("components", {}).get("securitySchemes") or {}),
)
check(
    "аутентификация обязательна по умолчанию",
    bool(spec.get("security")),
    "правило «закрыто по умолчанию» должно быть видно и в спецификации: иначе "
    "читатель решит, что API открыт",
)

spec_paths: dict[str, set[str]] = {
    path: {m.upper() for m in item if m.lower() in {x.lower() for x in METHODS}}
    for path, item in (spec.get("paths") or {}).items()
}

# ─── Маршруты в коде ────────────────────────────────────────────────────────

code_paths: dict[str, set[str]] = {}
for route_file in sorted(API_DIR.rglob("route.ts")):
    src = route_file.read_text("utf-8")
    found = set(re.findall(r"export\s+(?:async\s+)?function\s+(" + "|".join(METHODS) + ")", src))
    path = to_openapi_path(route_file)
    # Auth.js обрабатывает свои маршруты сам: экспортов GET/POST в файле нет,
    # они приходят из handlers библиотеки. Для документации это всё равно два
    # метода, и молчать о них нельзя — это единственный публичный вход.
    if not found and "nextauth" in path:
        found = {"GET", "POST"}
    code_paths[path] = found

print(f"\nМаршрутов в коде: {len(code_paths)}, операций: {sum(len(v) for v in code_paths.values())}")
print(f"Путей в спецификации: {len(spec_paths)}, операций: {sum(len(v) for v in spec_paths.values())}\n")

# ─── Сверка ─────────────────────────────────────────────────────────────────

missing_paths = sorted(set(code_paths) - set(spec_paths))
check(
    "все маршруты кода описаны в спецификации",
    not missing_paths,
    "нет: " + ", ".join(missing_paths[:6]),
)

extra_paths = sorted(set(spec_paths) - set(code_paths))
check(
    "в спецификации нет несуществующих путей",
    not extra_paths,
    "лишние: " + ", ".join(extra_paths[:6]),
)

missing_ops: list[str] = []
extra_ops: list[str] = []
for path, methods in code_paths.items():
    documented = spec_paths.get(path, set())
    missing_ops += [f"{m} {path}" for m in sorted(methods - documented)]
    extra_ops += [f"{m} {path}" for m in sorted(documented - methods)]

check("все методы описаны", not missing_ops, "нет: " + ", ".join(missing_ops[:8]))
check("нет описанных, но не реализованных методов", not extra_ops,
      "лишние: " + ", ".join(extra_ops[:8]))

# ─── Публичные маршруты помечены как публичные ──────────────────────────────

auth_config = (WEB / "lib" / "server" / "auth.config.ts").read_text("utf-8")
public = re.findall(r'"(/[^"]+)"', re.search(r"PUBLIC_PATHS\s*=\s*\[([^\]]*)\]", auth_config).group(1))

wrong: list[str] = []
for path, item in (spec.get("paths") or {}).items():
    is_public_in_code = any(path == p or path.startswith(f"{p}/") for p in public)
    for method, op in item.items():
        if method.upper() not in METHODS:
            continue
        declared_public = op.get("security") == []
        if declared_public != is_public_in_code:
            wrong.append(f"{method.upper()} {path}")

check(
    "публичные маршруты совпадают с PUBLIC_PATHS",
    not wrong,
    "расходятся: " + ", ".join(wrong[:6]),
)

# ─── Отдача ─────────────────────────────────────────────────────────────────

print("\nПубликация")

openapi_route = WEB / "app" / "api" / "openapi" / "route.ts"
docs_page = WEB / "app" / "api" / "page.tsx"

check("маршрут /api/openapi отдаёт спецификацию", openapi_route.exists())
check("страница /api рендерит Swagger UI", docs_page.exists())
check(
    "Swagger UI берёт спецификацию по тому же URL, что и внешние потребители",
    "/api/openapi" in (WEB / "components" / "agora" / "SwaggerDocs.tsx").read_text("utf-8"),
    "иначе страница и генератор клиента смотрят на разные копии документа",
)

pkg = json.loads((WEB / "package.json").read_text("utf-8"))
check(
    "swagger-ui объявлен в зависимостях",
    "swagger-ui-dist" in pkg.get("dependencies", {}),
)

# ─── Поведенческий уровень ──────────────────────────────────────────────────

print("\nПоведение (нужен поднятый веб)")

BEHAVIOURAL = ("GET /api/openapi отдаёт спецификацию",)

if not live_env():
    for name in BEHAVIOURAL:
        skip(name, "нет поднятого сервера (BASE_URL/E2E_BASE_URL не задан)")
else:
    base = os.environ.get("BASE_URL") or os.environ.get("E2E_BASE_URL") or ""
    client, why = login(base)
    if client is None:
        skip(BEHAVIOURAL[0], why)
    else:
        status, text = client.call("/api/openapi")
        ok = status == 200
        if ok:
            try:
                ok = json.loads(text).get("openapi", "").startswith("3.1")
            except json.JSONDecodeError:
                ok = False
        check(BEHAVIOURAL[0], ok, f"код {status}")


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
