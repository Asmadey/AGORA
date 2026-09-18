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

# 4. Schema defines the closed set of question types as enum
#
# Изначально типов было пять. Шестой, `watched_share`, добавлен при закрытии
# #21: экран отчёта показывал «Досмотрено, %», а взять это число было неоткуда —
# `retention_intent` категориален, и процент из категории не выводится. В
# прототипе интерфейса там стояло выдуманное значение.
#
# Проверка осталась на равенство множеству, а не превратилась в «содержит
# нужные». Смысл её в том, что список ЗАКРЫТ: воркер разбирает ответ только
# известных форм, и седьмой тип обязан сломать этот тест — чтобы вместе с ним
# поправили prompts/respondent.user.md, миграцию засева и разбор в agent_core.
#
# ─── 17.09.2026: шесть типов сведены к пяти ─────────────────────────────────
# Решение владельца под анкету заказчика. «Эмоции», «удержание», «рекомендация»
# и «доля просмотра» оказались не типами, а ПРЕСЕТАМИ: эмоции — выбор
# нескольких из готового словаря, удержание — выбор одного из трёх,
# рекомендация и доля — шкалы. Каждый нёс свою ветку в конструкторе, промпте,
# правилах QA, агрегате, графиках и выгрузке.
#
# Требование «список закрыт» НЕ ослаблено: проверка осталась на равенство, и
# шестой тип по-прежнему обязан сломать этот тест. Изменился состав списка, а
# не его закрытость.
QUESTION_TYPES = {"scale", "single_choice", "multi_choice", "matrix_single", "open"}

if schema:
    qt_def = defs.get("QuestionType", {})
    qt_enum = qt_def.get("enum", [])
    check(
        "схема определяет закрытый набор типов вопросов в enum",
        set(qt_enum) == QUESTION_TYPES,
        f"enum={qt_enum}, ожидалось {sorted(QUESTION_TYPES)}",
    )
else:
    check("схема определяет закрытый набор типов вопросов в enum", False, "схема не загружена")

# 5. Базовые критерии объявлены, но не прибиты к шкале 1–10
#
# ─── Чем это было и почему изменилось ──────────────────────────────────────
# Здесь стояло «схема требует 5 базовых критериев со шкалой 1–10» — пять
# блоков `contains`, каждый из которых требовал ПРИСУТСТВИЯ вопроса с своим
# baseKey и границами ровно 1 и 10.
#
# Требование отменено дважды, и оба раза молча:
#
# 1. Базовые критерии перестали быть обязательными — владелец разрешил снимать
#    любое их число. Рукописный валидатор `survey-validator.ts` это учёл, схема
#    нет, и расхождение полтора месяца жило незамеченным: валидатор мягче
#    схемы, поэтому ни один прогон на нём не падал. Оно было записано в его
#    же тесте («survey.schema.json всё ещё требует пять вопросов, а валидатор —
#    один») и осталось незакрытым.
# 2. 17.09.2026 анкета заказчика пришла на шкале 0–10. Старые блоки отвергали
#    её целиком.
#
# Что осталось проверяться: перечень ключей баз объявлен и закрыт. Именно он —
# контракт с корпусом: по этим пяти ключам посчитаны средние 165 респондентов,
# и ключ здесь часть данных, а не подпись.
if schema:
    base_enum = set(defs.get("BaseCriterionKey", {}).get("enum") or [])
    check(
        "схема объявляет закрытый перечень ключей базовых критериев",
        base_enum == {"overall_impression", "plot", "acting", "music", "cinematography"},
        f"перечень={sorted(base_enum)}",
    )
    pinned = [
        block for block in (schema.get("allOf") or [])
        if (block.get("properties", {}).get("questions", {})
            .get("contains", {}).get("properties", {})
            .get("scaleMin", {}).get("const") == 1)
    ]
    check(
        "базовые критерии не прибиты к шкале 1–10",
        not pinned,
        f"осталось {len(pinned)} блоков, требующих шкалу 1–10 — анкета 0–10 будет отвергнута",
    )
