#!/usr/bin/env python3
"""
CDD-тест задачи #22 — «E2E-верификация».

CDD (из tasks.json):
  e2e_short: fixture 60s → REPORT_READY ≤ 10 мин, report.aggregate непустой,
             len(per_persona) == audience_size.
  e2e_long:  fixture ~12 мин, mode=long → map-reduce → stitched == true →
             REPORT_READY.

─── Что здесь проверяется на самом деле ──────────────────────────────────────
Гейты `e2e_short` и `e2e_long` в `evals/check.py` читают артефакты прогона. Пока
артефактов нет, обе метрики пишут `skip` — честно, но бесполезно. Задача #22 —
это то, что артефакты производит.

Отсюда главное свойство прогонщика, и проверяется оно первым: он не имеет права
записать артефакт, которого не заработал. Метрика читает файл и не знает, откуда
он взялся; артефакт, записанный при недоступном сервере или на половине прогона,
превращает `e2e_short` из гейта в украшение. Проверка этого свойства работает
без сервера: прогонщик натравливается на заведомо мёртвый адрес, и от него
требуется ненулевой код возврата и отсутствие файла.

─── Почему прогонщик ходит по HTTP, а не по браузеру ─────────────────────────
Acceptance задачи называет Playwright. Отступление сознательное, и вот почему.

Все условия CDD — про конвейер, а не про вёрстку: статус прогона, непустой
агрегат, число карточек персон, признак склейки. Ни одно из них браузер не
проверяет лучше HTTP, зато Playwright тянет в `apps/web` бинарные зависимости,
что запрещено §6 CLAUDE.md: `node_modules` общий для worktree, а собранный под
одну платформу пакет ломает запуск на другой. Это уже стоило прохода.

Проверка вёрстки отчёта нужна отдельно и остаётся ненаписанной — это сказано в
PR и в PROGRESS_REPORT, а не спрятано за зелёной метрикой.

─── Golden-сеты ×3 ───────────────────────────────────────────────────────────
«3/3 = trust» из acceptance: конвейер, прошедший один раз, не доказан. Между
прогонами меняются seed и порядок ответов модели, и одиночный зелёный прогон
не отличает работающий конвейер от везения. Поэтому прогонщик умеет повторять
прогон, а метрика требует, чтобы прошли все повторы, а не большинство.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
EVALS = REPO / "evals"
RUNNER = EVALS / "e2e_run.py"
FIXTURES = EVALS / "fixtures"

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, "OK" if ok else "FAIL", detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if not ok and detail else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, "SKIP", reason))
    print(f"  SKIP  {name}  →  {reason}")


# ═══════════════════════════════════════════════════════════════════════════
# ПРОГОНЩИК СУЩЕСТВУЕТ И СОГЛАСОВАН С ГЕЙТОМ
# ═══════════════════════════════════════════════════════════════════════════

print("== Прогонщик ==")

check("прогонщик E2E существует", RUNNER.is_file(),
      "нет evals/e2e_run.py: метрики e2e_short и e2e_long будут вечно писать skip, "
      "потому что артефакты производить нечем")

runner_src = RUNNER.read_text("utf-8") if RUNNER.is_file() else ""

check("прогонщик умеет оба режима",
      '"short"' in runner_src and '"long"' in runner_src,
      "в прогонщике нет обоих режимов: e2e_long остался бы непроверяемым")

# Пути артефактов берутся из самого check.py, а не переписываются сюда строкой.
# Разъехавшиеся константы дали бы прогонщик, который пишет файл, и метрику,
# которая читает другой, — и оба выглядели бы исправными.
check_src = (EVALS / "check.py").read_text("utf-8")
artifact_names = ["e2e_short_report.json", "e2e_long_report.json"]
check("прогонщик пишет туда, откуда читает гейт",
      all(n in runner_src and n in check_src for n in artifact_names),
      f"расхождение имён артефактов: в прогонщике "
      f"{[n for n in artifact_names if n not in runner_src]}, "
      f"в гейте {[n for n in artifact_names if n not in check_src]}")


# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНОЕ СВОЙСТВО: НЕЗАРАБОТАННЫЙ АРТЕФАКТ НЕ ПИШЕТСЯ
# ═══════════════════════════════════════════════════════════════════════════

print("== Провал прогона не оставляет зелёного артефакта ==")

if not RUNNER.is_file():
    for n in ("провал даёт ненулевой код возврата",
              "провал не оставляет артефакта",
              "причина провала названа в выводе"):
        skip(n, "прогонщика нет")
else:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "artifacts"
        proc = subprocess.run(
            [sys.executable, str(RUNNER), "--mode", "short",
             "--base-url", "http://127.0.0.1:9", "--artifacts", str(out),
             "--timeout", "5"],
            capture_output=True, text=True, timeout=120, check=False,
        )
        combined = f"{proc.stdout}\n{proc.stderr}"

        check("провал даёт ненулевой код возврата", proc.returncode != 0,
              f"код {proc.returncode}: CI не отличит провалившийся прогон от успешного")

        written = sorted(p.name for p in out.glob("*.json")) if out.is_dir() else []
        check("провал не оставляет артефакта", written == [],
              f"записаны файлы {written}: гейт прочитает их и не узнает, что прогон "
              f"не состоялся — метрика превратится в украшение")

        check("причина провала названа в выводе",
              any(w in combined.lower() for w in
                  ("не удалось", "недоступ", "отказ", "connection", "ошибка")),
              f"вывод не объясняет провал: {combined.strip()[:160]!r}")


# ═══════════════════════════════════════════════════════════════════════════
# ФИКСТУРЫ
# ═══════════════════════════════════════════════════════════════════════════

print("== Фикстуры ==")

short_fixture = FIXTURES / "short_60s.mp4"
check("короткая фикстура на месте", short_fixture.is_file(),
      "нет evals/fixtures/short_60s.mp4 — e2e_short прогнать не на чем")

# Длинной фикстуры в репозитории нет, и это отдельное условие, а не молчание.
# Мегабайтам видео в git не место, но и «e2e_long не проверен» обязано быть
# видно в выводе теста, а не только в acceptance задачи.
long_fixture = FIXTURES / "long_12min.mp4"
if long_fixture.is_file():
    check("длинная фикстура на месте", True)
else:
    skip("длинная фикстура на месте",
         "нет evals/fixtures/long_12min.mp4 — e2e_long прогнать не на чем; "
         "файл в git не кладётся, путь задаётся через E2E_LONG_FIXTURE")

check("путь к длинной фикстуре настраивается снаружи",
      "E2E_LONG_FIXTURE" in runner_src,
      "путь к длинному видео зашит: положить двенадцатиминутный ролик в git "
      "нельзя, а прогнать e2e_long надо")


# ═══════════════════════════════════════════════════════════════════════════
# GOLDEN-СЕТЫ ×3
# ═══════════════════════════════════════════════════════════════════════════

print("== Golden-сеты ×3 ==")

check("прогонщик умеет повторять прогон", "--repeat" in runner_src,
      "нет повторов: одиночный зелёный прогон не отличает работающий конвейер "
      "от везения")

check("артефакт несёт число прогонов и число успешных",
      '"runs"' in runner_src and '"passed"' in runner_src,
      "в артефакте нет счётчиков повторов — гейт не сможет потребовать 3/3")

check("гейт требует все повторы, а не большинство",
      "passed" in check_src and "runs" in check_src,
      "evals/check.py не смотрит на счётчики повторов: два прогона из трёх "
      "прошли бы как доверенный результат")


# ═══════════════════════════════════════════════════════════════════════════
# СОСТАВ АРТЕФАКТА
# ═══════════════════════════════════════════════════════════════════════════

print("== Состав артефакта ==")

# Поля, которые читает check.py. Прогонщик обязан их писать, иначе метрика
# упадёт не на дефекте конвейера, а на своей же несогласованности.
REQUIRED = ["status", "mode", "audience_size", "per_persona", "aggregate",
            "elapsed_sec", "stitched"]
missing = [f for f in REQUIRED if f'"{f}"' not in runner_src]
check("прогонщик заполняет все поля, которые читает гейт", not missing,
      f"нет в прогонщике: {missing}")


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Поведенческий уровень ==")

BEHAVIOUR = [
    "e2e_short: прогон доходит до REPORT_READY за 10 минут",
    "e2e_short: агрегат непустой, карточек столько же, сколько персон",
    "e2e_long: склейка отработала (stitched)",
]

base_url = os.environ.get("BASE_URL")
if not base_url:
    for n in BEHAVIOUR:
        skip(n, "BASE_URL не задан — сервера нет")
else:
    art_dir = EVALS / "artifacts"
    short_art = art_dir / "e2e_short_report.json"

    proc = subprocess.run(
        [sys.executable, str(RUNNER), "--mode", "short", "--base-url", base_url,
         "--artifacts", str(art_dir), "--timeout", "600"],
        capture_output=True, text=True, timeout=1800, check=False,
    )
    if proc.returncode != 0 or not short_art.is_file():
        for n in BEHAVIOUR[:2]:
            check(n, False, f"прогон не состоялся: {proc.stderr.strip()[:200]}")
    else:
        a = json.loads(short_art.read_text("utf-8"))
        check(BEHAVIOUR[0],
              a.get("status") == "REPORT_READY" and a.get("elapsed_sec", 1e9) <= 600,
              f"status={a.get('status')} elapsed={a.get('elapsed_sec')}с")
        check(BEHAVIOUR[1],
              bool(a.get("aggregate")) and len(a.get("per_persona") or []) == a.get("audience_size"),
              f"агрегат={'есть' if a.get('aggregate') else 'пуст'}, "
              f"карточек {len(a.get('per_persona') or [])} против "
              f"{a.get('audience_size')} персон")

    long_fixture_path = os.environ.get("E2E_LONG_FIXTURE")
    if not long_fixture_path or not Path(long_fixture_path).is_file():
        skip(BEHAVIOUR[2],
             "E2E_LONG_FIXTURE не указывает на файл — двенадцатиминутного ролика нет")
    else:
        long_art = art_dir / "e2e_long_report.json"
        proc = subprocess.run(
            [sys.executable, str(RUNNER), "--mode", "long", "--base-url", base_url,
             "--artifacts", str(art_dir), "--timeout", "3600"],
            capture_output=True, text=True, timeout=7200, check=False,
        )
        if proc.returncode != 0 or not long_art.is_file():
            check(BEHAVIOUR[2], False, f"прогон не состоялся: {proc.stderr.strip()[:200]}")
        else:
            a = json.loads(long_art.read_text("utf-8"))
            check(BEHAVIOUR[2],
                  a.get("status") == "REPORT_READY" and bool(a.get("stitched")),
                  f"status={a.get('status')} stitched={a.get('stitched')}")


sys.exit(verdict(results, "#22"))
