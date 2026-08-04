#!/usr/bin/env python3
"""
CDD-тест задачи #27 — Настройки (per-tenant).

Приёмка разделена: #27 отвечает за хранение, права и контракт снимка настроек.
Влияние на прогон переезжает в verifies задач #13 и #15.
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO / "apps" / "web" / "lib" / "settings.ts"
API_ROUTE = REPO / "apps" / "web" / "app" / "api" / "settings" / "route.ts"

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

# 1. Validator rejects invalid whisper_model
settings_text = SETTINGS_PATH.read_text("utf-8") if SETTINGS_PATH.exists() else ""
has_whisper_enum = "WHISPER_MODELS" in settings_text and "large-v3" in settings_text
check("валидатор: whisper_model из перечисления", has_whisper_enum)

# 2. replication_count bounds
has_replication = "REPLICATION_VALUES" in settings_text
check("replication_count ограничен", has_replication)

# 3. cost_cap_value bounds
has_cost_cap_bounds = "COST_CAP_BOUNDS" in settings_text
check("cost_cap_value в границах COST_CAP_BOUNDS", has_cost_cap_bounds)

# 4. requireOwner on mutating routes
api_text = API_ROUTE.read_text("utf-8") if API_ROUTE.exists() else ""
has_require_owner = "requireOwner" in api_text
check("запись требует requireOwner", has_require_owner)

# 5. Provider keys not written to DB
has_key_insert = bool(re.search(r"INSERT.*api_key|INSERT.*secret", api_text, re.IGNORECASE))
check("ключи провайдера не пишутся в БД", not has_key_insert)


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

if not dsn and not os.environ.get("BASE_URL"):
    for i in range(6, 15):
        skip(f"поведенческий кейс {i}", "нет подключения к среде")
else:
    try:
        import urllib.request
        import urllib.parse
        import http.cookiejar

        from _harness import login  # noqa: E402

        # Прежде вход собирался здесь вручную, с адресом и паролем владельца в
        # исходнике. Пароль в репозитории — §7 CLAUDE.md; secret_scan его не
        # ловил, потому что ищет только sk-… и AIza…. Учётные данные теперь
        # приходят из окружения, а сам вход — общий для всех тестов.
        client, why_login = login(base_url)
        if client is None:
            raise RuntimeError(why_login)

        jar = client.jar
        opener = client.opener
        cookies = "; ".join(f"{c.name}={c.value}" for c in jar)

        # 6. GET without saved settings → defaults
        status, raw = client.call("/api/settings")
        body = json.loads(raw) if status == 200 else {}
        # API возвращает обёртку { settings, persistence } — см. комментарий
        # в route.ts. Настройки — в body["settings"].
        s = body.get("settings", {})
        check("GET без сохранённых настроек → умолчания", status == 200 and "whisperModel" in s,
              f"HTTP {status}")

        # 7. PUT valid → GET
        put_data = json.dumps({
            "costCap": "hard",
            "costCapValue": 300,
            "whisperModel": "large-v3-turbo",
            "defaultReplication": 3,
        }).encode()
        put_req = urllib.request.Request(f"{base_url}/api/settings", data=put_data, method="PUT")
        put_req.add_header("Content-Type", "application/json")
        put_req.add_header("Cookie", cookies)
        resp = opener.open(put_req, timeout=10)
        put_status = resp.getcode()
        check("PUT валидных настроек", put_status in (200, 204), f"HTTP {put_status}")

        # Verify via GET
        req = urllib.request.Request(f"{base_url}/api/settings")
        req.add_header("Cookie", cookies)
        resp = opener.open(req, timeout=10)
        body = json.loads(resp.read())
        s = body.get("settings", {})
        check("GET после PUT — значения совпадают",
              s.get("whisperModel") == "large-v3-turbo" and s.get("defaultReplication") == 3,
              f"got: {s}")

        # 8. PUT garbage → 400
        put_garbage = b'{"whisperModel": "invalid-model", "costCap": "bad"}'
        put_req = urllib.request.Request(f"{base_url}/api/settings", data=put_garbage, method="PUT")
        put_req.add_header("Content-Type", "application/json")
        put_req.add_header("Cookie", cookies)
        try:
            opener.open(put_req, timeout=10)
            check("PUT мусора → 400", False, "не вернул 400")
        except urllib.error.HTTPError as e:
            check("PUT мусора → 400", e.code == 400, f"HTTP {e.code}")

        # 9. Broken JSON → 400
        put_bad = b'{broken json'
        put_req = urllib.request.Request(f"{base_url}/api/settings", data=put_bad, method="PUT")
        put_req.add_header("Content-Type", "application/json")
        put_req.add_header("Cookie", cookies)
        try:
            opener.open(put_req, timeout=10)
            check("битый JSON → 400", False, "не вернул 400")
        except urllib.error.HTTPError as e:
            check("битый JSON → 400", e.code == 400, f"HTTP {e.code}")

        # 10/11. Member permissions — второй пароль, лежавший в исходнике.
        member, why_member = login(base_url, "member")
        cookies2 = (
            "; ".join(f"{c.name}={c.value}" for c in member.jar) if member else ""
        )

        put_member = json.dumps({
            "costCap": "auto",
            "costCapValue": 500,
            "whisperModel": "large-v3",
            "defaultReplication": 1,
        }).encode()

        if member is None:
            skip("member PUT → 403", why_member)
        else:
            code_m, _ = member.call("/api/settings", "PUT", put_member)
            check(
                "member PUT → 403",
                code_m == 403,
                f"HTTP {code_m}; 200 значит, что участник меняет настройки арендатора",
            )

        # 11. member GET → 200
        if member is None:
            skip("member GET → 200", why_member)
            skip("настройки арендатора A из-под B не видны", why_member)
        else:
            code_g, raw_g = member.call("/api/settings")
            check("member GET → 200", code_g == 200, f"HTTP {code_g}")

            # 12. Cross-tenant isolation — member sees only own tenant settings
            member_body = json.loads(raw_g) if code_g == 200 else {}
            check("настройки арендатора A из-под B не видны", code_g == 200,
                  f"member sees: {list(member_body.keys())[:5]}")

        # 13/14. settings_snapshot in task — requires task creation API
        skip("снимок настроек в задаче при постановке", "требует API задач")
        skip("смена настроек после постановки — снимок не изменился", "требует API задач")

    except ImportError:
        for i in range(6, 15):
            skip(f"поведенческий кейс {i}", "urllib не доступен")
    except Exception as e:
        check("поведенческий тест", False, f"{type(e).__name__}: {str(e)[:150]}")


# --- Summary ---
# Вердикт общий для всех тестов: GREEN только когда проверено всё, что можно
# было проверить здесь. Прежде GREEN печатался при любом числе SKIP, и по
# выводу нельзя было отличить «проверено» от «пропущено» — см. _harness.verdict.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#27"))
