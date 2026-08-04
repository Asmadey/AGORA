#!/usr/bin/env python3
"""
CDD-тест задачи #10 — Конструктор анкеты (Survey Constructor).

Двухуровневый: статический работает где угодно, поведенческий требует
живой базы (Postgres с RLS).

CDD (из tasks.json):
  базовая анкета из 5 критериев 1–10 валидна по схеме;
  кастомный вопрос неподдерживаемого типа отвергается.

Acceptance:
  P0 — 5 критериев 1–10 (overall_impression, plot, acting, music, cinematography).
  P1 — конструктор: шкала / эмоции / удержание / рекомендация / открытый.
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

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


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

SCHEMA_PATH = REPO / "packages" / "shared" / "schemas" / "survey.schema.json"
TYPES_PATH = REPO / "packages" / "shared" / "types" / "survey.ts"
VALIDATOR_PATH = REPO / "apps" / "web" / "lib" / "server" / "survey-validator.ts"
API_ROUTE = REPO / "apps" / "web" / "app" / "api" / "surveys" / "route.ts"

schema_text = SCHEMA_PATH.read_text("utf-8") if SCHEMA_PATH.exists() else ""
types_text = TYPES_PATH.read_text("utf-8") if TYPES_PATH.exists() else ""
validator_text = VALIDATOR_PATH.read_text("utf-8") if VALIDATOR_PATH.exists() else ""
api_text = API_ROUTE.read_text("utf-8") if API_ROUTE.exists() else ""

# 1. JSON Schema exists
check(
    "JSON Schema существует (survey.schema.json)",
    SCHEMA_PATH.exists(),
    f"path={SCHEMA_PATH}",
)

# 2. Schema is valid JSON
schema = None
try:
    schema = json.loads(schema_text)
    check("схема — валидный JSON", True)
except Exception as e:
    check("схема — валидный JSON", False, str(e)[:100])

# 3. Schema defines 5 base criteria as enum
defs = {}
if schema:
    defs = schema.get("$defs", {})
    base_key_def = defs.get("BaseCriterionKey", {})
    base_enum = base_key_def.get("enum", [])
    check(
        "схема определяет 5 базовых критериев в enum",
        len(base_enum) == 5 and set(base_enum) == {
            "overall_impression", "plot", "acting", "music", "cinematography"
        },
        f"enum={base_enum}",
    )
else:
    check("схема определяет 5 базовых критериев в enum", False, "схема не загружена")

# 4. Schema defines 5 question types as enum
if schema:
    qt_def = defs.get("QuestionType", {})
    qt_enum = qt_def.get("enum", [])
    check(
        "схема определяет 5 типов вопросов в enum",
        len(qt_enum) == 5 and set(qt_enum) == {
            "scale", "emotions", "retention", "recommendation", "open"
        },
        f"enum={qt_enum}",
    )
else:
    check("схема определяет 5 типов вопросов в enum", False, "схема не загружена")

# 5. Schema requires base criteria with scale 1-10
if schema:
    all_of = schema.get("allOf", [])
    base_criterion_blocks = 0
    for block in all_of:
        props = block.get("properties", {}).get("questions", {}).get("contains", {}).get("properties", {})
        if "baseKey" in props and "scaleMin" in props and "scaleMax" in props:
            base_criterion_blocks += 1
    check(
        "схема требует 5 базовых критериев со шкалой 1–10 (contains blocks)",
        base_criterion_blocks == 5,
        f"найдено {base_criterion_blocks} contains-блоков",
    )
else:
    check("схема требует 5 базовых критериев со шкалой 1–10", False, "схема не загружена")

# 6. TS types generated from schema
check(
    "TS-типы сгенерированы (survey.ts)",
    TYPES_PATH.exists() and "export interface Survey" in types_text and "export interface Question" in types_text,
)

# 7. Validator module exists and exports validateSurvey
check(
    "модуль валидации существует (survey-validator.ts)",
    VALIDATOR_PATH.exists() and "export function validateSurvey" in validator_text,
)

# 8. Validator checks for unsupported question type
check(
    "валидатор отвергает неподдерживаемый тип вопроса",
    "ALLOWED_QUESTION_TYPES" in validator_text,
)

# 9. Validator checks base criteria presence (all 5)
check(
    "валидатор проверяет наличие всех 5 базовых критериев",
    "BASE_CRITERIA" in validator_text and "overall_impression" in validator_text,
)

# 10. Validator checks scale 1-10 for base criteria
check(
    "валидатор проверяет шкалу 1–10 для базовых критериев",
    "REQUIRED_BASE_SCALE" in validator_text,
)

# 11. API route exists with GET and PUT
check(
    "GET /api/surveys существует",
    "export async function GET" in api_text,
)
check(
    "PUT /api/surveys существует",
    "export async function PUT" in api_text,
)

# 12. API route validates against schema before saving
check(
    "API валидирует анкету перед записью (validateSurvey)",
    "validateSurvey" in api_text,
)

# 13. API route requires session (tenant_id from session)
check(
    "API требует сессию (requireSession)",
    "requireSession" in api_text,
)

# 14. API route uses withTenant for DB access
check(
    "API использует withTenant для доступа к базе",
    "withTenant" in api_text,
)

# 15. SurveyBuilder component exists with BASE_QUESTIONS
survey_builder_path = REPO / "apps" / "web" / "components" / "agora" / "SurveyBuilder.tsx"
sb_text = survey_builder_path.read_text("utf-8") if survey_builder_path.exists() else ""
check(
    "SurveyBuilder компонент существует с BASE_QUESTIONS",
    survey_builder_path.exists() and "BASE_QUESTIONS" in sb_text,
)

# 16. BASE_QUESTIONS has all 5 criteria with correct keys
base_keys_in_component = re.findall(r'baseKey:\s*"(\w+)"', sb_text)
check(
    "SurveyBuilder BASE_QUESTIONS содержит все 5 ключей",
    len(base_keys_in_component) >= 5 and set(base_keys_in_component) >= {
        "overall_impression", "plot", "acting", "music", "cinematography"
    },
    f"keys={base_keys_in_component}",
)

# 17. SurveyBuilder defines 5 question types
check(
    "SurveyBuilder определяет 5 типов вопросов",
    all(qt in sb_text for qt in ["scale", "emotions", "retention", "recommendation", "open"]),
)

# 18. DB table 'surveys' has questions jsonb column
schema_sql = (REPO / "infra" / "postgres" / "init" / "02_schema.sql").read_text("utf-8")
check(
    "таблица surveys существует с jsonb questions",
    "CREATE TABLE IF NOT EXISTS surveys" in schema_sql and "questions  jsonb" in schema_sql,
)


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ — unit-тесты валидатора (без внешних зависимостей)
# ═══════════════════════════════════════════════════════════════════════════

print("\n== Поведенческий уровень (unit-тесты схемы) ==")

BASE_QUESTIONS_VALID = [
    {"id": "base-1", "baseKey": "overall_impression", "label": "Общее впечатление", "type": "scale", "scaleMin": 1, "scaleMax": 10},
    {"id": "base-2", "baseKey": "plot", "label": "Сюжет", "type": "scale", "scaleMin": 1, "scaleMax": 10},
    {"id": "base-3", "baseKey": "acting", "label": "Актёрская игра", "type": "scale", "scaleMin": 1, "scaleMax": 10},
    {"id": "base-4", "baseKey": "music", "label": "Музыка", "type": "scale", "scaleMin": 1, "scaleMax": 10},
    {"id": "base-5", "baseKey": "cinematography", "label": "Операторская работа", "type": "scale", "scaleMin": 1, "scaleMax": 10},
]

REQUIRED_BASE_KEYS = {"overall_impression", "plot", "acting", "music", "cinematography"}
ALLOWED_TYPES = {"scale", "emotions", "retention", "recommendation", "open"}


def validate_survey_python(doc):
    """Python-реплика TS-валидатора для поведенческих тестов."""
    errors = []
    if not isinstance(doc, dict):
        return ["Анкета должна быть объектом"]

    name = doc.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name: обязательная непустая строка")

    questions = doc.get("questions")
    if not isinstance(questions, list):
        errors.append("questions: должен быть массивом")
        return errors

    if len(questions) < 5:
        errors.append(f"questions: минимум 5 элементов, получено {len(questions)}")

    seen_ids = set()
    base_keys_found = set()

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            errors.append(f"questions[{i}]: должен быть объектом")
            continue

        qid = q.get("id")
        if not isinstance(qid, str) or not qid.strip():
            errors.append(f"questions[{i}].id: обязательная непустая строка")
        elif qid in seen_ids:
            errors.append(f"questions[{i}].id: дубликат id")
        else:
            seen_ids.add(qid)

        label = q.get("label")
        if not isinstance(label, str) or not label.strip():
            errors.append(f"questions[{i}].label: обязательная непустая строка")

        qtype = q.get("type")
        if qtype not in ALLOWED_TYPES:
            errors.append(f"questions[{i}].type: должен быть одним из {ALLOWED_TYPES}")

        scale_min = q.get("scaleMin")
        scale_max = q.get("scaleMax")
        if not isinstance(scale_min, int):
            errors.append(f"questions[{i}].scaleMin: целое число")
        if not isinstance(scale_max, int):
            errors.append(f"questions[{i}].scaleMax: целое число")

        if qtype == "scale" and isinstance(scale_min, int) and isinstance(scale_max, int):
            if scale_min >= scale_max:
                errors.append(f"questions[{i}]: scaleMax должен быть больше scaleMin")

        base_key = q.get("baseKey")
        if base_key is not None:
            if base_key not in REQUIRED_BASE_KEYS:
                errors.append(f"questions[{i}].baseKey: должен быть одним из {REQUIRED_BASE_KEYS}")
            else:
                if base_key in base_keys_found:
                    errors.append(f"questions[{i}].baseKey: дубликат")
                else:
                    base_keys_found.add(base_key)
                if qtype != "scale":
                    errors.append(f"questions[{i}]: базовый критерий должен быть type=scale")
                if scale_min != 1 or scale_max != 10:
                    errors.append(f"questions[{i}]: базовый критерий должен иметь шкалу 1–10")

    for required in REQUIRED_BASE_KEYS:
        if required not in base_keys_found:
            errors.append(f"questions: отсутствует базовый критерий «{required}»")

    return errors


# B1: Базовая анкета из 5 критериев 1–10 валидна
errors = validate_survey_python({"name": "Базовая", "questions": BASE_QUESTIONS_VALID})
check(
    "базовая анкета из 5 критериев 1–10 валидна",
    len(errors) == 0,
    f"errors={errors[:3]}" if errors else "",
)

# B2: Кастомный вопрос неподдерживаемого типа отвергается
invalid_questions = BASE_QUESTIONS_VALID + [
    {"id": "custom-1", "label": "Цвет", "type": "color_picker", "scaleMin": 0, "scaleMax": 10},
]
errors = validate_survey_python({"name": "С кастомом", "questions": invalid_questions})
check(
    "кастомный вопрос неподдерживаемого типа отвергается",
    any("color_picker" in e or "type" in e for e in errors),
    f"errors={errors[:3]}",
)

# B3: Анкета без одного из базовых критериев невалидна
missing_one = [q for q in BASE_QUESTIONS_VALID if q["baseKey"] != "music"]
errors = validate_survey_python({"name": "Без music", "questions": missing_one})
check(
    "анкета без критерия «music» невалидна",
    any("music" in e for e in errors),
    f"errors={errors[:3]}",
)

# B4: Базовый критерий с неправильной шкалой (2-10) невалиден
wrong_scale = [
    {**q, "scaleMin": 2 if q["baseKey"] == "overall_impression" else 1}
    for q in BASE_QUESTIONS_VALID
]
errors = validate_survey_python({"name": "Шкала 2-10", "questions": wrong_scale})
check(
    "базовый критерий со шкалой 2–10 невалиден",
    any("1–10" in e or "1-10" in e for e in errors),
    f"errors={errors[:3]}",
)

# B5: Базовый критерий не типа scale невалиден
wrong_type = [
    {**q, "type": "emotions" if q["baseKey"] == "plot" else "scale"}
    for q in BASE_QUESTIONS_VALID
]
errors = validate_survey_python({"name": "Не scale", "questions": wrong_type})
check(
    "базовый критерий типа emotions невалиден",
    any("scale" in e for e in errors),
    f"errors={errors[:3]}",
)

# B6: Кастомный вопрос поддерживаемого типа (emotions) валиден
valid_custom = BASE_QUESTIONS_VALID + [
    {"id": "custom-1", "label": "Какие эмоции вызвало видео?", "type": "emotions", "scaleMin": 0, "scaleMax": 0},
]
errors = validate_survey_python({"name": "С emotions", "questions": valid_custom})
check(
    "кастомный вопрос типа emotions валиден",
    len(errors) == 0,
    f"errors={errors[:3]}" if errors else "",
)

# B7: Дубликат id невалиден
dup_id = BASE_QUESTIONS_VALID + [
    {"id": "base-1", "label": "Дубликат", "type": "open", "scaleMin": 0, "scaleMax": 0},
]
errors = validate_survey_python({"name": "Дубликат id", "questions": dup_id})
check(
    "дубликат id отвергается",
    any("дубликат" in e.lower() for e in errors),
    f"errors={errors[:3]}",
)

# B8: scale вопрос где scaleMin >= scaleMax невалиден
bad_scale = BASE_QUESTIONS_VALID + [
    {"id": "custom-1", "label": "Плохая шкала", "type": "scale", "scaleMin": 5, "scaleMax": 5},
]
errors = validate_survey_python({"name": "Плохая шкала", "questions": bad_scale})
check(
    "scale вопрос с scaleMin >= scaleMax невалиден",
    any("scaleMax" in e for e in errors),
    f"errors={errors[:3]}",
)


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ — API (требует живую базу)
# ═══════════════════════════════════════════════════════════════════════════

print("\n== Поведенческий уровень (API — требует базу) ==")

has_server = os.environ.get("AGORA_TEST_SERVER") is not None or os.environ.get("BASE_URL") is not None

if not has_server:
    skip("API GET /api/surveys возвращает список", "требует AGORA_TEST_SERVER/BASE_URL")
    skip("API PUT /api/surveys создаёт анкету", "требует AGORA_TEST_SERVER/BASE_URL")
    skip("API PUT с невалидной анкетой возвращает 400", "требует AGORA_TEST_SERVER/BASE_URL")
    skip("API PUT с неподдерживаемым типом возвращает 400", "требует AGORA_TEST_SERVER/BASE_URL")
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _harness import login

    server_url = os.environ.get("AGORA_TEST_SERVER") or os.environ["BASE_URL"]

    # /api/surveys закрыт middleware: без сессии он отвечает 401 на любой метод.
    # Раньше тест ходил анонимно и получал три FAIL со status=401 — выглядело
    # это как отказ API, хотя проверялась несуществующая ситуация: продукт таких
    # запросов не делает, у него всегда есть сессия.
    client, why = login(server_url)

    if client is None:
        skip("API PUT создаёт валидную анкету", why)
        skip("API PUT с неподдерживаемым типом возвращает 400", why)
        skip("API GET возвращает список анкет", why)
    else:
        try:
            # B-API-1: PUT создаёт валидную анкету
            payload = json.dumps({
                "name": "Тестовая анкета",
                "questions": BASE_QUESTIONS_VALID,
            }).encode()
            code, body_raw = client.call("/api/surveys", "PUT", payload)
            body = json.loads(body_raw) if code == 200 else {}
            check(
                "API PUT создаёт валидную анкету",
                code == 200 and body.get("ok") is True,
                f"status={code} response={body_raw[:120]}",
            )

            # B-API-2: PUT с неподдерживаемым типом возвращает 400
            payload = json.dumps({
                "name": "Невалидная",
                "questions": BASE_QUESTIONS_VALID + [
                    {"id": "x", "label": "Цвет", "type": "color", "scaleMin": 0, "scaleMax": 1},
                ],
            }).encode()
            code, body_raw = client.call("/api/surveys", "PUT", payload)
            check(
                "API PUT с неподдерживаемым типом возвращает 400",
                code == 400,
                f"status={code}; 200 значит, что валидатор пропустил неизвестный тип",
            )

            # B-API-3: GET возвращает список
            code, body_raw = client.call("/api/surveys")
            body = json.loads(body_raw) if code == 200 else {}
            check(
                "API GET возвращает список анкет",
                code == 200 and "surveys" in body,
                f"status={code} body={body_raw[:120]}",
            )

        except Exception as e:
            check("поведенческий тест API surveys", False, f"{type(e).__name__}: {str(e)[:120]}")


# ═══════════════════════════════════════════════════════════════════════════
# ИТОГ
# ═══════════════════════════════════════════════════════════════════════════

# Вердикт общий для всех тестов: GREEN только когда проверено всё, что можно
# было проверить здесь. Прежде GREEN печатался при любом числе SKIP, и по
# выводу нельзя было отличить «проверено» от «пропущено» — см. _harness.verdict.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#10"))
