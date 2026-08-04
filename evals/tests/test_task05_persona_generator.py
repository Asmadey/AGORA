#!/usr/bin/env python3
"""
CDD-тест задачи #5 — Persona Generator.

Двухуровневый по AGENTS.md §3:

**Статический уровень** (работает где угодно):
  1. Модуль генератора существует
  2. Генератор использует persona-dna.schema.json (валидация)
  3. Генератор использует промпт persona.generate.md
  4. Генератор seed-based (детерминизм)
  5. API-маршрут POST /api/personas/generate существует (FastAPI + Next.js)
  6. Методология PRD §10: калибровка по реальным средним
  7. Методология PRD §10: сэмплирование по реальным долям
  8. Методология PRD §10: заземление на verbatims

**Поведенческий уровень** (требует генератор, но не LLM):
  9.  На reference конфиге распределения age_group/geo/gender отклоняются
      от корпуса не более чем на 0.10 (метрика persona_grounding)
  10. Повторный прогон на том же seed → diff == 0
  11. Разный seed → разный результат (контракт детерминизма)
  12. Все сгенерированные персоны валидируются против JSON Schema

CDD из tasks.json:
  «на эталонном (reference) конфиге генерации распределения по
   age_group/geo/gender отклоняются от корпуса не более чем на 0.10;
   повторный прогон на том же seed → diff == 0»
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO / "packages" / "shared" / "schemas" / "persona-dna.schema.json"
FIXTURE_PATH = REPO / "evals" / "fixtures" / "persona_reference.json"
CORPUS_PATH = REPO / "data" / "grounding" / "unified_respondent_sessions.json"
PROMPT_PATH = REPO / "prompts" / "persona.generate.md"
GENERATOR_PATH = REPO / "services" / "agent-core" / "agent_core" / "persona" / "generator.py"
API_ROUTER_PATH = REPO / "services" / "agent-core" / "agent_core" / "api" / "routers" / "personas.py"
NEXTJS_ROUTE_PATH = REPO / "apps" / "web" / "app" / "api" / "personas" / "generate" / "route.ts"

PASS = "OK"
FAIL = "FAIL"
SKIP = "SKIP"

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


# ===========================================================================
# Static level
# ===========================================================================

print("== Статический уровень ==")

# --- 1. Generator module exists ---
generator_src = ""
try:
    generator_src = GENERATOR_PATH.read_text("utf-8")
    check("модуль генератора существует", True)
except Exception as e:
    check("модуль генератора существует", False, str(e))

if generator_src:
    check(
        "генератор импортирует схему (SCHEMA_PATH)",
        "persona-dna.schema.json" in generator_src or "SCHEMA_PATH" in generator_src,
    )
    check(
        "генератор seed-based (random.Random(seed))",
        "random.Random" in generator_src and "seed" in generator_src,
    )

# --- 2. Schema loads ---
schema = None
try:
    schema = json.loads(SCHEMA_PATH.read_text("utf-8"))
    check("schema загружается", isinstance(schema, dict))
except Exception as e:
    check("schema загружается", False, str(e))

# --- 3. Prompt exists ---
try:
    prompt_text = PROMPT_PATH.read_text("utf-8")
    check("промпт persona.generate.md существует", len(prompt_text) > 0)
    if generator_src:
        check(
            "генератор ссылается на промпт (PROMPT_PATH)",
            "persona.generate" in generator_src or "PROMPT_PATH" in generator_src,
        )
except Exception as e:
    check("промпт persona.generate.md существует", False, str(e))

# --- 4. Generator is seed-based ---
if generator_src:
    has_seed = "seed" in generator_src
    has_random = "random.Random" in generator_src or "random.seed" in generator_src
    check("генератор seed-based", has_seed and has_random)

# --- 5. API routes exist ---
try:
    api_src = API_ROUTER_PATH.read_text("utf-8")
    check("API-маршрут (FastAPI) существует", "/personas/generate" in api_src)
except Exception as e:
    check("API-маршрут (FastAPI) существует", False, str(e))

try:
    nextjs_src = NEXTJS_ROUTE_PATH.read_text("utf-8")
    check(
        "Next.js proxy route существует",
        "personas/generate" in nextjs_src,
    )
except Exception as e:
    check("Next.js proxy route существует", False, str(e))

# --- 6. PRD §10: calibration on real means ---
if generator_src:
    check(
        "калибровка по реальным средним (CORPUS_SCORE_MEANS)",
        "CORPUS_SCORE_MEANS" in generator_src or "score_means" in generator_src,
    )

# --- 7. PRD §10: sampling by real proportions ---
if generator_src:
    check(
        "сэмплирование по реальным долям (CorpusDistribution)",
        "CorpusDistribution" in generator_src and "serial_x_city" in generator_src,
    )

# --- 8. PRD §10: grounding on verbatims ---
if generator_src:
    check(
        "заземление на verbatims",
        "verbatim" in generator_src.lower(),
    )


# ===========================================================================
# Behavioral level — requires generator (no LLM needed)
# ===========================================================================

print("\n== Поведенческий уровень ==")

# Check if we can import the generator
generator_available = False
gen_cls = None
config_cls = None
corpus_dist_cls = None

try:
    agent_core_src = str(REPO / "services" / "agent-core")
    if agent_core_src not in sys.path:
        sys.path.insert(0, agent_core_src)
    from agent_core.persona.generator import (
        CorpusDistribution,
        GenerationConfig,
        PersonaGenerator,
    )

    generator_available = True
    gen_cls = PersonaGenerator
    config_cls = GenerationConfig
    corpus_dist_cls = CorpusDistribution
    check("генератор импортируется", True)
except Exception as e:
    check("генератор импортируется", False, str(e))


if generator_available:
    # Load corpus
    try:
        corpus_records = json.loads(CORPUS_PATH.read_text("utf-8"))
        corpus_dist = CorpusDistribution.from_corpus(corpus_records)
        check(
            "корпус загружен (165 записей)",
            len(corpus_records) == 165,
            f"записей: {len(corpus_records)}",
        )
    except Exception as e:
        check("корпус загружен", False, str(e))
        corpus_records = []
        corpus_dist = None

    if corpus_dist and corpus_records:
        # --- 9. Distribution deviation ≤ 0.10 ---
        # Reference config: size=165 (same as corpus), seed=42, no filters
        try:
            config = config_cls(size=165, seed=42)
            gen = gen_cls.from_corpus()
            personas = gen.generate(config)
            check(f"генерация {len(personas)} персон", len(personas) == 165)

            gen_age = Counter(p["demographics"]["age_group"] for p in personas)
            gen_geo = Counter(p["demographics"]["geo"] for p in personas)
            gen_gender = Counter(p["demographics"]["gender"] for p in personas)

            n = len(personas)
            gen_age_dist = {k: v / n for k, v in gen_age.items()}
            gen_geo_dist = {k: v / n for k, v in gen_geo.items()}
            gen_gender_dist = {k: v / n for k, v in gen_gender.items()}

            def max_deviation(gen_d: dict, corp_d: dict) -> float:
                all_keys = set(gen_d) | set(corp_d)
                return max(abs(gen_d.get(k, 0) - corp_d.get(k, 0)) for k in all_keys)

            age_dev = max_deviation(gen_age_dist, corpus_dist.age_group)
            geo_dev = max_deviation(gen_geo_dist, corpus_dist.geo)
            gender_dev = max_deviation(gen_gender_dist, corpus_dist.gender)

            check(
                "распределение age_group отклоняется ≤ 0.10",
                age_dev <= 0.10,
                f"max deviation = {age_dev:.4f}",
            )
            check(
                "распределение geo отклоняется ≤ 0.10",
                geo_dev <= 0.10,
                f"max deviation = {geo_dev:.4f}",
            )
            check(
                "распределение gender отклоняется ≤ 0.10",
                gender_dev <= 0.10,
                f"max deviation = {gender_dev:.4f}",
            )

        except Exception as e:
            check("генерация и распределения", False, str(e))

        # --- 10. Same seed → identical output (diff == 0) ---
        try:
            config_a = config_cls(size=20, seed=42)
            config_b = config_cls(size=20, seed=42)
            personas_a = gen.generate(config_a)
            personas_b = gen.generate(config_b)
            diff = json.dumps(personas_a, ensure_ascii=False, sort_keys=True) != json.dumps(
                personas_b, ensure_ascii=False, sort_keys=True
            )
            check("тот же seed → diff == 0", not diff, f"diff={'YES' if diff else 'NO'}")
        except Exception as e:
            check("тот же seed → diff == 0", False, str(e))

        # --- 11. Different seed → different result ---
        try:
            config_c = config_cls(size=20, seed=999)
            personas_c = gen.generate(config_c)
            diff_seed = json.dumps(personas_a, ensure_ascii=False, sort_keys=True) != json.dumps(
                personas_c, ensure_ascii=False, sort_keys=True
            )
            check("разный seed → разный результат", diff_seed, f"diff={'YES' if diff_seed else 'NO'}")
        except Exception as e:
            check("разный seed → разный результат", False, str(e))

        # --- 12. All generated personas validate against schema ---
        try:
            import jsonschema

            config_v = config_cls(size=20, seed=42)
            personas_v = gen.generate(config_v)
            invalid_count = 0
            errors: list[str] = []
            for i, p in enumerate(personas_v):
                try:
                    jsonschema.validate(p, schema)
                except jsonschema.ValidationError as ve:
                    invalid_count += 1
                    if len(errors) < 3:
                        errors.append(f"persona {i}: {ve.message} at {list(ve.path)}")
            check(
                f"все {len(personas_v)} персон валидируются против schema",
                invalid_count == 0,
                f"invalid: {invalid_count}" + (f"; {errors[0]}" if errors else ""),
            )
        except ImportError:
            skip("валидация против schema (jsonschema not installed)", "no jsonschema")
        except Exception as e:
            check("валидация против schema", False, str(e))

    else:
        skip("поведенческие тесты (корпус недоступен)", "corpus not loaded")

else:
    skip("поведенческие тесты (генератор не импортируется)", "generator import failed")


# ===========================================================================
# Summary
# ===========================================================================

print("\n" + "=" * 60)
passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)
skipped = sum(1 for _, s, _ in results if s == SKIP)
# Вердикт общий для всех тестов — см. _harness.verdict.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#5"))
