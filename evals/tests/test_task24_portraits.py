#!/usr/bin/env python3
"""CDD-тест задачи #24 — Audience Portraits."""
from __future__ import annotations
import json, os, sys, uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DISTILL_PATH = REPO / "services" / "agent-core" / "agent_core" / "portraits" / "distill.py"
PROMPT_PATH = REPO / "prompts" / "portrait.distill.md"
API_LIST = REPO / "apps" / "web" / "app" / "api" / "portraits" / "route.ts"
API_DETAIL = REPO / "apps" / "web" / "app" / "api" / "portraits" / "[id]" / "route.ts"
API_DISTILL = REPO / "apps" / "web" / "app" / "api" / "portraits" / "distill" / "route.ts"
MIGRATION = REPO / "infra" / "postgres" / "init" / "08_portrait_versions.sql"

results = []
def check(n, ok, d=""): results.append((n, "OK" if ok else "FAIL", d)); print(f"  {'OK  ' if ok else 'FAIL'}  {n}" + (f"  →  {d}" if d else ""))
def skip(n, r): results.append((n, "SKIP", r)); print(f"  SKIP  {n}  →  {r}")

print("== Статический уровень ==")
distill = DISTILL_PATH.read_text("utf-8") if DISTILL_PATH.exists() else ""
check("модуль distill существует", DISTILL_PATH.exists())
check("использует промпт portrait.distill", PROMPT_PATH.exists() and "portrait.distill" in distill)
check("API list существует", API_LIST.exists())
check("API detail существует", API_DETAIL.exists())
check("API distill существует", API_DISTILL.exists())
check("группировка по сегментам", "age_group" in distill and "geo" in distill or "segment" in distill.lower())
check("версионирование (миграция 08)", MIGRATION.exists())

api_detail = API_DETAIL.read_text("utf-8") if API_DETAIL.exists() else ""
check("PUT для ручной правки", "PUT" in api_detail)

print("\n== Поведенческий уровень ==")
# Строка подключения берётся через db_dsn: в .env.local хост — имя сервиса
# compose, которое резолвится только внутри сети контейнеров. При запуске с
# хоста это давало FAIL «failed to resolve host postgres», читавшийся как
# поломка базы. См. evals/tests/_harness.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import db_dsn  # noqa: E402

base_url = os.environ.get("BASE_URL")

if not db_dsn():
    skip("авто-дистилляция → непустой .md", "нет DATABASE_URL")
    skip("ручная правка сохраняется", "нет DATABASE_URL")
    skip("версионирование работает", "нет DATABASE_URL")
elif not base_url:
    skip("авто-дистилляция → непустой .md", "BASE_URL не задан — запустите при поднятом сервере")
    skip("ручная правка сохраняется", "BASE_URL не задан")
    skip("версионирование работает", "BASE_URL не задан")
else:
    # Прежде все три пропускались безусловно — «требует LLM-вызова» и «требует
    # живой API» печатались даже при поднятом сервере и живой базе. Оба пункта
    # cdd задачи лежат именно здесь, поэтому задача стояла done, ни разу не
    # будучи проверенной.
    #
    # Модель при этом не нужна: у /api/portraits/distill параметр use_llm по
    # умолчанию false, и дистилляция считается из датасета. Гейт CANARY тут ни
    # при чём — реальных вызовов не делается.
    from _harness import login  # noqa: E402

    client, why = login(base_url)  # маршруты портретов требуют роли owner

    if client is None:
        skip("авто-дистилляция → непустой .md", why)
        skip("ручная правка сохраняется", why)
        skip("версионирование работает", why)
    else:
        code, body = client.call("/api/portraits/distill", "POST", json.dumps({}).encode())
        portraits = []
        if code == 200:
            try:
                portraits = (json.loads(body) or {}).get("portraits") or []
            except json.JSONDecodeError:
                portraits = []
        non_empty = [p for p in portraits if (p.get("body_md") or "").strip()]
        check(
            "авто-дистилляция → непустой .md",
            code == 200 and bool(non_empty),
            f"status={code}, сегментов={len(portraits)}, непустых={len(non_empty)}",
        )

        created = json.dumps(
            {"name": f"CDD-портрет {uuid.uuid4().hex[:8]}", "body_md": "# Первая редакция\n\nтекст"}
        ).encode()
        code, body = client.call("/api/portraits", "POST", created)
        portrait_id = ""
        if code == 200:
            try:
                portrait_id = ((json.loads(body) or {}).get("portrait") or {}).get("id", "")
            except json.JSONDecodeError:
                portrait_id = ""

        if not portrait_id:
            check("ручная правка сохраняется", False, f"портрет не создан: status={code}")
            check("версионирование работает", False, "нет портрета для правки")
        else:
            edited = "# Вторая редакция\n\nправка из CDD-прогона"
            code, _ = client.call(
                f"/api/portraits/{portrait_id}", "PUT", json.dumps({"body_md": edited}).encode()
            )
            put_ok = code == 200

            code2, body2 = client.call(f"/api/portraits/{portrait_id}")
            after, versions = {}, []
            if code2 == 200:
                try:
                    payload = json.loads(body2) or {}
                    after = payload.get("portrait") or {}
                    # Ключ ответа — history, не versions: getPortraitWithHistory
                    # возвращает { portrait, history }.
                    versions = payload.get("history") or []
                except json.JSONDecodeError:
                    pass

            check(
                "ручная правка сохраняется",
                put_ok and after.get("body_md") == edited,
                f"PUT={code}, GET={code2}, прочитано={(after.get('body_md') or '')[:40]!r}",
            )
            # Версионирование — не «поле version растёт», а «прежняя редакция
            # осталась доступной». Проверяется наличием более чем одной записи в
            # истории и присутствием исходного текста среди них.
            check(
                "версионирование работает",
                len(versions) >= 2
                and any("Первая редакция" in (v.get("body_md") or "") for v in versions),
                f"версий={len(versions)}, номера={[v.get('version') for v in versions]}",
            )

n_pass = sum(1 for _,s,_ in results if s=="OK"); n_fail = sum(1 for _,s,_ in results if s=="FAIL")
print(f"\n{'GREEN' if not n_fail else 'RED'} — pass={n_pass} fail={n_fail}")
sys.exit(1 if n_fail else 0)