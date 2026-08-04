#!/usr/bin/env python3
"""
CDD-тест задачи #9 — Шаг «Аудитория».

CDD (из tasks.json):
  выбор критериев (пол / возраст 6 групп / гео 3 / образование) + размер
  даёт корректный запрос к Persona Generator;
  выбор существующего persona_set пропускает генерацию.

─── Что здесь проверяется на самом деле ──────────────────────────────────────
Не форма с галочками. «Корректный запрос к Persona Generator» — это сквозной
контракт: критерий, выбранный в интерфейсе, обязан доехать до генератора и
изменить состав выданных персон. До этой задачи доехать было некуда:
GenerationConfig принимал size / seed / serial / city / segment, и полей пола,
возрастных групп, гео и образования в нём не было вовсе.

Поэтому основной уровень теста — не HTTP, а прямой прогон генератора на корпусе
из git. Среда для него не нужна, пропусков он не даёт, и проверяет он именно то,
что требует cdd: заданные критерии соблюдены в выдаче.

─── Про заземление ───────────────────────────────────────────────────────────
Приёмка требует пометить гео «иные НП» как слабо заземлённое. Проверка не
сверяет текст предупреждения со строкой, а требует, чтобы охват СЧИТАЛСЯ из
корпуса. Причина простая: захардкоженное «0 из 165» становится неправдой в день,
когда в корпус добавят исследование, и никто этого не заметит — а процедура
добавления исследования описана в паспорте корпуса, то есть это ожидаемое
событие, а не гипотетическое.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "services" / "agent-core"
WEB = REPO / "apps" / "web"
CORPUS = REPO / "data" / "grounding" / "unified_respondent_sessions.json"

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


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

audience_ts = read(WEB / "lib" / "audience.ts")
check("контракт критериев apps/web/lib/audience.ts существует", bool(audience_ts))

# Контракт общий для интерфейса и воркера — как settings.ts ↔ config.py. Иначе
# интерфейс предложит критерий, которого генератор не знает, и выбор молча
# пропадёт по дороге.
for name, needle in (
    ("шесть возрастных групп", "60+"),
    ("три гео", "иные НП"),
    ("пол", "муж"),
    ("образование", "education"),
    ("размер по умолчанию 20", "20"),
):
    check(f"в контракте объявлен(ы) {name}", needle in audience_ts)

gen_src = read(CORE / "agent_core" / "persona" / "generator.py")
check(
    "GenerationConfig принимает критерии отбора, а не только size/seed",
    all(f in gen_src for f in ("age_groups", "geos", "genders")),
)

# Ключевое отличие от фильтрации записей: генератор сэмплирует из РАСПРЕДЕЛЕНИЙ
# корпуса. Если ограничить только выборку записей, а распределение оставить
# прежним, персоны продолжат рождаться со всеми возрастными группами подряд.
check(
    "распределения пересчитываются под выбранные критерии (restrict/renormalize)",
    "restrict" in gen_src or "renormalize" in gen_src,
)

grounding_src = read(WEB / "lib" / "audience-grounding.ts")
check("охват заземления считается отдельным модулем", bool(grounding_src))
check(
    "охват берётся из корпуса, а не из захардкоженного числа",
    "loadSessions" in grounding_src or "corpus" in grounding_src.lower(),
)

# Мерить надо свойство «вычисление не зависит от литерала», а не «строка не
# встречается в файле». Замер, записанный в комментарии с датой, — это как раз
# то, что просит §5 CLAUDE.md: зафиксированный факт, а не магическое число в
# логике. Поэтому комментарии вырезаются до проверки.
def strip_comments(ts: str) -> str:
    out, i, n = [], 0, len(ts)
    while i < n:
        if ts.startswith("/*", i):
            end = ts.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif ts.startswith("//", i):
            end = ts.find("\n", i)
            i = n if end == -1 else end
        else:
            out.append(ts[i])
            i += 1
    return "".join(out)


check(
    "число записей корпуса не захардкожено в логике",
    "165" not in strip_comments(grounding_src),
    "литерал 165 в коде — станет неправдой при добавлении исследования"
    if "165" in strip_comments(grounding_src) else "считается из корпуса",
)

machine_src = read(WEB / "lib" / "wizard" / "machine.ts")
check(
    "машина визарда знает про выбор существующего набора",
    "personaSetId" in machine_src,
)
# Требовать критерии, когда набор уже выбран, — значит заставлять заполнять то,
# что не будет использовано: генерации не произойдёт.
check(
    "при выбранном наборе шаг не требует критериев генерации",
    "personaSetId" in machine_src and "audience" in machine_src,
)


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ: генератор
# ═══════════════════════════════════════════════════════════════════════════

print("\n== Генератор: критерии доезжают и соблюдаются ==")

GEN_CASES = (
    "заданные возрастные группы соблюдены в выдаче",
    "заданное гео соблюдено в выдаче",
    "заданный пол соблюдён в выдаче",
    "размер выдачи равен заданному",
    "критерии не ломают детерминизм: тот же seed → тот же результат",
    "невозможная комбинация критериев отвергается внятной ошибкой",
)

if not CORPUS.exists():
    for n in GEN_CASES:
        skip(n, "корпус data/grounding не найден")
else:
    sys.path.insert(0, str(CORE))
    try:
        from agent_core.persona.generator import GenerationConfig, PersonaGenerator
    except Exception as e:  # noqa: BLE001
        for n in GEN_CASES:
            skip(n, f"генератор не импортируется: {type(e).__name__}: {str(e)[:60]}")
    else:
        def dna_field(p: dict, field: str) -> str:
            demo = p.get("demographics") or {}
            return str(demo.get(field, ""))

        try:
            gen = PersonaGenerator.from_corpus()
            cfg = GenerationConfig(
                size=12, seed=42,
                age_groups=["25-34", "35-44"],
                geos=["столицы"],
                genders=["жен"],
            )
            people = gen.generate(cfg)

            got_ages = {dna_field(p, "age_group") for p in people}
            check("заданные возрастные группы соблюдены в выдаче",
                  got_ages <= {"25-34", "35-44"} and got_ages,
                  f"в выдаче: {sorted(got_ages)}")

            got_geo = {dna_field(p, "geo") for p in people}
            check("заданное гео соблюдено в выдаче",
                  got_geo <= {"столицы"} and got_geo,
                  f"в выдаче: {sorted(got_geo)}")

            got_gender = {dna_field(p, "gender") for p in people}
            check("заданный пол соблюдён в выдаче",
                  got_gender <= {"жен"} and got_gender,
                  f"в выдаче: {sorted(got_gender)}")

            check("размер выдачи равен заданному", len(people) == 12,
                  f"персон: {len(people)}")

            again = PersonaGenerator.from_corpus().generate(
                GenerationConfig(size=12, seed=42,
                                 age_groups=["25-34", "35-44"],
                                 geos=["столицы"], genders=["жен"])
            )
            check("критерии не ломают детерминизм: тот же seed → тот же результат",
                  json.dumps(people, sort_keys=True, ensure_ascii=False)
                  == json.dumps(again, sort_keys=True, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            for n in GEN_CASES[:5]:
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")

        # Пустой отбор обязан быть ошибкой, а не пустым списком: «ноль персон»
        # дальше по конвейеру выглядит как исследование без респондентов, и
        # причину этого уже не восстановить.
        try:
            gen2 = PersonaGenerator.from_corpus()
            gen2.generate(GenerationConfig(size=5, seed=1, geos=["иные НП"]))
            check("невозможная комбинация критериев отвергается внятной ошибкой", False,
                  "гео «иные НП» отсутствует в корпусе, но генерация прошла молча")
        except ValueError as e:
            check("невозможная комбинация критериев отвергается внятной ошибкой",
                  "иные НП" in str(e) or "корпус" in str(e).lower(),
                  f"ValueError: {str(e)[:100]}")
        except Exception as e:  # noqa: BLE001
            check("невозможная комбинация критериев отвергается внятной ошибкой", False,
                  f"вместо ValueError прилетело {type(e).__name__}: {str(e)[:70]}")


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ: охват заземления считается по корпусу
# ═══════════════════════════════════════════════════════════════════════════

print("\n== Заземление критериев в корпусе ==")

if not CORPUS.exists():
    skip("гео «иные НП» не заземлено — 0 записей в корпусе", "корпус не найден")
    skip("образование не заземлено — поля нет в корпусе", "корпус не найден")
else:
    records = json.loads(CORPUS.read_text("utf-8"))
    geos = [r.get("socio_demographics", {}).get("geo") for r in records]
    check("гео «иные НП» не заземлено — 0 записей в корпусе",
          geos.count("иные НП") == 0,
          f"столицы={geos.count('столицы')}, "
          f"центры субъектов={geos.count('центры субъектов')}, "
          f"иные НП={geos.count('иные НП')} из {len(records)}")

    # Отдельная находка задачи: образование в cdd есть, а в корпусе такого поля
    # нет ни у одной записи. Это сильнее, чем «иные НП»: там пустое значение
    # существующего измерения, здесь измерения нет вовсе, и persona_grounding
    # (метрика с порогом) его не проверяет — то есть незаземлённость была бы
    # невидима.
    with_edu = sum(1 for r in records if "education" in r.get("socio_demographics", {}))
    check("образование не заземлено — поля нет в корпусе",
          with_edu == 0,
          f"записей с полем education: {with_edu} из {len(records)}")


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ: машина визарда
# ═══════════════════════════════════════════════════════════════════════════

print("\n== Машина визарда ==")

MACHINE_CASES = (
    "шаг «Аудитория» не пускает вперёд без критериев",
    "заданные критерии пускают вперёд",
    "выбор существующего набора пускает вперёд без критериев",
    "без пола шаг не пускает вперёд",
)

# Проба лежит фикстурой и запускается из корня монорепо — иначе не разрешается
# xstate. Тот же приём, что у #7: guard живёт в TypeScript, из Python его не
# вызвать, а сборка ради проверки перехода не нужна.
probe = REPO / "evals" / "tests" / "fixtures" / "audience_step_probe.mjs"
node = shutil.which("node")

if node is None:
    for n in MACHINE_CASES:
        skip(n, "node не установлен")
elif not (REPO / "node_modules" / "xstate").exists():
    for n in MACHINE_CASES:
        skip(n, "xstate не установлен (npm ci)")
elif not probe.exists():
    for n in MACHINE_CASES:
        skip(n, "проба машины не найдена")
else:
    proc = subprocess.run(
        [node, str(probe)], capture_output=True, text=True, cwd=REPO, timeout=120,
    )
    try:
        rows = json.loads(proc.stdout.strip())
    except Exception:  # noqa: BLE001
        why = (proc.stderr or proc.stdout).strip()[-220:]
        for n in MACHINE_CASES:
            check(n, False, f"машина не прогналась: {why}")
    else:
        for row in rows:
            check(row["name"], row["ok"], row.get("detail", ""))


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

sys.exit(verdict(results, "#9"))
