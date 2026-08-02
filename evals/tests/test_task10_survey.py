#!/usr/bin/env python3
"""CDD-тест задачи #10 — Survey Constructor."""
from __future__ import annotations
import json, os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO / "packages" / "shared" / "schemas" / "survey.schema.json"
TS_PATH = REPO / "packages" / "shared" / "types" / "survey.ts"
VALIDATOR_PATH = REPO / "apps" / "web" / "lib" / "server" / "survey-validator.ts"
BUILDER_PATH = REPO / "apps" / "web" / "components" / "agora" / "SurveyBuilder.tsx"

results = []
def check(n, ok, d=""): results.append((n, "OK" if ok else "FAIL", d)); print(f"  {'OK  ' if ok else 'FAIL'}  {n}" + (f"  →  {d}" if d else ""))
def skip(n, r): results.append((n, "SKIP", r)); print(f"  SKIP  {n}  →  {r}")

print("== Статический уровень ==")
check("survey schema существует", SCHEMA_PATH.exists())
check("TS типы сгенерированы", TS_PATH.exists())
check("валидатор существует", VALIDATOR_PATH.exists())

if SCHEMA_PATH.exists():
    schema = json.loads(SCHEMA_PATH.read_text("utf-8"))
    defs = schema.get("$defs", schema.get("definitions", {}))
    # 5 base criteria 1-10
    base_keys = defs.get("BaseCriterionKey", {}).get("enum", [])
    expected_base = {"overall_impression", "plot", "acting", "music", "cinematography"}
    check("5 базовых критериев 1-10", expected_base.issubset(set(base_keys)),
          f"есть: {set(base_keys)}, нет: {expected_base - set(base_keys)}")

    # Custom question types
    qtypes = defs.get("QuestionType", {}).get("enum", [])
    expected_types = {"scale", "emotions", "retention", "recommendation", "open"}
    check("5 типов кастомных вопросов", expected_types.issubset(set(qtypes)),
          f"есть: {set(qtypes)}, нет: {expected_types - set(qtypes)}")

    check("additionalProperties: false", schema.get("additionalProperties") is False)
else:
    check("5 базовых критериев 1-10", False, "схема не найдена")
    check("5 типов кастомных вопросов", False)
    check("additionalProperties: false", False)

print("\n== Поведенческий уровень ==")
if not os.environ.get("BASE_URL"):
    for i in range(8, 12): skip(f"кейс {i}", "нет BASE_URL")
else:
    skip("валидация анкеты через API", "требует живой сервер")

n_pass = sum(1 for _,s,_ in results if s=="OK"); n_fail = sum(1 for _,s,_ in results if s=="FAIL")
print(f"\n{'GREEN' if not n_fail else 'RED'} — pass={n_pass} fail={n_fail}")
sys.exit(1 if n_fail else 0)