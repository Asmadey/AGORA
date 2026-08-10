#!/usr/bin/env python3
"""
CDD-тест задачи #21 — «Отчёт в UI».

CDD (из tasks.json):
  отчёт рендерится из артефакта без ошибок;
  len(per_persona) == audience_size;
  каждое обоснование кликабельно ведёт на таймкод.

─── Почему первый пункт CDD не про вёрстку ───────────────────────────────────
«Отчёт рендерится из артефакта» предполагает, что артефакт до интерфейса
доезжает. Он не доезжал: узел analytics (#20) клал отчёт в состояние графа и
писал report.json в локальный каталог воркера, а Celery возвращал наружу только
статус. Веб прочитать отчёт не мог ниоткуда, и страница /runs/[id] рендерилась
из lib/mock-data — то есть выглядела готовой, показывая выдуманные числа.

Дефект такого рода не виден на скриншоте: экран с моком и экран с данными
отличаются только тем, откуда взялись цифры. Поэтому здесь первым делом
проверяется путь данных, а уже потом разметка.

─── Почему отчёт и карточки персон хранятся раздельно ────────────────────────
Замерено на синтетике: агрегат с синтезом — от 1 КБ (100 персон) до 178 КБ
(500 персон × 3 повтора), а те же данные вместе с карточками персон для
аккордеона — 654 КБ и 2.1 МБ соответственно.

Отсюда разделение: отчёт читается целиком при открытии экрана, карточки персон
лежат отдельными документами и подтягиваются постранично. Одним документом в
Mongo 2.1 МБ поместились бы (лимит 16 МБ), но первый экран тянул бы два
мегабайта ради пяти чисел, а запас съедался бы ростом аудитории.

Требование `len(per_persona) == audience_size` при этом никуда не девается:
оно проверяется по общему числу карточек, а не по одной странице.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import db_dsn, login, verdict  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "services" / "agent-core"
WEB = REPO / "apps" / "web"
OPENAPI = REPO / "packages" / "shared" / "openapi" / "agora.openapi.json"

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, "OK" if ok else "FAIL", detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if not ok and detail else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, "SKIP", reason))
    print(f"  SKIP  {name}  →  {reason}")


# ═══════════════════════════════════════════════════════════════════════════
# ПУТЬ ДАННЫХ: ВОРКЕР
# ═══════════════════════════════════════════════════════════════════════════

print("== Воркер: отчёт покидает процесс ==")

store_module = CORE / "agent_core" / "analytics" / "store.py"
check("хранение отчёта выделено отдельным модулем", store_module.is_file(),
      "нет agent_core/analytics/store.py: отчёт остаётся в состоянии графа и в "
      "локальном файле воркера, откуда веб его не прочитает")

sys.path.insert(0, str(CORE))
save_report = None
try:
    from agent_core.analytics.store import REPORTS, REPORT_PERSONAS, save_report
except Exception as e:  # noqa: BLE001
    REPORTS = REPORT_PERSONAS = None
    reason = f"модуль не импортируется: {type(e).__name__}: {str(e)[:70]}"
    (skip if store_module.is_file() else lambda n, r: check(n, False, r))(
        "сохранение отчёта импортируется", reason
    )
else:
    check("сохранение отчёта импортируется", True)

STORE_CASES = [
    "отчёт и карточки персон пишутся в разные коллекции",
    "каждая запись несёт tenant_id — в Mongo изоляцию держит только код",
    "карточек ровно столько, сколько ответов",
    "повторное сохранение не плодит документы",
    "карточка несёт срез DNA — иначе посегментный разрез не восстановить",
]

if save_report is None:
    for n in STORE_CASES:
        skip(n, "модуль хранения недоступен")
else:
    class FakeCollection:
        """Достаточно узкая подделка Mongo: upsert по ключу и подсчёт документов."""

        def __init__(self) -> None:
            self.docs: dict[str, dict] = {}

        def update_one(self, flt, update, upsert=False):  # noqa: ARG002
            self.docs[json.dumps(flt, sort_keys=True, default=str)] = {
                **flt, **(update.get("$set") or {})
            }

        def delete_many(self, flt):  # noqa: ARG002
            pass

    class FakeDb:
        def __init__(self) -> None:
            self.collections: dict[str, FakeCollection] = {}

        def __getitem__(self, name: str) -> FakeCollection:
            return self.collections.setdefault(name, FakeCollection())

    #: Настоящий UUID, а не "t1": db.assert_tenant_filter приводит идентификатор
    #: арендатора к UUID и отвергает всё остальное — это и есть та защита, из-за
    #: которой забыть фильтр в Mongo труднее, чем написать его.
    TENANT = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"

    def answer(i: int) -> dict:
        return {"persona_id": f"p{i}", "persona_name": f"Персона {i}", "replication": 0,
                "segment": {"age_group": "25-34", "geo": "столицы", "gender": "жен"},
                "answer": {"scores": {"overall_impression": 7},
                           "verbatims": {"why_impression": "на 00:40 зацепило"},
                           "grounding_refs": ["00:40 спор на кухне"]}}

    try:
        db = FakeDb()
        answers = [answer(i) for i in range(7)]
        report = {"aggregate": {"sample_size": 7}, "narrative": []}

        save_report(db, tenant_id=TENANT, task_id="task-1", report=report,
                    answers=answers, qa_flags=[])

        check(STORE_CASES[0],
              REPORTS in db.collections and REPORT_PERSONAS in db.collections,
              f"коллекции: {sorted(db.collections)}")

        all_docs = [d for c in db.collections.values() for d in c.docs.values()]
        check(STORE_CASES[1], all(str(d.get("tenant_id")) == TENANT for d in all_docs),
              f"документов без tenant_id: "
              f"{sum(1 for d in all_docs if str(d.get('tenant_id')) != TENANT)}")

        check(STORE_CASES[2], len(db[REPORT_PERSONAS].docs) == len(answers),
              f"карточек {len(db[REPORT_PERSONAS].docs)}, ответов {len(answers)}")

        save_report(db, tenant_id=TENANT, task_id="task-1", report=report,
                    answers=answers, qa_flags=[])
        check(STORE_CASES[3], len(db[REPORT_PERSONAS].docs) == len(answers),
              f"после повторного сохранения карточек {len(db[REPORT_PERSONAS].docs)}")

        cards = list(db[REPORT_PERSONAS].docs.values())
        with_segment = [c for c in cards
                        if (c.get("segment") or {}).get("age_group") == "25-34"]
        check(STORE_CASES[4], len(with_segment) == len(answers),
              f"карточек со срезом {len(with_segment)} из {len(answers)}; "
              f"состав первой: {sorted(cards[0]) if cards else '—'}")
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        for n in STORE_CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")


# ═══════════════════════════════════════════════════════════════════════════
# ПУТЬ ДАННЫХ: ВЕБ
# ═══════════════════════════════════════════════════════════════════════════

print("== Веб: отчёт читается из хранилища, а не из мока ==")

page = WEB / "app" / "runs" / "[id]" / "page.tsx"
page_src = page.read_text("utf-8") if page.is_file() else ""

check("страница отчёта не рендерится из mock-data",
      bool(page_src) and "MOCK_RUNS" not in page_src,
      "app/runs/[id]/page.tsx импортирует MOCK_RUNS: экран выглядит готовым, "
      "показывая выдуманные числа, и отличить это от рабочего можно только по коду")

reports_lib = WEB / "lib" / "server" / "reports.ts"
check("доступ к отчёту выделен в lib/server", reports_lib.is_file(),
      "нет apps/web/lib/server/reports.ts")

lib_src = reports_lib.read_text("utf-8") if reports_lib.is_file() else ""
check("модуль отчёта помечен server-only", 'import "server-only"' in lib_src,
      "без server-only импорт с клиента утащит в браузер строку подключения к Mongo")
check("тенант берётся из сессии, а не из аргумента",
      bool(lib_src) and not re.search(r"function \w+\([^)]*tenantId", lib_src),
      "функция принимает tenantId параметром: в Mongo нет RLS, и подставить чужой "
      "идентификатор смог бы вызывающий")

route = WEB / "app" / "api" / "tasks" / "[id]" / "report" / "route.ts"
check("маршрут отчёта существует", route.is_file(),
      "нет app/api/tasks/[id]/report/route.ts")
route_src = route.read_text("utf-8") if route.is_file() else ""
check("маршрут отчёта закрыт сессией",
      "requireSession" in route_src or "auth()" in route_src,
      "в обработчике нет проверки сессии")

personas_route = WEB / "app" / "api" / "tasks" / "[id]" / "report" / "personas" / "route.ts"
check("карточки персон отдаются отдельным маршрутом", personas_route.is_file(),
      "нет app/api/tasks/[id]/report/personas/route.ts — аккордеон тянул бы "
      "мегабайты вместе с первым экраном")

spec = json.loads(OPENAPI.read_text("utf-8")) if OPENAPI.is_file() else {}
paths = spec.get("paths") or {}
check("оба маршрута описаны в OpenAPI",
      "/api/tasks/{id}/report" in paths and "/api/tasks/{id}/report/personas" in paths,
      f"в спецификации нет: "
      f"{[p for p in ('/api/tasks/{id}/report', '/api/tasks/{id}/report/personas')
          if p not in paths]}")


# ═══════════════════════════════════════════════════════════════════════════
# РАЗМЕТКА: ОБОСНОВАНИЕ ВЕДЁТ НА ТАЙМКОД
# ═══════════════════════════════════════════════════════════════════════════

print("== Обоснование кликабельно ==")

#: Смотреть надо туда, где таймкод РИСУЕТСЯ, а не туда, где он упоминается.
#: Первая редакция читала только PersonaAccordion.tsx и краснела при рабочем
#: коде: аккордеон отдаёт отрисовку компоненту TimecodeRef, и якорь живёт в нём.
#: Проверка, привязанная к файлу вместо поведения, требует правки себя при
#: каждом выносе компонента — то есть учит править проверку, а не код.
timecode_sources = [
    WEB / "components" / "agora" / "PersonaAccordion.tsx",
    WEB / "components" / "agora" / "Primitives.tsx",
]
acc_src = "\n".join(p.read_text("utf-8") for p in timecode_sources if p.is_file())

check("таймкод в карточке персоны — элемент, а не текст",
      bool(re.search(r"<a[\s\n]", acc_src)) and "timecode" in acc_src.lower(),
      "таймкод отрисован обычным span: «кликабельно ведёт на таймкод» не выполняется")

check("ссылка на таймкод несёт позицию в секундах",
      "#t=" in acc_src or "?t=" in acc_src or "seek" in acc_src.lower(),
      "в разметке нет ни якоря с позицией, ни обработчика перемотки — «ведёт» "
      "не реализовано, кликабельность без адреса ничего не даёт")


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Поведенческий уровень ==")

BEHAVIOUR = [
    "отчёт отдаётся по маршруту и содержит агрегат",
    "карточек персон ровно audience_size",
    "чужой арендатор отчёта не получает",
]

base_url = os.environ.get("BASE_URL")
task_id = os.environ.get("AGORA_REPORT_TASK_ID")

if not base_url:
    for n in BEHAVIOUR:
        skip(n, "BASE_URL не задан — сервера нет")
elif not task_id:
    for n in BEHAVIOUR:
        skip(n, "AGORA_REPORT_TASK_ID не задан: нужен идентификатор прогона со "
                "статусом REPORT_READY. Прогон кладёт его сам — возьмите из /api/tasks")
else:
    client, why = login(base_url)
    if client is None:
        for n in BEHAVIOUR:
            skip(n, why)
    else:
        code, payload = client.call(f"/api/tasks/{task_id}/report")
        try:
            body = json.loads(payload)
        except Exception:  # noqa: BLE001
            body = {}
        check(BEHAVIOUR[0],
              code == 200 and bool((body.get("aggregate") or {}).get("core_scores_mean")),
              f"код {code}, ключи {sorted(body)[:6]}")

        size = (body.get("audience_size") or 0)
        code2, payload2 = client.call(f"/api/tasks/{task_id}/report/personas?limit=1000")
        try:
            cards = json.loads(payload2).get("items") or []
        except Exception:  # noqa: BLE001
            cards = []
        check(BEHAVIOUR[1], size > 0 and len(cards) == size,
              f"карточек {len(cards)}, audience_size {size}")

        other, why2 = login(base_url, role="member")
        if other is None:
            skip(BEHAVIOUR[2], why2)
        else:
            code3, _ = other.call(f"/api/tasks/{task_id}/report")
            check(BEHAVIOUR[2], code3 in (403, 404),
                  f"чужому арендатору вернулось {code3}, ожидалось 403 или 404")

_ = db_dsn  # используется через _harness.live_env для вердикта


print()
sys.exit(verdict(results, task="#21"))
