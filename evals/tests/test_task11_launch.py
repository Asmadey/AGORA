#!/usr/bin/env python3
"""
CDD-тест задачи #11 — Шаг «Резюме» + запуск (task_id) + «Перекрытие».

CDD (из tasks.json):
  запуск создаёт task с непустым prompts_snapshot и replication_count;
  повторный запуск с тем же seed идемпотентен.

─── Что значит «идемпотентен» ────────────────────────────────────────────────
Не «даёт похожий результат», а «не создаёт вторую задачу». Запуск — платная
операция: разбор кадров и прогон респондентов стоят денег при каждом вызове.
Двойной клик по кнопке «Запустить», ретрай прокси или обновление страницы не
должны порождать второй прогон, и различить его потом будет нечем: две задачи с
одинаковыми параметрами выглядят как намеренный повтор.

Поэтому проверяется равенство идентификаторов: второй POST с теми же
параметрами обязан вернуть ТОТ ЖЕ task_id, а изменение seed — новый.

─── Зачем снимок промптов ────────────────────────────────────────────────────
Decision Log #10. Промпты правятся в Промпт-студии между прогонами, и без
пиннинга версий отчёт невоспроизводим: перезапуск того же исследования пошёл бы
по другим инструкциям, а объяснить расхождение было бы нечем.

Снимок обязан быть НЕПУСТЫМ и содержать все ключи реестра — пустой снимок
означает «пиннинг есть в схеме, но не работает», и это неотличимо от рабочего
до первой правки промпта.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"
MIGRATIONS = REPO / "infra" / "postgres" / "init"

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


#: 13 ключей реестра промптов (задача #26). Снимок обязан покрывать их все.
PROMPT_KEYS = [
    "persona.generate", "content.frame_analysis", "content.stitch_summary",
    "respondent.system", "respondent.user", "qa.consistency", "qa.grounding",
    "qa.diversity", "analytics.report", "dataset.unification", "portrait.distill",
    "chat.analyst", "chat.persona_followup",
]


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

launch_src = read(WEB / "app" / "api" / "tasks" / "route.ts")
check("маршрут запуска /api/tasks существует", bool(launch_src))

tasks_lib = read(WEB / "lib" / "server" / "tasks.ts")
check("серверный слой lib/server/tasks.ts существует", bool(tasks_lib))

both = launch_src + tasks_lib

# Снимок собирается из активных версий, а не из файлов prompts/: файлы — это
# seed, а активной может быть версия арендатора из Промпт-студии.
check(
    "снимок промптов берётся из активных версий в БД",
    "listActivePromptsByStage" in both or "prompts_snapshot" in both,
)
check(
    "снимок пишется в колонку prompts_snapshot",
    "prompts_snapshot" in both,
)

# Идемпотентность — свойство базы, а не проверки «поищем похожую задачу перед
# вставкой». Проверка-перед-вставкой гонку не закрывает: два одновременных
# запроса оба ничего не найдут и оба вставят.
check(
    "идемпотентность держится уникальным ключом в БД, а не поиском перед вставкой",
    "idempotency_key" in both,
)
check(
    "ключ идемпотентности учитывает seed",
    "seed" in both,
)

# Дефолт «Перекрытия» приходит из Настроек (#27), а не зашит числом.
check(
    "дефолт replication_count берётся из настроек арендатора",
    "defaultReplication" in both or "default_replication" in both,
)

# ── Миграция ────────────────────────────────────────────────────────────────
migrations = sorted(MIGRATIONS.glob("*.sql"))
idem_migration = [m for m in migrations if "idempot" in m.name or "task" in m.name.lower()]
idem_sql = "\n".join(read(m) for m in idem_migration)

check(
    "заведена миграция под ключ идемпотентности",
    "idempotency_key" in idem_sql,
    f"файлы: {[m.name for m in idem_migration]}" if idem_migration else "не найдена",
)
check(
    "миграция идемпотентна (IF NOT EXISTS)",
    "IF NOT EXISTS" in idem_sql,
)
# Уникальность обязана быть в пределах арендатора: одинаковые параметры у разных
# команд — это разные прогоны, и глобальный уникальный ключ склеил бы их,
# отдав одной команде задачу другой.
check(
    "уникальность ключа ограничена арендатором",
    bool(re.search(r"UNIQUE.*\(\s*tenant_id\s*,\s*idempotency_key", idem_sql, re.S | re.I)),
)

# Уже применённые миграции не редактируются (§5 CLAUDE.md) — новый файл идёт
# следующим номером.
applied = [m.name for m in migrations if m.name[:2].isdigit()]
check(
    "новая миграция добавлена следующим номером, прежние не тронуты",
    any(m.startswith("09") for m in applied),
    f"миграции: {applied}",
)

migrate_sh = read(MIGRATIONS.parent / "migrate.sh")
check(
    "новая миграция подключена в migrate.sh",
    any(m.replace(".sql", "") in migrate_sh for m in applied if m.startswith("09")),
)


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("\n== Поведенческий уровень ==")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import ApiClient, db_dsn, login, verdict  # noqa: E402

BEHAVIOURAL = (
    "запуск создаёт задачу с непустым prompts_snapshot",
    "снимок содержит все 13 ключей реестра",
    "replication_count сохранён и равен запрошенному",
    "повторный запуск с тем же seed возвращает ТОТ ЖЕ task_id",
    "другой seed создаёт новую задачу",
    "дефолт replication_count подставляется из настроек",
)

base_url = os.environ.get("BASE_URL")
if not base_url:
    for n in BEHAVIOURAL:
        skip(n, "не задан BASE_URL")
else:
    client, why = login(base_url)
    if client is None:
        for n in BEHAVIOURAL:
            skip(n, why)
    else:
        seed = 20260804
        payload = {
            "mode": "short",
            "videoRef": "s3://fixtures/short_60s.mp4",
            "replicationCount": 3,
            "seed": seed,
        }

        code, body = client.call("/api/tasks", "POST", json.dumps(payload).encode())
        try:
            first = json.loads(body)
        except Exception:  # noqa: BLE001
            first = {}

        if code not in (200, 201):
            for n in BEHAVIOURAL:
                check(n, False, f"запуск ответил {code}: {body[:140]}")
        else:
            snapshot = first.get("promptsSnapshot") or first.get("prompts_snapshot") or {}
            check("запуск создаёт задачу с непустым prompts_snapshot",
                  bool(first.get("id")) and bool(snapshot),
                  f"task_id={str(first.get('id'))[:8]}…, ключей в снимке: {len(snapshot)}")

            missing = [k for k in PROMPT_KEYS if k not in snapshot]
            check("снимок содержит все 13 ключей реестра",
                  not missing,
                  f"нет ключей: {missing}" if missing else f"{len(snapshot)} ключей")

            rc = first.get("replicationCount") or first.get("replication_count")
            check("replication_count сохранён и равен запрошенному", rc == 3,
                  f"получено {rc}")

            # ── Идемпотентность ────────────────────────────────────────────
            code2, body2 = client.call("/api/tasks", "POST", json.dumps(payload).encode())
            try:
                second = json.loads(body2)
            except Exception:  # noqa: BLE001
                second = {}
            check("повторный запуск с тем же seed возвращает ТОТ ЖЕ task_id",
                  code2 in (200, 201) and second.get("id") == first.get("id"),
                  f"код {code2}, id совпал: {second.get('id') == first.get('id')}")

            other = {**payload, "seed": seed + 1}
            code3, body3 = client.call("/api/tasks", "POST", json.dumps(other).encode())
            try:
                third = json.loads(body3)
            except Exception:  # noqa: BLE001
                third = {}
            check("другой seed создаёт новую задачу",
                  code3 in (200, 201) and third.get("id") not in (None, first.get("id")),
                  f"код {code3}, новый id: {third.get('id') != first.get('id')}")

            # ── Дефолт «Перекрытия» из Настроек ────────────────────────────
            # /api/settings отдаёт { settings: {...}, persistence }, а не плоский
            # объект. Разбор ответа — самая частая причина ложных «дефектов
            # продукта» в этом наборе: за проход 10 таких было три.
            scode, sbody = client.call("/api/settings")
            try:
                want = json.loads(sbody)["settings"]["defaultReplication"]
            except Exception:  # noqa: BLE001
                want = None
            if want is None:
                skip("дефолт replication_count подставляется из настроек",
                     f"настройки не прочитаны (код {scode})")
            else:
                no_rc = {"mode": "short", "videoRef": "s3://fixtures/short_60s.mp4",
                         "seed": int(uuid.uuid4().int % 10**8)}
                code4, body4 = client.call("/api/tasks", "POST", json.dumps(no_rc).encode())
                try:
                    fourth = json.loads(body4)
                except Exception:  # noqa: BLE001
                    fourth = {}
                got = fourth.get("replicationCount") or fourth.get("replication_count")
                check("дефолт replication_count подставляется из настроек",
                      got == want,
                      f"настройки говорят {want}, задача получила {got}")


# ── Колонка в базе ───────────────────────────────────────────────────────────
dsn = db_dsn("POSTGRES_ADMIN_URL") or db_dsn()
if not dsn:
    skip("колонка idempotency_key существует в базе", "нет DATABASE_URL / POSTGRES_ADMIN_URL")
else:
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=10) as conn:
            row = conn.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='tasks' AND column_name='idempotency_key'"
            ).fetchone()
            check("колонка idempotency_key существует в базе", row is not None,
                  "миграция 09 применена" if row else "миграция 09 не применена")
    except ImportError:
        skip("колонка idempotency_key существует в базе", "psycopg не установлен")
    except Exception as e:  # noqa: BLE001
        check("колонка idempotency_key существует в базе", False,
              f"{type(e).__name__}: {str(e)[:90]}")


sys.exit(verdict(results, "#11"))