else:
    check("схема объявляет закрытый перечень ключей базовых критериев", False, "схема не загружена")
    check("базовые критерии не прибиты к шкале 1–10", False, "схема не загружена")

# 6. TS types generated from schema
#
# `Question` экспортируется как `type`, а не `interface`: у вопроса появились
# условные требования (шкала только у шкалы, варианты только у закрытого), и
# json2ts выражает их пересечением, а не интерфейсом. Проверка смотрит на
# наличие экспорта, а не на ключевое слово — иначе она держалась бы за форму
# генератора, а не за утверждение «типы собраны из схемы».
check(
    "TS-типы сгенерированы (survey.ts)",
    TYPES_PATH.exists()
    and "export interface Survey" in types_text
    and ("export interface Question" in types_text or "export type Question" in types_text),
)

# 6-бис. Сгенерированные типы не отстали от схемы
#
# Повод конкретный: `packages/shared/types/survey.ts` полтора месяца не знал
# типа `watched_share`, потому что анкеты не было в `npm run codegen`, — а его
# докстрока при этом утверждала «только этих пяти форм». Файл, который никто не
# генерирует, это рукописный файл с надписью «не править руками».
if schema:
    generated = set(re.findall(r'"(\w+)"', (
        re.search(r"export type QuestionType = ([^;]+);", types_text) or re.Match
    ).group(1))) if "export type QuestionType" in types_text else set()
    check(
        "перечень типов в сгенерированном survey.ts совпадает со схемой",
        generated == QUESTION_TYPES,
        f"в типах={sorted(generated)}, в схеме={sorted(QUESTION_TYPES)}",
    )
    check(
        "анкета входит в npm run codegen",
        "codegen:survey" in (REPO / "package.json").read_text("utf-8"),
        "без этого сгенерированный файл отстанет от схемы молча",
    )
else:
    check("перечень типов в сгенерированном survey.ts совпадает со схемой", False, "схема не загружена")
    check("анкета входит в npm run codegen", False, "схема не загружена")

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

# 10. Перечень типов у валидатора и у схемы совпадает
#
# ─── Чем это было ──────────────────────────────────────────────────────────
# Здесь стояло «валидатор проверяет шкалу 1–10 для базовых критериев». Анкета
# заказчика пришла на шкале 0–10 (17.09.2026), требование снято, и проверять
# нечего.
#
# Место занято тем, чего в этом файле не хватало и что уже стоило полутора
# месяцев незамеченного расхождения: перечень типов живёт в ТРЁХ копиях —
# в JSON Schema, в рукописном валидаторе и в реплике ниже. Две копии расходятся
# молча, и это уже случилось: схема требовала пять базовых критериев, валидатор
# считал их необязательными, и ни один прогон на этом не падал, потому что
# валидатор мягче.
if schema:
    ts_types = set(
        re.findall(r'"(\w+)"', (
            re.search(
                r"ALLOWED_QUESTION_TYPES: QuestionType\[\] = \[(.*?)\]",
                validator_text, re.S,
            ) or re.Match
        ).group(1))
    ) if re.search(r"ALLOWED_QUESTION_TYPES: QuestionType\[\] = \[", validator_text) else set()
    check(
        "перечень типов у валидатора совпадает со схемой",
        ts_types == QUESTION_TYPES,
        f"валидатор={sorted(ts_types)}, схема={sorted(QUESTION_TYPES)}",
    )
else:
    check("перечень типов у валидатора совпадает со схемой", False, "схема не загружена")

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

