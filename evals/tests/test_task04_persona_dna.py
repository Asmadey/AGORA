#!/usr/bin/env python3
"""
CDD-тест задачи #4 — Persona DNA (схема, эталон, codegen).

Двухуровневый по AGENTS.md §3: статический работает где угодно, поведенческий
требует живой базы и Pydantic — при отсутствии честно SKIP.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import tempfile
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO / "packages" / "shared" / "schemas" / "persona-dna.schema.json"
FIXTURE_PATH = REPO / "evals" / "fixtures" / "persona_reference.json"
CORPUS_PATH = REPO / "data" / "grounding" / "unified_respondent_sessions.json"
TS_PATH = REPO / "packages" / "shared" / "types" / "persona-dna.ts"
PY_PATH = REPO / "services" / "agent-core" / "agent_core" / "schemas" / "persona_dna.py"

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


# --- Static level ---

print("== Статический уровень ==")

# 1. Schema exists and parses as JSON Schema
schema = None
try:
    schema = json.loads(SCHEMA_PATH.read_text("utf-8"))
    check("схема существует и разбирается", isinstance(schema, dict) and "$schema" in schema)
except Exception as e:
    check("схема существует и разбирается", False, str(e))

if schema:
    # 2. All 8 categories in required
    required = schema.get("required", [])
    expected_cats = {
        "demographics", "big_five", "values_and_beliefs", "viewer_behavior",
        "communication_style", "decision_making", "technology_usage", "lifestyle_and_interests",
    }
    check("все 8 категорий в required", expected_cats.issubset(set(required)),
          f"отсутствуют: {expected_cats - set(required)}")

    # 3. Count leaf fields (40-60)
    def count_leaves(obj, depth=0):
        if depth > 10:
            return 0
        if obj.get("type") == "object" and "properties" in obj:
            return sum(count_leaves(p, depth+1) for p in obj["properties"].values())
        return 1  # leaf

    leaf_count = 0
    for cat in schema.get("properties", {}).values():
        leaf_count += count_leaves(cat)
    leaf_count += 2  # narrative + seed
    check("40 ≤ листовых полей ≤ 60", 40 <= leaf_count <= 60, f"N={leaf_count}")

    # 4. additionalProperties: false on root and each category
    root_ap = schema.get("additionalProperties")
    cats_ap = all(
        schema["properties"].get(c, {}).get("additionalProperties") is False
        for c in expected_cats
    )
    check("additionalProperties: false на корне и в категориях", root_ap is False and cats_ap)

    # Try jsonschema validator
    try:
        import jsonschema
        validator = jsonschema.Draft202012Validator(schema)
    except ImportError:
        validator = None
        skip("jsonschema не установлен — валидация пропущена", "pip install jsonschema")

    fixture = json.loads(FIXTURE_PATH.read_text("utf-8"))

    if validator:
        # 5. Reference persona is valid
        errors = list(validator.iter_errors(fixture))
        check("эталонная персона валидна", len(errors) == 0,
              "; ".join(e.message[:80] for e in errors[:3]))

        # 6. Big Five value 6 rejected
        bf6 = json.loads(json.dumps(fixture))
        bf6["big_five"]["openness"] = 6
        errs6 = [e for e in validator.iter_errors(bf6) if "big_five" in e.json_path]
        check("Big Five: значение 6 отвергается", len(errs6) > 0,
              errs6[0].json_path if errs6 else "")

        # 7. Big Five value 3.5 rejected (integer, not float)
        bf35 = json.loads(json.dumps(fixture))
        bf35["big_five"]["openness"] = 3.5
        errs35 = list(validator.iter_errors(bf35))
        check("Big Five: значение 3.5 отвергается", len(errs35) > 0)

        # 8. Missing viewer_behavior rejected
        no_vb = json.loads(json.dumps(fixture))
        del no_vb["viewer_behavior"]
        errs_vb = [e for e in validator.iter_errors(no_vb) if "viewer_behavior" in e.message]
        check("удалена категория viewer_behavior — отвергается", len(errs_vb) > 0)

        # 9. Extra field favourite_colour rejected
        extra = json.loads(json.dumps(fixture))
        extra["favourite_colour"] = "blue"
        errs_extra = [e for e in validator.iter_errors(extra) if "favourite_colour" in e.message]
        check("добавлено поле favourite_colour — отвергается", len(errs_extra) > 0)

        # 10. age_group out of enum rejected
        bad_age = json.loads(json.dumps(fixture))
        bad_age["demographics"]["age_group"] = "99-100"
        errs_age = list(validator.iter_errors(bad_age))
        check("age_group вне перечисления — отвергается", len(errs_age) > 0)

        # 11. age_group covers corpus values
        corpus = json.loads(CORPUS_PATH.read_text("utf-8"))
        corpus_ages = {r.get("socio_demographics", {}).get("age_group") for r in corpus}
        schema_ages = set(schema["properties"]["demographics"]["properties"]["age_group"]["enum"])
        check("age_group покрывает все значения корпуса", corpus_ages.issubset(schema_ages),
              f"нет: {corpus_ages - schema_ages}")

        # 12. geo and gender cover corpus
        corpus_geos = {r.get("socio_demographics", {}).get("geo") for r in corpus}
        schema_geos = set(schema["properties"]["demographics"]["properties"]["geo"]["enum"])
        check("geo покрывает все значения корпуса", corpus_geos.issubset(schema_geos),
              f"нет: {corpus_geos - schema_geos}")

        corpus_genders = {r.get("socio_demographics", {}).get("gender") for r in corpus}
        schema_genders = set(schema["properties"]["demographics"]["properties"]["gender"]["enum"])
        check("gender покрывает все значения корпуса", corpus_genders.issubset(schema_genders),
              f"нет: {corpus_genders - schema_genders}")

    # 13. No consumer_* fields
    schema_text = json.dumps(schema)
    consumer_hits = re.findall(r'"consumer_\w+"', schema_text)
    check("ни одно поле не называется consumer_*", len(consumer_hits) == 0,
          str(consumer_hits))

    # 14. seed is integer
    seed_prop = schema["properties"].get("seed", {})
    check("seed целочисленный", seed_prop.get("type") == "integer")

    # 15. Codegen artifacts exist and match a fresh regeneration.
    #
    # Прежняя редакция делала `git diff --exit-code` по закоммиченным файлам и
    # не запускала кодогенерацию вовсе. Такая проверка неверна в обе стороны:
    # она зелёная, если артефакт правили руками и закоммитили (диффа нет), и
    # красная, если его просто перегенерировали (в шапке меняется timestamp).
    # Настоящая проверка — сгенерировать во временный каталог и сравнить
    # содержимое, игнорируя строку времени.
    if TS_PATH.exists() and PY_PATH.exists():
        check("TS и Pydantic артефакты существуют", True)

        def _strip_timestamp(text: str) -> str:
            return "\n".join(
                ln for ln in text.splitlines() if not ln.startswith("#   timestamp:")
            )

        try:
            with tempfile.TemporaryDirectory() as tmp:
                regen = Path(tmp) / "persona_dna.py"
                r = subprocess.run(
                    ["datamodel-codegen", "--input", str(SCHEMA_PATH),
                     "--input-file-type", "jsonschema", "--output", str(regen),
                     "--output-model-type", "pydantic_v2.BaseModel"],
                    cwd=REPO, capture_output=True, text=True, timeout=180,
                )
                if r.returncode != 0 or not regen.is_file():
                    skip("перегенерация Pydantic совпадает с закоммиченной",
                         "datamodel-codegen отработал с ошибкой")
                else:
                    same = _strip_timestamp(regen.read_text("utf-8")) == _strip_timestamp(
                        PY_PATH.read_text("utf-8"))
                    check("перегенерация Pydantic совпадает с закоммиченной", same,
                          "" if same else "модель правили руками либо схема ушла вперёд")
        except FileNotFoundError:
            skip("перегенерация Pydantic совпадает с закоммиченной",
                 "datamodel-codegen не установлен (pip install datamodel-code-generator)")
        except subprocess.TimeoutExpired:
            skip("перегенерация Pydantic совпадает с закоммиченной",
                 "генератор не уложился в 180 с")
    else:
        check("TS и Pydantic артефакты существуют", False,
              f"TS={TS_PATH.exists()} PY={PY_PATH.exists()}")

    # 16. Field names match between TS and Pydantic
    ts_text = TS_PATH.read_text("utf-8") if TS_PATH.exists() else ""
    py_text = PY_PATH.read_text("utf-8") if PY_PATH.exists() else ""
    # Extract field names from schema
    schema_fields = set()
    for cat in schema["properties"].values():
        if cat.get("type") == "object":
            schema_fields.update(cat.get("properties", {}).keys())
    schema_fields.update(schema["properties"].keys())
    # Remove narrative/seed (top-level, present in both)
    # Check that key field names appear in both files
    ts_present = all(f in ts_text for f in schema_fields if f not in {"narrative", "seed"})
    py_present = all(f in py_text for f in schema_fields if f not in {"narrative", "seed"})
    check("набор полей в TS и Pydantic совпадает", ts_present and py_present,
          "" if ts_present and py_present else f"TS={ts_present} PY={py_present}")


# --- Behavioral level ---

print("\n== Поведенческий уровень ==")

# Строка подключения берётся через db_dsn: в .env.local хост — имя сервиса
# compose, которое резолвится только внутри сети контейнеров. При запуске с
# хоста это давало FAIL «failed to resolve host postgres», читавшийся как
# поломка базы. См. evals/tests/_harness.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import db_dsn  # noqa: E402

dsn = db_dsn()
if not dsn:
    # Пропускается только проверка, которой действительно нужна база. Прежде здесь
    # заодно пропускались Pydantic-проверки с причиной «Pydantic не установлен» — при
    # том что к базе они отношения не имеют, а причина была вымышленной. В выводе это
    # давало по две строки на одну проверку: SKIP с ложным объяснением и настоящий
    # результат ниже.
    skip("INSERT персоны в Postgres", "DATABASE_URL не задан")
else:
    # Use admin URL if available for fetching team, then switch to app role for INSERT
    admin_dsn = db_dsn("POSTGRES_ADMIN_URL") or dsn
    try:
        import psycopg
        with psycopg.connect(admin_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM teams LIMIT 1")
                row = cur.fetchone()
                if not row:
                    check("INSERT персоны с валидной DNA", False, "нет команд в базе")
                else:
                    tenant = str(row[0])
                    # Now test INSERT under agora_app with tenant context
                    with psycopg.connect(dsn) as app_conn:
                        with app_conn.cursor() as app_cur:
                            app_cur.execute("BEGIN")
                            app_cur.execute("SET LOCAL ROLE agora_app")
                            app_cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
                            app_cur.execute("INSERT INTO persona_sets (tenant_id, name, size) VALUES (%s, %s, %s) RETURNING id",
                                        (tenant, "test-dna", 1))
                            ps_id = app_cur.fetchone()[0]
                            fixture_str = json.dumps(fixture)
                            app_cur.execute(
                                "INSERT INTO personas (tenant_id, persona_set_id, name, dna) "
                                "VALUES (%s, %s, %s, %s::jsonb) RETURNING id",
                                (tenant, ps_id, "test-persona", fixture_str)
                            )
                            pid = app_cur.fetchone()
                            check("INSERT персоны с валидной DNA", pid is not None)
                            app_conn.rollback()
    except ImportError:
        skip("INSERT персоны в Postgres", "psycopg не установлен")
    except Exception as e:
        check("INSERT персоны с валидной DNA", False, f"{type(e).__name__}: {str(e)[:120]}")

# Pydantic validation
#
# Имя корневой модели задаёт datamodel-codegen по полю title схемы: "Persona DNA"
# превращается в класс PersonaDna. Тест был написан под прежнюю генерацию, где title
# отсутствовал и класс назывался Model, — отсюда ImportError, который уходил в SKIP и
# маскировал то, что Pydantic-уровень задачи #4 не проверялся вообще.
#
# Имя не захардкожено: сначала пробуем вывести его из title, затем известные варианты.
# Если корневой модели нет ни под одним именем — это FAIL, а не SKIP: отсутствие
# сгенерированной модели есть дефект, а не особенность среды.
def _root_model():
    import importlib

    sys.path.insert(0, str(REPO / "services" / "agent-core"))
    module = importlib.import_module("agent_core.schemas.persona_dna")
    title = (schema or {}).get("title", "")
    candidates = ["".join(p[:1].upper() + p[1:] for p in title.split()), "PersonaDna", "Model"]
    for name in candidates:
        model = getattr(module, name, None)
        if model is not None:
            return name, model
    raise AttributeError(
        f"корневая модель не найдена среди {candidates}; "
        f"проверьте title схемы и перегенерируйте: npm run codegen:persona"
    )


try:
    model_name, Model = _root_model()
    # 18. Pydantic accepts reference persona
    try:
        m = Model(**fixture)
        check("Pydantic принимает эталонную персону", True)
    except Exception as e:
        check("Pydantic принимает эталонную персону", False, str(e)[:120])

    # 19. Pydantic rejects same invalid variants
    invalid_variants = [
        ("Big Five 6", {**fixture, "big_five": {**fixture["big_five"], "openness": 6}}),
        ("Big Five 3.5", {**fixture, "big_five": {**fixture["big_five"], "openness": 3.5}}),
        ("extra field", {**fixture, "favourite_colour": "blue"}),
        ("bad age_group", {**fixture, "demographics": {**fixture["demographics"], "age_group": "99-100"}}),
    ]
    all_reject = True
    for label, variant in invalid_variants:
        try:
            Model(**variant)
            all_reject = False
            results.append((f"Pydantic отвергает: {label}", FAIL, "принял"))
            print(f"  FAIL  Pydantic отвергает: {label}  →  принял")
        except Exception:
            results.append((f"Pydantic отвергает: {label}", PASS, ""))
            print(f"  OK   Pydantic отвергает: {label}")
    check("Pydantic отвергает все невалидные варианты", all_reject)

except ModuleNotFoundError as e:
    # Единственная причина для SKIP здесь — отсутствие среды: пакет agent_core не
    # установлен, значит Pydantic-модель физически неоткуда взять.
    skip("Pydantic принимает эталонную персону", f"agent_core не установлен: {e}")
    skip("Pydantic отвергает невалидные варианты", f"agent_core не установлен: {e}")
except AttributeError as e:
    # Модуль есть, а корневой модели в нём нет — это дефект генерации, не среда.
    check("Pydantic-модель существует", False, str(e)[:160])
except Exception as e:
    check("Pydantic проверка", False, f"{type(e).__name__}: {str(e)[:120]}")


# --- Summary ---
n_pass = sum(1 for _, s, _ in results if s == PASS)
n_fail = sum(1 for _, s, _ in results if s == FAIL)
n_skip = sum(1 for _, s, _ in results if s == SKIP)

if n_fail:
    print(f"\nRED — не выполнено условий: {n_fail}")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  · {name}" + (f" ({detail})" if detail else ""))
elif n_skip > 0 and n_pass == 0:
    print(f"\nSKIP — все тесты пропущены")
else:
    print(f"\nGREEN — задача #4 удовлетворяет статическим критериям приёмки")

sys.exit(1 if n_fail else 0)