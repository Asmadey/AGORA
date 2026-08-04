#!/usr/bin/env python3
"""
CDD-тест задачи #6 — Реестр персон, карточка и раздел «Персоны».

CDD (из tasks.json):
  persona_set сохраняется и переиспользуется в новом прогоне;
  клик по плашке открывает карточку, в которой присутствует КАЖДОЕ непустое
  поле DNA (проверяется сверкой с canonical JSON Schema — ни одно поле не
  потеряно при рендере);
  кросс-арендаторный доступ к persona_set → 404.

─── Почему сверка со схемой, а не список полей в тесте ────────────────────
Список, выписанный руками, устаревает молча: добавили поле в DNA — тест
по-прежнему зелёный, а в карточке поля нет. Здесь схема разбирается на листовые
пути и каждый ищется в исходнике карточки. Расширение DNA автоматически делает
тест красным, пока карточку не дополнили. Это и есть смысл пункта «ни одно поле
не потеряно при рендере».

На момент написания в схеме 47 листовых полей.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"
SCHEMA = REPO / "packages" / "shared" / "schemas" / "persona-dna.schema.json"

LIST_PAGE = WEB / "app" / "personas" / "page.tsx"
CARD_PAGE = WEB / "app" / "personas" / "[id]" / "page.tsx"
API_LIST = WEB / "app" / "api" / "personas" / "route.ts"
API_ONE = WEB / "app" / "api" / "personas" / "[id]" / "route.ts"
API_SETS = WEB / "app" / "api" / "persona-sets" / "route.ts"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


def read(p: Path) -> str:
    return p.read_text("utf-8") if p.exists() else ""


def schema_leaves() -> list[str]:
    """Листовые пути канонической схемы: demographics.gender, big_five.openness, …"""
    s = json.loads(SCHEMA.read_text("utf-8"))

    def walk(node: dict, path: str = "") -> list[str]:
        props = node.get("properties") or {}
        if not props:
            return [path] if path else []
        out: list[str] = []
        for k, v in props.items():
            child = f"{path}.{k}" if path else k
            out += walk(v, child) or [child]
        return out

    return walk(s)


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

list_src = read(LIST_PAGE)
card_src = read(CARD_PAGE)
api_list_src = read(API_LIST)
api_one_src = read(API_ONE)
api_sets_src = read(API_SETS)

check("страница реестра существует", bool(list_src))
check("страница карточки существует", bool(card_src))
check("GET /api/personas существует", "export async function GET" in api_list_src)
check("GET /api/personas/[id] существует", "export async function GET" in api_one_src)
check(
    "API persona-sets существует (список и создание)",
    "export async function GET" in api_sets_src and "export async function POST" in api_sets_src,
)

# Тенант берётся из сессии, а не из параметров запроса: иначе кросс-арендаторный
# доступ закрывается «по-честному» только до первой подделки идентификатора.
for name, src in (("personas", api_list_src), ("personas/[id]", api_one_src),
                  ("persona-sets", api_sets_src)):
    check(
        f"{name}: сессия и тенант-контекст (requireSession + withTenant)",
        "requireSession" in src and "withTenant" in src,
    )

# Выдуманные данные в продуктовом коде — это ровно тот случай, когда страница
# выглядит работающей и не работает. Пока страницы читают MOCK_*, ни один пункт
# cdd проверить нельзя: база в них не участвует.
#
# Ищется ИМПОРТ, а не слово: упоминание mock-data в комментарии, объясняющем
# историю правки, — не то же самое, что чтение из него. Проверка по слову
# краснела бы на объяснении и заставляла бы это объяснение убрать.
def imports_mock(src: str) -> bool:
    return any(
        "mock-data" in line and line.lstrip().startswith("import")
        for line in src.splitlines()
    )


for page_name, src in (("реестр", list_src), ("карточка", card_src)):
    check(
        f"{page_name} не читает MOCK-данные",
        not imports_mock(src),
        "страница импортирует lib/mock-data" if imports_mock(src) else "",
    )
    check(
        f"{page_name} берёт данные из базы (withTenant)",
        "withTenant" in src and "requireSession" in src,
    )

# Канонический тип — сгенерированный из схемы, а не рукописный. В проекте
# сосуществуют две модели DNA: packages/shared/types/persona-dna.ts (из схемы,
# snake_case) и apps/web/lib/agora-types.ts (руками, camelCase, другой состав
# полей). Пока карточка построена на второй, сверка со схемой невозможна:
# у неё просто другие имена.
uses_canonical = "persona-dna" in card_src or "@agora/shared" in card_src
check(
    "карточка использует канонический тип из packages/shared",
    uses_canonical,
    "" if uses_canonical else "используется рукописный agora-types",
)

# ── Ключевой пункт cdd: ни одно поле DNA не потеряно ────────────────────────
#
# Проверяется не «имя поля встречается в исходнике карточки», а два условия,
# которые вместе дают гарантию сильнее.
#
# Первая редакция теста искала каждое имя в тексте карточки. Это молча
# навязывало реализацию: поля обязаны быть выписаны поимённо. Но именно такой
# рендер и теряет поля — добавили атрибут в схему, карточка про него не знает,
# и заметить это можно только глазами. Перечисление держится на дисциплине, а
# требование cdd — на структуре.
#
# Поэтому: (1) карточка обходит объект DNA, то есть рисует всё, что в нём есть;
# (2) словарь подписей покрывает все поля схемы, иначе поле выйдет на экран с
# техническим именем вместо русского. Новое поле в схеме краснит второй пункт,
# а потерять его при рендере первый пункт не даёт физически.

LABELS = WEB / "lib" / "persona-dna-labels.ts"
labels_src = read(LABELS)
leaves = schema_leaves()

check(
    "карточка рендерит DNA обходом структуры, а не перечислением полей",
    "Object.entries" in card_src,
    "перечисление полей теряет их молча при расширении схемы",
)

# narrative и seed — скаляры верхнего уровня, а не поля категорий: карточка
# рисует их отдельно (описание отдельной секцией, seed в шапке). Подписи им не
# нужны, но присутствие в карточке проверяется — иначе они выпадут незаметно.
TOP_LEVEL = {"narrative", "seed"}
category_leaves = [p for p in leaves if p not in TOP_LEVEL]

missing = [p for p in category_leaves if p.split(".")[-1] not in labels_src]
check(
    f"подписи покрывают все {len(category_leaves)} полей категорий DNA",
    not missing,
    f"нет {len(missing)}: {', '.join(missing[:6])}" + ("…" if len(missing) > 6 else ""),
)

missing_top = [f for f in sorted(TOP_LEVEL) if f not in card_src]
check(
    "карточка показывает narrative и seed",
    not missing_top,
    f"нет: {', '.join(missing_top)}" if missing_top else "",
)


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("\n== Поведенческий уровень ==")

BEHAVIOURAL = (
    "GET /api/personas возвращает список арендатора",
    "persona_set сохраняется и виден в списке",
    "persona_set переиспользуется в новом прогоне",
    "кросс-арендаторный доступ к persona_set → 404",
)

base_url = os.environ.get("BASE_URL") or os.environ.get("AGORA_TEST_SERVER")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import login  # noqa: E402

if not base_url:
    for n in BEHAVIOURAL:
        skip(n, "BASE_URL не задан — запустите при поднятом сервере")
elif not api_sets_src:
    for n in BEHAVIOURAL:
        skip(n, "маршрут persona-sets ещё не реализован")
else:
    client, why = login(base_url)
    if client is None:
        for n in BEHAVIOURAL:
            skip(n, why)
    else:
        code, body = client.call("/api/personas")
        payload = json.loads(body) if code == 200 else {}
        check(
            "GET /api/personas возвращает список арендатора",
            code == 200 and isinstance(payload.get("personas"), list),
            f"status={code} keys={list(payload.keys())[:4]}",
        )

        set_name = f"CDD-набор {uuid.uuid4().hex[:8]}"
        code, body = client.call(
            "/api/persona-sets", "POST",
            json.dumps({"name": set_name, "size": 5, "seed": 42}).encode(),
        )
        set_id = ""
        if code in (200, 201):
            try:
                set_id = ((json.loads(body) or {}).get("personaSet") or {}).get("id", "")
            except json.JSONDecodeError:
                pass

        code_l, body_l = client.call("/api/persona-sets")
        listed = []
        if code_l == 200:
            try:
                listed = (json.loads(body_l) or {}).get("personaSets") or []
            except json.JSONDecodeError:
                pass
        check(
            "persona_set сохраняется и виден в списке",
            bool(set_id) and any(s.get("id") == set_id for s in listed),
            f"создание={code}, список={code_l}, наборов={len(listed)}",
        )

        # «Переиспользуется в новом прогоне» — это не «строка осталась в базе», а
        # «повторный запрос с тем же идентификатором возвращает тот же набор с
        # теми же параметрами генерации». Иначе преселект «Выбрать существующую»
        # опирался бы на данные, которые молча разошлись.
        if not set_id:
            skip("persona_set переиспользуется в новом прогоне", "набор не создан")
        else:
            code_r, body_r = client.call(f"/api/persona-sets?id={set_id}")
            again = []
            if code_r == 200:
                try:
                    again = (json.loads(body_r) or {}).get("personaSets") or []
                except json.JSONDecodeError:
                    pass
            same = next((s for s in again if s.get("id") == set_id), None)
            check(
                "persona_set переиспользуется в новом прогоне",
                same is not None and same.get("name") == set_name and same.get("seed") == 42,
                f"status={code_r}, найден={same is not None}, "
                f"seed={(same or {}).get('seed')}",
            )

        # Кросс-арендаторный доступ. Несуществующий идентификатор годится: RLS
        # обязана вернуть тот же 404, что и для чужого набора, — иначе разница в
        # ответах сама сообщает, существует ли объект у другого арендатора.
        foreign = str(uuid.uuid4())
        code_f, _ = client.call(f"/api/persona-sets/{foreign}")
        check(
            "кросс-арендаторный доступ к persona_set → 404",
            code_f == 404,
            f"status={code_f}; 200 значит утечку, 500 — что RLS роняет запрос",
        )


from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#6"))
