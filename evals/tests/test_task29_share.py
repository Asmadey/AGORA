#!/usr/bin/env python3
"""CDD-тест задачи #29 - публичная ссылка на результат.

Требования взяты из полей ``cdd`` и ``acceptance`` в evals/state/tasks.json.
Статический уровень проверяет границы публичного доступа, токен и RLS.
Поведенческий уровень идёт через HTTP и не требует входа для самой ссылки.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"
INIT = REPO / "infra" / "postgres" / "init"

SHARE_DIALOG = WEB / "components" / "agora" / "ShareDialog.tsx"
SHARE_API = WEB / "app" / "api" / "tasks" / "[id]" / "share" / "route.ts"
SHARE_PAGE = WEB / "app" / "share" / "[token]" / "page.tsx"
TIMELINE_API = WEB / "app" / "share" / "[token]" / "timeline" / "route.ts"
AUTH = WEB / "lib" / "server" / "auth.config.ts"
TOKEN = WEB / "lib" / "server" / "share-token.ts"
SCOPE = WEB / "lib" / "share-scope.ts"
RLS = INIT / "03_rls.sql"
TASK_POLICY = INIT / "39_share_reads_its_run.sql"

results: list[tuple[str, str, str]] = []


def read(path: Path) -> str:
    return path.read_text("utf-8") if path.exists() else ""


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, "OK" if ok else "FAIL", detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  ->  {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, "SKIP", reason))
    print(f"  SKIP  {name}  ->  {reason}")


print("== Статический уровень ==")

dialog = read(SHARE_DIALOG)
api = read(SHARE_API)
page = read(SHARE_PAGE)
timeline = read(TIMELINE_API)
auth = read(AUTH)
token = read(TOKEN)
scope = read(SCOPE)
rls = read(RLS)
task_policy = read(TASK_POLICY)

check("кнопка «Поделиться» есть на экране отчёта", "ShareDialog" in read(WEB / "app" / "runs" / "[id]" / "page.tsx"))
check("диалог выпускает ссылку через API", "POST" in dialog and "/api/tasks/${runId}/share" in dialog)
check("токен выпускается сервером криптостойко", "randomBytes" in token and "TOKEN_BYTES = 32" in token)
check("в базу сохраняется отпечаток токена", "hashToken(token)" in api and "token_hash" in api)
check("TTL настраивается и передаётся в API", "TTL_OPTIONS" in dialog and "ttl" in api and "expiresAt" in api)
check("кнопка отзыва вызывает DELETE", "DELETE" in api and "method: \"DELETE\"" in dialog)
check("есть список активных ссылок", "active" in dialog.lower() and ("GET" in api or "list" in api.lower()))
check("публичный маршрут разрешён без сессии", '"/share"' in auth and "withShareToken" in page)
check("публичная страница читает полный отчёт и персоны", "loadReport" in page and "loadReportPersonas" in page and "<ReportBody" in page)
check("режим без поимённых персон является отдельной опцией", "aggregate" in dialog and "parseScope" in page and "showsSection" in scope)
check("публичная страница не содержит мутаций и чата", "ShareDialog" not in page and "DeleteRunButton" not in page and "fetch(" not in page)
check("просмотр пишет запись в аудит-лог", "INSERT INTO report_share_views" in page and "report_share_views_public_insert" in rls)
check("RLS-обход ограничен ролью и живым токеном", "TO agora_share" in rls and "current_share_token_hash" in rls and "FORCE ROW LEVEL SECURITY" in rls)
check("доступ к материалу по ссылке read-only", "GET" in timeline and "INSERT" not in timeline and "UPDATE" not in timeline and "DELETE" not in timeline)
check("публичная политика задач даёт ровно прогон ссылки", "tasks_public_share_read" in task_policy and "s.task_id = tasks.id" in task_policy)
check("истёкший TTL закрывает ссылку HTTP 410", "status: 410" in page or "status: 410" in timeline)
check("отозванная ссылка закрывается HTTP 410", "status: 410" in page or "status: 410" in timeline)
check("подобранный токен получает HTTP 404", "status: 404" in timeline or "status: 404" in page)

print("\n== Поведенческий уровень ==")

base_url = os.environ.get("BASE_URL")
if not base_url:
    for name in (
        "валидная ссылка открывается без логина и отдаёт один отчёт",
        "чужой или подобранный токен -> 404",
        "отзыв закрывает ранее выданную ссылку",
        "истёкший TTL закрывает ссылку -> 410",
        "просмотр попадает в аудит-лог",
    ):
        skip(name, "BASE_URL не задан - нужен поднятый сервер и готовый отчёт")
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _harness import login, verdict  # noqa: E402

    owner, why = login(base_url)
    if owner is None:
        for name in (
            "валидная ссылка открывается без логина и отдаёт один отчёт",
            "чужой или подобранный токен -> 404",
            "отзыв закрывает ранее выданную ссылку",
            "истёкший TTL закрывает ссылку -> 410",
            "просмотр попадает в аудит-лог",
        ):
            skip(name, why)
    else:
        code, raw = owner.call("/api/tasks")
        try:
            tasks = json.loads(raw).get("tasks") or []
        except (TypeError, json.JSONDecodeError):
            tasks = []
        ready = [task for task in tasks if task.get("status") == "REPORT_READY"]
        if not ready:
            for name in (
                "валидная ссылка открывается без логина и отдаёт один отчёт",
                "чужой или подобранный токен -> 404",
                "отзыв закрывает ранее выданную ссылку",
                "просмотр попадает в аудит-лог",
            ):
                skip(name, "нет REPORT_READY-прогона, на который можно выпустить ссылку")
            skip("истёкший TTL закрывает ссылку -> 410", "нужна заранее созданная просроченная ссылка или управляемые часы")
        else:
            task_id = ready[0].get("id")
            code, raw = owner.call(
                f"/api/tasks/{task_id}/share",
                "POST",
                json.dumps({"ttl": "24h", "scope": "full"}).encode(),
            )
            try:
                share = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                share = {}
            url = share.get("url")
            if not url:
                for name in (
                    "валидная ссылка открывается без логина и отдаёт один отчёт",
                    "чужой или подобранный токен -> 404",
                    "отзыв закрывает ранее выданную ссылку",
                    "просмотр попадает в аудит-лог",
                ):
                    check(name, False, f"POST выпуска ссылки: HTTP {code}: {raw[:160]}")
                skip("истёкший TTL закрывает ссылку -> 410", "ссылка не выпущена")
            else:
                # Отдельный opener без cookie доказывает именно публичный путь.
                try:
                    with urllib.request.urlopen(url, timeout=30) as response:
                        body = response.read().decode("utf-8", "replace")
                        public_code = response.status
                    check(
                        "валидная ссылка открывается без логина и отдаёт один отчёт",
                        public_code == 200 and body.count("Отчёт исследования") == 1,
                        f"HTTP {public_code}, заголовков отчёта: {body.count('Отчёт исследования')}",
                    )
                except Exception as exc:  # noqa: BLE001
                    check("валидная ссылка открывается без логина и отдаёт один отчёт", False, str(exc)[:160])

                guessed = url.rsplit("/", 1)[0] + "/definitely-not-a-token"
                try:
                    with urllib.request.urlopen(guessed, timeout=30) as response:
                        guessed_code = response.status
                except urllib.error.HTTPError as exc:
                    guessed_code = exc.code
                check("чужой или подобранный токен -> 404", guessed_code == 404, f"HTTP {guessed_code}")

                revoke_code, _ = owner.call(f"/api/tasks/{task_id}/share", "DELETE")
                try:
                    with urllib.request.urlopen(url, timeout=30) as response:
                        revoked_code = response.status
                except urllib.error.HTTPError as exc:
                    revoked_code = exc.code
                check(
                    "отзыв закрывает ранее выданную ссылку",
                    revoke_code in (200, 204) and revoked_code == 410,
                    f"DELETE HTTP {revoke_code}, ссылка HTTP {revoked_code}",
                )
                skip("просмотр попадает в аудит-лог", "проверка требует чтения report_share_views под владельцем")
                skip("истёкший TTL закрывает ссылку -> 410", "нужна заранее созданная просроченная ссылка или управляемые часы")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#29 Публичная ссылка"))
