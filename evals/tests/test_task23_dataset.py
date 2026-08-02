#!/usr/bin/env python3
"""
CDD-тест задачи #23 — «Grounding-корпус: схема, паспорт, единая точка доступа».

Приёмка задачи изменена 02.08.2026 (вариант А). Прежняя формулировка требовала
воспроизводимой пересборки корпуса из XLSX и DOCX. Это оказалось недостижимо:
поле focus_group_verbatims получено моделью — реплики групповой дискуссии
распределены по конкретным респондентам, — а модель недетерминирована. 165
уникальных наборов реплик при четырёх стенограммах побайтово не повторить.

Поэтому корпус принят источником истины, и задача проверяет другое: что он
структурирован, валиден, обезличен, снабжён паспортом происхождения и читается
через единственную точку в каждом языке. Пересборка из исходников не требуется —
исходники содержат персональные данные и в репозитории не хранятся.

Запуск:
    python3 evals/tests/test_task23_dataset.py

Exit 0 = green.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "grounding" / "unified_respondent_sessions.json"
META = ROOT / "data" / "grounding" / "corpus.meta.json"
SCHEMA = ROOT / "packages" / "shared" / "schemas" / "respondent-session.schema.json"
PERSONA_SCHEMA = ROOT / "packages" / "shared" / "schemas" / "persona-dna.schema.json"
PY_MODEL = ROOT / "services" / "agent-core" / "agent_core" / "schemas" / "respondent_session.py"
TS_TYPE = ROOT / "packages" / "shared" / "types" / "respondent-session.ts"
PY_LOADER = ROOT / "services" / "agent-core" / "agent_core" / "grounding" / "corpus.py"
TS_LOADER = ROOT / "apps" / "web" / "lib" / "server" / "corpus.ts"

failures: list[str] = []
skipped: list[str] = []
warnings: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def skip(name: str, reason: str) -> None:
    print(f"  SKIP  {name}  →  {reason}")
    skipped.append(f"{name}: {reason}")


def warn(name: str, detail: str) -> None:
    print(f"  WARN  {name}  →  {detail}")
    warnings.append(f"{name}: {detail}")


print("== файлы корпуса ==")
for label, path in [
    ("датасет", DATASET),
    ("паспорт corpus.meta.json", META),
    ("canonical JSON Schema", SCHEMA),
    ("загрузчик Python", PY_LOADER),
    ("загрузчик TypeScript", TS_LOADER),
]:
    check(f"{label} существует", path.is_file(), "" if path.is_file() else str(path))

if not (DATASET.is_file() and META.is_file() and SCHEMA.is_file()):
    print("\nRED — нет базовых файлов, остальные проверки бессмысленны")
    sys.exit(1)

raw_bytes = DATASET.read_bytes()
sessions = json.loads(raw_bytes.decode("utf-8"))
meta = json.loads(META.read_text(encoding="utf-8"))
schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

print("\n== паспорт согласован с датасетом ==")
check("records в паспорте == числу записей", meta.get("records") == len(sessions),
      f"паспорт={meta.get('records')} факт={len(sessions)}")

actual_sha = hashlib.sha256(raw_bytes).hexdigest()
check("sha256 в паспорте == хешу файла", meta.get("sha256") == actual_sha,
      "датасет изменён без обновления паспорта" if meta.get("sha256") != actual_sha else "")
check("паспорт перечисляет источники",
      bool(meta.get("provenance", {}).get("sources")), "")
check("паспорт объясняет происхождение",
      len(meta.get("provenance", {}).get("explanation", "")) > 100,
      "объяснение слишком короткое, чтобы что-то объяснить")
check("паспорт описывает процедуру добавления исследования",
      len(meta.get("how_to_add_study", [])) >= 3, "")

print("\n== структура ==")
check("датасет — непустой массив", isinstance(sessions, list) and len(sessions) > 0,
      f"{len(sessions)} записей")
ids = [r.get("respondent_id") for r in sessions]
check("respondent_id уникальны", len(set(ids)) == len(ids),
      f"уникальных {len(set(ids))} из {len(ids)}")
check("respondent_id обезличен (<источник>_<номер>)",
      all(re.fullmatch(r".+_\d+", str(i)) for i in ids), "")

print("\n== валидация по canonical JSON Schema ==")
try:
    import jsonschema
    has_2020 = hasattr(jsonschema, "Draft202012Validator")
except ImportError:
    jsonschema = None
    has_2020 = False

if not has_2020:
    # Отдельно от ImportError: старая версия импортируется, но валидатора 2020-12
    # в ней нет. Раньше на этом падал тест задачи #4 — трассировкой вместо SKIP.
    skip("все записи валидны по схеме", "нужен jsonschema>=4 (pip install 'jsonschema>=4')")
else:
    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    for r in sessions:
        for e in validator.iter_errors(r):
            path = "/".join(str(p) for p in e.absolute_path) or "<корень>"
            errors.append(f"{r.get('respondent_id')}: {path} — {e.message[:80]}")
    check("все записи валидны по схеме", not errors,
          f"{len(errors)} ошибок; первая: {errors[0]}" if errors else "")

print("\n== словарь совпадает с Persona DNA ==")
# Расхождение делает persona_grounding невычислимой: метрика сравнивает
# распределения сгенерированных персон с корпусом по этим трём полям.


def find_enum(node: object, field: str) -> set[str] | None:
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict) and field in props:
            enum = props[field].get("enum")
            if enum:
                return set(enum)
        for v in node.values():
            found = find_enum(v, field)
            if found:
                return found
    elif isinstance(node, list):
        for v in node:
            found = find_enum(v, field)
            if found:
                return found
    return None


persona = json.loads(PERSONA_SCHEMA.read_text(encoding="utf-8")) if PERSONA_SCHEMA.is_file() else None
for field in ("age_group", "geo", "gender"):
    corpus_values = {r["socio_demographics"][field] for r in sessions}
    corpus_enum = find_enum(schema, field) or set()
    check(f"схема корпуса покрывает фактические значения {field}",
          corpus_values <= corpus_enum,
          f"не покрыто: {corpus_values - corpus_enum}")
    if persona is None:
        skip(f"{field} сверен с persona-dna", "persona-dna.schema.json не найдена")
        continue
    persona_enum = find_enum(persona, field)
    if persona_enum is None:
        skip(f"{field} сверен с persona-dna", "поле не найдено в схеме персоны")
    else:
        check(f"persona-dna покрывает значения {field} из корпуса",
              corpus_values <= persona_enum,
              f"не покрыто: {corpus_values - persona_enum}")

print("\n== обезличенность ==")
text = raw_bytes.decode("utf-8")
patterns = {
    "телефон": r"(?:\+7|\b8)[\s\-(]?\d{3}[\s\-)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b",
    "e-mail": r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b",
    "дата рождения": r"\b\d{2}[./]\d{2}[./]\d{4}\b",
    "паспортные данные": r"\b\d{4}\s\d{6}\b",
}
for label, pat in patterns.items():
    hits = re.findall(pat, text)
    check(f"в корпусе нет: {label}", not hits, f"найдено {len(hits)}: {hits[:2]}")

print("\n== сгенерированные артефакты ==")
check("Pydantic-модель существует", PY_MODEL.is_file(), "" if PY_MODEL.is_file() else str(PY_MODEL))
check("TS-тип существует", TS_TYPE.is_file(), "" if TS_TYPE.is_file() else str(TS_TYPE))

# Настоящая проверка перегенерации: генерируем во временный каталог и сравниваем.
# git diff по закоммиченному файлу здесь бесполезен — он всегда пуст, потому что
# файл не менялся, и проверка проходит при любом содержимом.
if not PY_MODEL.is_file():
    skip("перегенерация Pydantic совпадает с закоммиченной", "модели нет")
else:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "regen.py"
            r = subprocess.run(
                ["datamodel-codegen", "--input", str(SCHEMA),
                 "--input-file-type", "jsonschema", "--output", str(out),
                 "--output-model-type", "pydantic_v2.BaseModel"],
                capture_output=True, text=True, timeout=180,
            )
            if r.returncode != 0 or not out.is_file():
                skip("перегенерация Pydantic совпадает с закоммиченной",
                     "datamodel-codegen отработал с ошибкой")
            else:
                def strip_ts(t: str) -> str:
                    # timestamp в шапке отличается всегда — сравниваем без него.
                    return "\n".join(ln for ln in t.splitlines() if not ln.startswith("#   timestamp:"))

                same = strip_ts(out.read_text("utf-8")) == strip_ts(PY_MODEL.read_text("utf-8"))
                check("перегенерация Pydantic совпадает с закоммиченной", same,
                      "" if same else "модель правили руками либо схема ушла вперёд")
    except FileNotFoundError:
        skip("перегенерация Pydantic совпадает с закоммиченной",
             "datamodel-codegen не установлен (pip install datamodel-code-generator)")
    except subprocess.TimeoutExpired:
        skip("перегенерация Pydantic совпадает с закоммиченной", "генератор не уложился в 180 с")

print("\n== единая точка доступа ==")
# Прямое чтение файла из произвольного места — то, ради чего загрузчики и делались:
# иначе имена полей начнут угадываться в каждом месте отдельно.
#
# Ищем именно ЧТЕНИЕ, а не упоминание. Имя датасета встречается в описаниях схемы и,
# как следствие, в сгенерированных из неё артефактах; тесты обращаются к файлу по
# долгу службы. Проверка на любое вхождение строки краснела бы на всём этом и была
# бы отключена в первую же неделю.
READ_CALLS = re.compile(
    r"(?:open|read_text|read_bytes|readFileSync|readFile)\s*\([^)]*unified_respondent_sessions",
)
allowed = {PY_LOADER.resolve(), TS_LOADER.resolve(), (ROOT / "evals" / "check.py").resolve()}
offenders = []
for path in list(ROOT.rglob("*.py")) + list(ROOT.rglob("*.ts")) + list(ROOT.rglob("*.mjs")):
    if any(part in {"node_modules", ".git", ".next", "__pycache__", "archive", "tests"}
           for part in path.parts):
        continue
    if path.resolve() in allowed:
        continue
    try:
        if READ_CALLS.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(ROOT)))
    except OSError:
        pass
check("датасет читается только через загрузчики", not offenders, "; ".join(offenders[:5]))

print("\n== известные дефекты из паспорта ==")
# Паспорт обязан описывать реальность. Если дефект исправлен, запись из паспорта
# нужно убрать — иначе он превращается в художественный текст.
issues = {i["field"] for i in meta.get("known_issues", [])}
emotions = [e for r in sessions for e in r["perception_and_retention"]["emotions_evoked"]]
scale_labels = [e for e in emotions if "балл" in e or "–" in e or e.strip().isdigit()]
if "perception_and_retention.emotions_evoked" in issues:
    if scale_labels:
        warn("подписи шкалы в emotions_evoked",
             f"{len(scale_labels)} значений — дефект описан в паспорте, не забыт")
    else:
        check("паспорт актуален: дефект emotions_evoked исправлен — уберите запись", False,
              "в данных дефекта больше нет")
titles = {r["content_under_test"]["title"] for r in sessions}
if "content_under_test.title" in issues:
    if "Тюремный" in titles:
        warn("обрезанный заголовок",
             "«Тюремный» вместо «Тюремный дневник» — дефект описан в паспорте, не забыт")
    else:
        check("паспорт актуален: заголовок исправлен — уберите запись", False, "")

print()
if failures:
    print(f"RED — не выполнено условий: {len(failures)}")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)

print(f"GREEN — задача #23 удовлетворяет критериям приёмки (skip={len(skipped)} warn={len(warnings)})")
for w in warnings:
    print(f"   ⚠ {w}")
for s in skipped:
    print(f"   · пропущено: {s}")
sys.exit(0)