# 15. Состав анкеты объявлен и доезжает до конструктора
#
# BASE_QUESTIONS переехали из компонента в lib/survey-composition.ts: веб-тесты
# собирают только `lib/**`, и логика, оставленная в .tsx, не покрыта ничем по
# построению. Так и разошлась проверка заземления — константы ушли на 0–10,
# а условие в компоненте осталось на 1–10.
#
# Гейт идёт за источником, а не за файлом: он читает то место, где константа
# объявлена СЕЙЧАС, и отдельно проверяет, что конструктор её импортирует.
# Иначе проверка молча стала бы проверять пустую строку.
composition_path = REPO / "apps" / "web" / "lib" / "survey-composition.ts"
comp_text = composition_path.read_text("utf-8") if composition_path.exists() else ""
survey_builder_path = REPO / "apps" / "web" / "components" / "agora" / "SurveyBuilder.tsx"
sb_text = survey_builder_path.read_text("utf-8") if survey_builder_path.exists() else ""
check(
    "BASE_QUESTIONS объявлены и конструктор их импортирует",
    "BASE_QUESTIONS" in comp_text and "BASE_QUESTIONS" in sb_text,
    f"объявление={'есть' if 'BASE_QUESTIONS' in comp_text else 'НЕТ'}, "
    f"импорт={'есть' if 'BASE_QUESTIONS' in sb_text else 'НЕТ'}",
)

# 16. BASE_QUESTIONS has all 5 criteria with correct keys
base_keys_in_component = re.findall(r'baseKey:\s*"(\w+)"', comp_text)
check(
    "BASE_QUESTIONS содержат все 5 ключей",
    len(base_keys_in_component) >= 5 and set(base_keys_in_component) >= {
        "overall_impression", "plot", "acting", "music", "cinematography"
    },
    f"keys={base_keys_in_component}",
)

# 17. SurveyBuilder offers every type the schema allows
#
# Сверка с тем же множеством, что и в проверке 4, а не со своим списком. Два
# списка типов в одном тесте разошлись бы при первом добавлении: конструктор
# предлагал бы не то, что принимает валидатор, и разницу увидел бы только
# пользователь — как вопрос, который не сохраняется.
check(
    "SurveyBuilder предлагает все типы из схемы",
    all(qt in sb_text for qt in QUESTION_TYPES),
    f"нет в конструкторе: {sorted(qt for qt in QUESTION_TYPES if qt not in sb_text)}",
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
    {"id": "base-1", "baseKey": "overall_impression", "label": "Общее впечатление", "type": "scale", "scaleMin": 0, "scaleMax": 10},
    {"id": "base-2", "baseKey": "plot", "label": "Сюжет", "type": "scale", "scaleMin": 0, "scaleMax": 10},
    {"id": "base-3", "baseKey": "acting", "label": "Актёрская игра", "type": "scale", "scaleMin": 0, "scaleMax": 10},
    {"id": "base-4", "baseKey": "music", "label": "Музыка", "type": "scale", "scaleMin": 0, "scaleMax": 10},
    {"id": "base-5", "baseKey": "cinematography", "label": "Операторская работа", "type": "scale", "scaleMin": 0, "scaleMax": 10},
]

REQUIRED_BASE_KEYS = {"overall_impression", "plot", "acting", "music", "cinematography"}

