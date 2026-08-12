#!/usr/bin/env python3
"""
Тест не выдаёт отсутствие зависимости за дефект кода.

Прогон всей сюиты на сервере 12.08 дал красное у четырёх задач:

    #15  транскрипт непустой   → ModuleNotFoundError: No module named 'faster_whisper'
    #18  distinct-2 выше порога → модель не дала ни одного ответа: ModuleNotFoundError: openai
    #19  живой судья ловит…     → судья не увидел противоречия
    #20  живая модель даёт…     → нарратив не собран: ModuleNotFoundError: openai

Ни одна из четырёх претензий не была правдой. `openai`, `faster_whisper` и
`pyannote.audio` живут в образе воркера — там они и нужны, — а тесты
исполнялись питоном хоста, где их нет и быть не должно: ставить torch на хост
ради прогона тестов значит заводить вторую среду, которая разойдётся с первой.

─── Почему это дефект стенда, а не мелочь ───────────────────────────────────
Красное, которое не значит «сломано», разучивает читать вывод. Четыре задачи
краснели на любом правильно настроенном сервере, и единственный способ узнать
причину — открыть трассировку и заметить в ней `ModuleNotFoundError`. Ровно об
этом написана обвязка `_harness`: проверка обязана отличать «среды нет» от
«код сломан», и обязана отличать «среды нет» от «среда есть, а проверку не
выполнили» — последнее даёт AMBER, а не зелёный.

Здесь проверяется и то, и другое: помощник `worker_deps_missing` отвечает за
распознавание, скрипт `evals/run_in_worker.sh` — за то, чтобы у ответа «запусти
в другом месте» это место существовало.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import verdict, worker_deps_missing  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "evals" / "tests"
RUNNER = REPO / "evals" / "run_in_worker.sh"

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, why: str = "", note: str = "") -> None:
    results.append((name, "OK" if ok else "FAIL", why))
    tail = note if ok else why
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {tail}" if tail else ""))


def skip(name: str, why: str) -> None:
    results.append((name, "SKIP", why))
    print(f"  SKIP  {name}  →  {why}")


# ─── Помощник ────────────────────────────────────────────────────────────────

print("\n== Распознавание чужой среды ==")

check(
    "имеющийся модуль не считается отсутствующим",
    worker_deps_missing("json", "pathlib") is None,
    f"вернулось {worker_deps_missing('json', 'pathlib')!r}",
)

absent = worker_deps_missing("модуля_с_таким_именем_нет")
check("отсутствующий модуль даёт причину, а не None", absent is not None)

# Составное имя — не частный случай, а тот самый, на котором помощник упал в
# первом же прогоне. `find_spec("pyannote.audio")` при отсутствии пакета
# `pyannote` не возвращает None: он импортирует родителя и бросает
# ModuleNotFoundError. Проверка «есть ли зависимость» роняла тест ровно тем
# исключением, ради которого написана.
try:
    dotted = worker_deps_missing("нет_такого_пакета.и_подмодуля")
    dotted_ok = dotted is not None
    dotted_why = f"вернулось {dotted!r}"
except Exception as exc:  # noqa: BLE001
    dotted_ok = False
    dotted_why = f"упал с {type(exc).__name__}: {exc}"
check("составное имя отсутствующего пакета не роняет проверку", dotted_ok, dotted_why)

# И обратное: составное имя существующего пакета опознаётся как имеющееся.
check(
    "составное имя имеющегося пакета опознаётся",
    worker_deps_missing("importlib.util", "json") is None,
    f"вернулось {worker_deps_missing('importlib.util', 'json')!r}",
)

check(
    "причина называет сам модуль",
    bool(absent) and "модуля_с_таким_именем_нет" in absent,
    f"причина: {absent!r}",
)

# Причина обязана быть действием, а не диагнозом. «Нет модуля openai» отправляет
# человека ставить openai на хост — то есть заводить вторую среду. Правильный
# следующий шаг ровно один, и он должен стоять в тексте.
check(
    "причина называет, чем это запускается",
    bool(absent) and "run_in_worker" in absent,
    f"причина: {absent!r}",
)

# ─── Четыре теста консультируются с помощником ──────────────────────────────

print("\n== Тесты, которым нужны зависимости воркера ==")

#: Задача → модули, без которых её поведенческий уровень бессмыслен.
NEEDS = {
    "test_task15_transcript.py": ("faster_whisper",),
    "test_task18_respondents.py": ("openai",),
    "test_task19_qa.py": ("openai",),
    "test_task20_analytics.py": ("openai",),
}

for filename, modules in NEEDS.items():
    path = TESTS / filename
    text = path.read_text("utf-8") if path.exists() else ""
    check(
        f"{filename} спрашивает про зависимости до прогона",
        "worker_deps_missing" in text,
        "нет обращения к worker_deps_missing — тест сообщит ModuleNotFoundError как дефект",
        note=", ".join(modules),
    )

# ─── Место, куда отсылает причина, существует ───────────────────────────────

print("\n== Запуск в образе воркера ==")

check("evals/run_in_worker.sh существует", RUNNER.exists())
check(
    "run_in_worker.sh исполняем",
    RUNNER.exists() and os.access(RUNNER, os.X_OK),
    "нет бита исполнения: chmod +x",
)

# ─── Поведенческий уровень: скрипт действительно даёт нужную среду ──────────

have_docker = subprocess.run(
    ["docker", "info"], capture_output=True, text=True
).returncode == 0 if subprocess.run(
    ["sh", "-c", "command -v docker"], capture_output=True
).returncode == 0 else False

IMAGE_CASE = "образ воркера отдаёт зависимости, которых нет на хосте"

if not have_docker:
    skip(IMAGE_CASE, "докера нет — проверять образ не на чем")
elif not RUNNER.exists():
    skip(IMAGE_CASE, "нет evals/run_in_worker.sh")
else:
    probe = (
        "import importlib, json, sys;"
        "print(json.dumps({m: importlib.util.find_spec(m) is not None"
        " for m in ('openai', 'faster_whisper')}))"
    )
    done = subprocess.run(
        [str(RUNNER), "--", "python", "-c", probe],
        capture_output=True, text=True, cwd=REPO, timeout=600,
    )
    # Скрипт печатает свои пояснения в stderr, чтобы stdout оставался
    # разбираемым: иначе проверка ниже читала бы вперемешку вывод теста и
    # вывод обвязки и ломалась бы от любой добавленной строки.
    tail = (done.stdout or "").strip().splitlines()
    payload = {}
    for line in reversed(tail):
        try:
            payload = json.loads(line)
            break
        except json.JSONDecodeError:
            continue

    if done.returncode != 0 and not payload:
        # Образа может не быть на машине разработчика — это отсутствие среды,
        # а не дефект. Отличается по тексту: докер говорит про образ прямо.
        why = (done.stderr or "")[-300:]
        if "No such image" in why or "Unable to find image" in why or "не собран" in why:
            skip(IMAGE_CASE, f"образ воркера не собран здесь: {why.strip()[:120]}")
        else:
            check(IMAGE_CASE, False, f"код {done.returncode}: {why.strip()[:200]}")
    else:
        check(
            IMAGE_CASE,
            payload.get("openai") is True and payload.get("faster_whisper") is True,
            f"внутри образа: {payload}",
            note=f"внутри образа: {payload}",
        )

    # Смысл всей затеи: на хосте этих модулей нет. Если они вдруг есть, значит
    # кто-то поставил torch на хост — и тогда две среды разойдутся молча.
    on_host = worker_deps_missing("openai", "faster_whisper")
    check(
        "на хосте этих зависимостей нет — среда одна, а не две",
        on_host is not None,
        "openai/faster_whisper установлены на хосте: появилась вторая среда, "
        "которая разойдётся с образом воркера и никем не сверяется",
        note="как и должно быть",
    )


sys.exit(verdict(results, "среда поведенческих проверок"))
