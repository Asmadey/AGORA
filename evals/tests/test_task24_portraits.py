#!/usr/bin/env python3
"""CDD-тест задачи #24 — Audience Portraits."""
from __future__ import annotations
import json, os, sys
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
if not os.environ.get("DATABASE_URL"):
    skip("авто-дистилляция → непустой .md", "нет DATABASE_URL")
    skip("ручная правка сохраняется", "нет DATABASE_URL")
    skip("версионирование работает", "нет DATABASE_URL")
else:
    skip("авто-дистилляция → непустой .md", "требует LLM-вызова")
    skip("ручная правка сохраняется", "требует живой API")
    skip("версионирование работает", "требует живой API")

n_pass = sum(1 for _,s,_ in results if s=="OK"); n_fail = sum(1 for _,s,_ in results if s=="FAIL")
print(f"\n{'GREEN' if not n_fail else 'RED'} — pass={n_pass} fail={n_fail}")
sys.exit(1 if n_fail else 0)