#: Берётся из QUESTION_TYPES выше, а не переписывается вторым литералом.
#:
#: Отдельный список здесь уже разошёлся: `watched_share` завели в JSON Schema,
#: в TS-типы, в конструктор и в TS-валидатор — а сюда не добавили. Реплика
#: валидатора отвергала бы анкету, которую настоящий валидатор принимает, и
#: заметить это было нечем: обе стороны зелёные, потому что каждая сверяется
#: сама с собой. Контракт в тесте обязан жить в одном месте.
ALLOWED_TYPES = set(QUESTION_TYPES)


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

    # Минимум — один вопрос, а не пять. Пятёрка держалась на том, что пять
    # базовых критериев обязательны; с 26.08.2026 они необязательны (решение
    # владельца, PRD §18). Ноль остаётся отказом: анкета без вопросов — это
    # оплаченный прогон, в котором персону не о чем спрашивать.
    if len(questions) < 1:
        errors.append("questions: нужен хотя бы один вопрос")

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

        # Шкала обязательна только у шкального вопроса: у выбора из списка её
        # нет и быть не может. Реплика повторяет `survey-validator.ts`.
        scale_min = q.get("scaleMin")
        scale_max = q.get("scaleMax")
        if qtype == "scale":
            if not isinstance(scale_min, int):
                errors.append(f"questions[{i}].scaleMin: целое число")
            if not isinstance(scale_max, int):
                errors.append(f"questions[{i}].scaleMax: целое число")
            if isinstance(scale_min, int) and isinstance(scale_max, int):
                if scale_min >= scale_max:
                    errors.append(f"questions[{i}]: scaleMax должен быть больше scaleMin")

        if qtype in {"single_choice", "multi_choice", "matrix_single"}:
            options = q.get("options")
            if not isinstance(options, list) or len(options) < 2:
                errors.append(
                    f"questions[{i}].options: закрытому вопросу нужно не меньше двух вариантов"
                )
        if qtype == "matrix_single":
            rows = q.get("rows")
            if not isinstance(rows, list) or not rows:
                errors.append(f"questions[{i}].rows: матрице нужна хотя бы одна строка")

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
                # Границы базового критерия больше не прибиты к 1–10.
                #
                # Здесь стояло `scale_min != 1 or scale_max != 10` — копия
                # прежнего правила, которое `survey-validator.ts` снял
                # 17.09.2026 ради анкеты заказчика на шкале 0–10. Реплика в
                # гейте осталась строже оригинала, и гейт был зелёным только
                # потому, что ни одна фикстура 0–10 в него не подавалась:
                # первая же настоящая анкета была бы отвергнута проверкой,
                # которая существует, чтобы её пропустить.
                #
                # Ключ критерия остаётся контрактом с данными — по этим пяти
                # ключам посчитаны средние 165 респондентов корпуса. Меняется
                # шкала, не ключ.
                # Ровно 0–10, как в `survey-validator.ts`.
                #
                # Правило переписывалось в этом файле дважды за день. Стояло
                # «ровно 1–10» — отвергало анкету заказчика. Стало «любая
                # шкала» — пропускало анкету на 1–5, для которой пороги
                # расчёта (доля 8–10, промоутеры 9–10) дают ноль и минус
                # единицу, то есть правдоподобные неверные числа. Решение
                # владельца 17.09.2026: базовому критерию разрешена одна
                # шкала. Своя шкала остаётся у вопроса БЕЗ baseKey.
                if (scale_min, scale_max) != (BASE_SCALE_MIN, BASE_SCALE_MAX):
                    errors.append(
                        f"questions[{i}]: базовый критерий должен быть на шкале "
                        f"{BASE_SCALE_MIN}–{BASE_SCALE_MAX}, "
                        f"получено {scale_min}–{scale_max}"
                    )

    # Требования «все пять базовых на месте» больше нет. Осталось то, что
    # защищает данные: базовый критерий, ЕСЛИ он есть, обязан быть шкалой и не
    # может повторяться — иначе ключ overall_impression встретился бы дважды с
    # разными границами и оба попали бы в одно среднее.

    return errors


# Шкала базовых критериев берётся ИЗ ВАЛИДАТОРА, а не объявляется здесь заново.
# Переписанная константа — ровно тот способ, которым реплика разошлась с
# оригиналом в прошлый раз.
_validator_src = (REPO / "apps" / "web" / "lib" / "server" / "survey-validator.ts").read_text(
    "utf-8"
)
BASE_SCALE_MIN = int(re.search(r"BASE_SCALE_MIN\s*=\s*(-?\d+)", _validator_src).group(1))
BASE_SCALE_MAX = int(re.search(r"BASE_SCALE_MAX\s*=\s*(-?\d+)", _validator_src).group(1))

# B1: Базовая анкета из 5 критериев 0–10 валидна
errors = validate_survey_python({"name": "Базовая", "questions": BASE_QUESTIONS_VALID})
check(
    "базовая анкета из 5 критериев 0–10 валидна",
    len(errors) == 0,
    f"errors={errors[:3]}" if errors else "",
)

