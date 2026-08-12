#!/usr/bin/env python3
"""
Экраны хранят данные продукта в базе арендатора, а не в браузере.

Написан после сверки кода с `docs/INTERFACE_REBUILD.md`. Документ описывает
интерфейс, который целиком ходит в Postgres и Mongo под RLS. Пять экранов —
`projects` (список, создание, карточка), `surveys` (список, редактор) и
`audience` — ходили в `lib/db.ts`: обёртку над localforage, то есть IndexedDB
внутри вкладки.

─── Почему это не косметика ─────────────────────────────────────────────────
Дефект такого рода на скриншоте не виден вовсе. Экран заполняется, карточки
рисуются, счётчики считаются. Разница обнаруживается позже и в худший момент:

  · коллега открывает тот же адрес и видит пустой список — данных «нет»;
  · тот же пользователь заходит с другого устройства — данных «нет»;
  · чистка данных сайта в браузере стирает всё безвозвратно;
  · таблицы `projects` и `surveys` в Postgres остаются пустыми, поэтому запуск
    исследования не может сослаться на проект, созданный на экране проектов.

Изоляция арендаторов здесь тоже отсутствует не «частично», а полностью: RLS
защищает базу, а вкладку он не защищает — в ней нет ни арендатора, ни ролей.

─── Проверка на класс, а не на случай ───────────────────────────────────────
Список запрещённых модулей закрыл бы ровно те пять экранов. Поэтому главная
проверка здесь другая: **ни один файл под `app/` и `components/` не обращается
к постоянному хранилищу браузера** — localforage, localStorage, sessionStorage,
indexedDB. Следующий экран, сохранивший проект во вкладку, покраснеет здесь, а
не в переписке через месяц.

Тест статический: разбирает исходники и `package.json`, живой базы не требует и
потому исполняется в CI всегда. Поведенческий уровень (маршрут `/api/projects`
на живом сервере) идёт ниже и честно пропускается там, где сервера нет.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import login, verdict  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"
SPEC = REPO / "packages" / "shared" / "openapi" / "agora.openapi.json"

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, why: str = "", note: str = "") -> None:
    """`why` печатается только при падении, `note` — всегда.

    Разделение не косметическое: первая редакция печатала причину отказа рядом
    с «OK», и зелёная строка выглядела как красная. Проверка, вывод которой
    нужно перечитывать дважды, перестаёт читаться.
    """
    results.append((name, "OK" if ok else "FAIL", why))
    tail = note if ok else why
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {tail}" if tail else ""))


def skip(name: str, why: str) -> None:
    results.append((name, "SKIP", why))
    print(f"  SKIP  {name}  →  {why}")


#: Единственный файл, которому разрешено хранилище браузера.
#:
#: Исключение перечислено поимённо и потому остаётся исключением. Тема — не
#: данные продукта: она не принадлежит арендатору, её незачем видеть коллеге,
#: и её потеря ничего не стоит. Разрешение «где-нибудь в lib/» вместо
#: конкретного файла превратило бы правило в рекомендацию: следующий модуль
#: сложил бы туда черновик визарда, и никто бы не заметил.
STORAGE_ALLOWED = {"lib/theme.ts"}


def sources() -> list[Path]:
    """
    Все .ts/.tsx интерфейса.

    `lib/` включён вместе с `app/` и `components/`. Раньше его здесь не было, и
    это была дыра ровно того размера, что и сам запрет: достаточно вынести
    обращение к localStorage в модуль `lib/`, и проверка молчит. Обнаружилось
    при добавлении переключателя темы — то есть первым же случаем, когда
    хранилище понадобилось по делу.
    """
    out: list[Path] = []
    for root in ("app", "components", "lib"):
        for ext in ("*.ts", "*.tsx"):
            out += sorted((WEB / root).rglob(ext))
    return out


# ─── 1. Хранилище браузера ───────────────────────────────────────────────────

print("\n== Данные продукта не живут во вкладке ==")

#: Постоянное хранилище браузера. `sessionStorage` включён намеренно: он
#: переживает перезагрузку страницы, и экран на нём выглядит работающим ровно
#: так же — до закрытия вкладки.
#:
#: Ищется ОБРАЩЕНИЕ, а не упоминание: имя с точкой, со скобкой или в импорте.
#: Голое слово ловит собственные комментарии («читал localforage») и объявляет
#: дефектом каждый файл, где написано, от чего он ушёл. Проверка, тонущая в
#: ложных срабатываниях, перестаёт читаться и потому не работает — тот же урок,
#: что в `test_schema_contract.py`, где регистронезависимый шаблон принимал
#: питоновский `from pathlib import Path` за SQL.
#:
#: Точка обязана вести к имени метода (`localforage.getItem`), а не просто
#: стоять следом: «читала из localforage. Две копии…» — конец предложения, и
#: первая редакция шаблона считала его обращением.
_BROWSER_STORAGE = re.compile(
    r"""(?:\b(localforage|localStorage|sessionStorage|indexedDB)\s*(?:\.\s*[A-Za-z_$]|\[))"""
    r"""|(?:from\s+['"](localforage)['"])"""
)

# Страховка самого теста: шаблон, переставший что-либо находить, сделал бы
# проверку зелёной навсегда — и это худший исход, потому что выглядит он как
# исправленный дефект.
_CANARY = "await localforage.setItem('projects', p); window.localStorage.clear();"
check(
    "шаблон действительно ловит обращение к хранилищу",
    len(_BROWSER_STORAGE.findall(_CANARY)) == 2,
    f"на образце найдено {len(_BROWSER_STORAGE.findall(_CANARY))} из 2",
)
_PROSE = (
    "// раньше экран читал localforage, теперь базу\n"
    "// список читала из localforage. Две копии расходились молча\n"
    "// в localStorage[никогда] — это тоже проза, но скобку шаблон ловит\n"
)
check(
    "шаблон не считает дефектом упоминание в комментарии",
    len(_BROWSER_STORAGE.findall(_PROSE)) == 1,
    f"ложных срабатываний на прозе: {len(_BROWSER_STORAGE.findall(_PROSE)) - 1}",
    note="скобочная форма остаётся находкой — шаблон не разбирает комментарии",
)

offenders: dict[str, list[str]] = {}
for path in sources():
    rel = str(path.relative_to(WEB))
    if rel in STORAGE_ALLOWED:
        continue
    text = path.read_text("utf-8")
    hits = sorted({name for groups in _BROWSER_STORAGE.findall(text) for name in groups if name})
    if hits:
        offenders[rel] = hits

check(
    "ни один экран не пишет данные продукта в хранилище браузера",
    not offenders,
    "; ".join(f"{f}: {', '.join(h)}" for f, h in sorted(offenders.items())),
    note=f"исключение одно: {', '.join(sorted(STORAGE_ALLOWED))}",
)

# Разрешение не должно пережить того, ради чего выдано. Файл удалили или
# переименовали — исключение обязано уйти вместе с ним, иначе в списке копится
# разрешение на несуществующий путь, а потом кто-то создаёт файл с этим именем.
stale = sorted(rel for rel in STORAGE_ALLOWED if not (WEB / rel).exists())
check("в списке исключений нет несуществующих файлов", not stale, ", ".join(stale))

# ─── 2. Прототипные модули ───────────────────────────────────────────────────

print("\n== Прототипный контур удалён, а не отключён ==")

#: Каждый из этих модулей — часть прототипа на Gemini и localforage.
#: `INTERFACE_REBUILD.md` §5 помечает их как уходящие с задачей #21.
PROTOTYPE_MODULES = [
    "lib/db.ts",          # localforage: проекты, анкеты, аудитории во вкладке
    "lib/ai.ts",          # клиентские вызовы прототипных маршрутов
    "lib/ai-server.ts",   # @google/genai на сервере
    "lib/mock-data.ts",   # заготовленные отчёты и персоны
    "lib/types.ts",       # типы прототипа, дублирующие agora-types.ts
    "app/api/chat/route.ts",
    "app/api/simulate/route.ts",
    "app/api/report/route.ts",
    "app/actions/news.ts",  # лента Google News: к продукту отношения не имеет
]

alive = [m for m in PROTOTYPE_MODULES if (WEB / m).exists()]
check("прототипные модули и маршруты удалены", not alive, ", ".join(alive))

# Отключить импорт, оставив файл, — половина работы: модуль остаётся в сборке,
# и следующий экран возьмёт его снова, потому что он «уже есть».
importers: dict[str, list[str]] = {}
_PROTO_IMPORT = re.compile(r"""from\s+['"]@/(lib/(?:db|ai|ai-server|mock-data|types))['"]""")
for path in sources():
    hits = sorted(set(_PROTO_IMPORT.findall(path.read_text("utf-8"))))
    if hits:
        importers[str(path.relative_to(WEB))] = hits

check(
    "ни один экран не импортирует прототипные модули",
    not importers,
    "; ".join(f"{f}: {', '.join(h)}" for f, h in sorted(importers.items())),
)

# ─── 3. Зависимости ──────────────────────────────────────────────────────────

print("\n== Зависимости прототипа не тянутся в сборку ==")

deps = json.loads((WEB / "package.json").read_text("utf-8")).get("dependencies", {})
PROTOTYPE_DEPS = ["localforage", "uuid", "@types/uuid", "@google/genai"]
kept = [d for d in PROTOTYPE_DEPS if d in deps]
check(
    "зависимости прототипа удалены из package.json",
    not kept,
    ", ".join(kept),
)

# ─── 4. Спецификация ─────────────────────────────────────────────────────────

print("\n== Контракт совпадает с маршрутами ==")

spec = json.loads(SPEC.read_text("utf-8"))
paths = set(spec["paths"])
ghosts = sorted(paths & {"/api/chat", "/api/simulate", "/api/report"})
check("прототипных путей нет в OpenAPI", not ghosts, ", ".join(ghosts))
check(
    "проекты описаны в контракте",
    "/api/projects" in paths and "/api/projects/{id}" in paths,
    why=f"есть только: {sorted(p for p in paths if p.startswith('/api/projects'))}",
    note="/api/projects, /api/projects/{id}",
)

# ─── 5. Экраны ходят в базу арендатора ───────────────────────────────────────

print("\n== Экраны читают данные под сессией ==")

#: Экраны, показывающие данные арендатора. Серверный компонент обязан спросить
#: сессию сам: без неё нет `tenantId`, а без `tenantId` RLS нечего применять.
TENANT_SCREENS = [
    "app/projects/page.tsx",
    "app/projects/new/page.tsx",
    "app/projects/[id]/page.tsx",
    "app/surveys/page.tsx",
    "app/surveys/[id]/page.tsx",
    "app/audience/page.tsx",
]

for rel in TENANT_SCREENS:
    path = WEB / rel
    if not path.exists():
        check(f"{rel} существует", False, "файла нет")
        continue
    text = path.read_text("utf-8")
    is_client = text.lstrip().startswith(('"use client"', "'use client'"))
    check(
        f"{rel} — серверный компонент с проверкой сессии",
        not is_client and "requireSession" in text,
        "client-компонент" if is_client else "нет requireSession",
    )

# Четыре состояния экрана: у страницы, которая ходит в базу, обязан быть
# скелетон. См. INTERFACE_REBUILD.md §4.
for rel in ("app/projects/loading.tsx", "app/surveys/loading.tsx", "app/audience/loading.tsx"):
    check(f"{rel} — скелетон на время запроса", (WEB / rel).exists(), "файла нет")

# ─── 6. Поведенческий уровень ────────────────────────────────────────────────

print("\n== Поведенческий уровень (требует сервер) ==")

BASE_URL = os.environ.get("BASE_URL") or os.environ.get("AGORA_TEST_SERVER")

if not BASE_URL:
    for name in (
        "POST /api/projects создаёт проект",
        "GET /api/projects возвращает созданный проект",
        "проект переживает перезагрузку (читается новым клиентом)",
        "DELETE /api/projects/{id} удаляет проект",
    ):
        skip(name, "требует BASE_URL/AGORA_TEST_SERVER")
else:
    client, why = login(BASE_URL)
    if client is None:
        for name in ("POST /api/projects создаёт проект",):
            skip(name, why)
    else:
        name = f"CDD-проверка {uuid.uuid4().hex[:8]}"
        code, payload = client.call(
            "/api/projects", "POST", json.dumps({"name": name}).encode()
        )
        created = json.loads(payload) if code in (200, 201) else {}
        project_id = (created.get("project") or {}).get("id")
        check("POST /api/projects создаёт проект", code == 201 and bool(project_id),
              f"код {code}, тело {payload[:200]}")

        code, payload = client.call("/api/projects")
        listed = json.loads(payload).get("projects", []) if code == 200 else []
        check(
            "GET /api/projects возвращает созданный проект",
            any(p.get("id") == project_id for p in listed),
            f"код {code}, проектов {len(listed)}",
        )

        # Главное свойство, которого не было у localforage: данные принадлежат
        # арендатору, а не вкладке. Отдельный клиент = отдельная сессия и
        # отдельные куки — ровно то, что делает коллега на своей машине.
        other, why2 = login(BASE_URL)
        if other is None:
            skip("проект переживает перезагрузку (читается новым клиентом)", why2)
        else:
            code, payload = other.call("/api/projects")
            listed = json.loads(payload).get("projects", []) if code == 200 else []
            check(
                "проект переживает перезагрузку (читается новым клиентом)",
                any(p.get("id") == project_id for p in listed),
                f"код {code}, проектов {len(listed)}",
            )

        if project_id:
            code, _ = client.call(f"/api/projects/{project_id}", "DELETE")
            _, payload = client.call("/api/projects")
            listed = json.loads(payload).get("projects", [])
            check(
                "DELETE /api/projects/{id} удаляет проект",
                code == 200 and not any(p.get("id") == project_id for p in listed),
                f"код {code}",
            )
        else:
            skip("DELETE /api/projects/{id} удаляет проект", "проект не создан")


sys.exit(verdict(results, "интерфейс на реальном хранилище"))