# B1-бис: анкета заказчика — настоящая, с диска — проходит реплику валидатора
#
# Проверки на фикстурах 1–10 были зелёными, пока реплика требовала ровно
# 1–10: фикстуры сами написаны на 1–10. Расхождение реплики с
# `survey-validator.ts` стало видно только когда на вход подали документ,
# ради которого правило и снимали. Поэтому гейт теперь читает анкету с диска,
# а не описывает её у себя.
CUSTOMER_SURVEY_PATH = REPO / "data" / "survey" / "customer_2026.json"
if CUSTOMER_SURVEY_PATH.exists():
    # Файл — КАТАЛОГ обязательных вопросов, а не готовая анкета: имени у него
    # нет, его даёт исследование. Поэтому сюда подаётся то, что отправит
    # конструктор, — имя плюс вопросы с диска.
    customer = json.loads(CUSTOMER_SURVEY_PATH.read_text("utf-8"))
    errors = validate_survey_python(
        {"name": "Анкета заказчика", "questions": customer["questions"]}
    )
    check(
        "анкета заказчика (шкала 0–10) валидна по реплике валидатора",
        len(errors) == 0,
        f"errors={errors[:3]}" if errors else "",
    )
else:
    skip(
        "анкета заказчика (шкала 0–10) валидна по реплике валидатора",
        f"нет {CUSTOMER_SURVEY_PATH.name}",
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

# B3: Анкета без части базовых критериев ВАЛИДНА (решение владельца 26.08.2026)
#
# Здесь стояло обратное утверждение, и оно пережило снятие требования в
# продукте: тест повторяет валидатор своей реализацией, поэтому остался
# зелёным, утверждая противоположное тому, что делает код. Зелёная проверка,
# утверждающая обратное продукту, хуже отсутствующей.
missing_one = [q for q in BASE_QUESTIONS_VALID if q["baseKey"] != "music"]
errors = validate_survey_python({"name": "Без music", "questions": missing_one})
check(
    "анкета без критерия «music» валидна",
    not errors,
    f"errors={errors[:3]}",
)

# B3-бис: анкета из одних своих вопросов валидна
only_custom = [
    {"id": "c1", "label": "Насколько понятен конфликт героя", "type": "scale",
     "scaleMin": 1, "scaleMax": 10},
]
errors = validate_survey_python({"name": "Только свои", "questions": only_custom})
check(
    "анкета из одних пользовательских вопросов валидна",
    not errors,
    f"errors={errors[:3]}",
)

# B3-трижды: пустая анкета по-прежнему отвергается
errors = validate_survey_python({"name": "Пустая", "questions": []})
check(
    "анкета без вопросов отвергается",
    any("хотя бы один вопрос" in e for e in errors),
    f"errors={errors[:3]}",
)

# B4: вырожденная шкала отвергается отдельной проверкой
#
# Проверка живёт своей жизнью и после привязки базовых критериев к 0–10:
# `scaleMax > scaleMin` относится к ЛЮБОЙ шкале, включая пользовательские
# вопросы без `baseKey`, которым своя шкала разрешена. Здесь она подана на
# базовом критерии просто потому, что такой набор уже собран рядом.
broken_scale = [
    {**q, "scaleMin": 10 if q["baseKey"] == "overall_impression" else 1, "scaleMax": 10}
    for q in BASE_QUESTIONS_VALID
]
errors = validate_survey_python({"name": "Вырожденная шкала", "questions": broken_scale})
check(
    "базовый критерий с вырожденной шкалой невалиден",
    any("scaleMax" in e for e in errors),
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

# B6: Кастомный вопрос поддерживаемого типа валиден
#
# Был `emotions`. 17.09.2026 он перестал быть типом и стал ПРЕСЕТОМ — выбором
# нескольких из готового словаря, — поэтому проверка идёт по типу, в который он
# превратился. Утверждение то же: конструктор вправе добавить свой вопрос
# поддерживаемой формы, и валидатор его принимает.
valid_custom = BASE_QUESTIONS_VALID + [
    {
        "id": "custom-1",
        "label": "Какие эмоции вызвало видео?",
        "type": "multi_choice",
        "maxChoices": 3,
        "options": [
            {"id": "c-1", "label": "Радость"},
            {"id": "c-2", "label": "Грусть"},
        ],
    },
]
errors = validate_survey_python({"name": "С выбором нескольких", "questions": valid_custom})
check(
    "кастомный вопрос с выбором нескольких валиден",
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
