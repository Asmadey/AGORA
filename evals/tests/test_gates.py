#!/usr/bin/env python3
"""
Тест гейтов, а не задач графа.

Появился после прохода, в котором шесть дефектов, делавших продукт нерабочим,
прошли мимо зелёного CI. Дефекты были разные, причина одна: проверки не отличали
«проверено» от «пропущено», а метрика секретов не смотрела туда, где лежали
пароли.

Здесь проверяется сам инструментарий. Если он врёт, вердикты по задачам не
значат ничего — а именно так и вышло: #7, #8, #10, #24 стояли `done`, ни разу не
будучи проверенными поведенчески.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, "OK" if ok else "FAIL", detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, "SKIP", reason))
    print(f"  SKIP  {name}  →  {reason}")


def run_secret_scan() -> tuple[str, str]:
    """Возвращает (статус, подробности) метрики secret_scan из check.py."""
    proc = subprocess.run(
        [sys.executable, "-c",
         "import json,sys;sys.path.insert(0,'evals');"
         "import check;r=check.check_secret_scan();"
         "print(json.dumps({'status':r['status'],'detail':r.get('detail',''),"
         "'actual':r.get('actual','')}))"],
        cwd=REPO, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        return "error", (proc.stderr or proc.stdout)[-200:]
    import json as _json
    try:
        data = _json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return "error", proc.stdout[-200:]
    return data["status"], f"{data['actual']} — {data['detail']}"


# ── 1. secret_scan обязан видеть каталог с тестами ───────────────────────────
# Два пароля пролежали в evals/tests открытым текстом и метрику не покраснели:
# каталог «evals» стоял в skip_dirs, то есть исключался из обхода целиком.

print("== Гейт секретов ==")

base_status, base_detail = run_secret_scan()
if base_status == "error":
    skip("secret_scan видит каталог evals", f"метрика не запустилась: {base_detail}")
    skip("secret_scan ловит литеральный пароль", "метрика не запустилась")
    skip("secret_scan не краснеет на плейсхолдерах", "метрика не запустилась")
else:
    check(
        "чистое дерево даёт зелёный secret_scan",
        base_status == "pass",
        f"статус={base_status} {base_detail}",
    )

    # Подкладываем пароль ровно туда, где он однажды уже лежал.
    #
    # Строка собирается из частей намеренно: записанная литералом, она сделала бы
    # срабатывание на самом этом файле, и тест начал бы ловить собственную
    # наживку вместо подложенного файла.
    key = "pass" + "word"
    value = "Agora" + "Owner2026!"
    canary = TESTS_DIR / "_gate_canary_tmp.py"
    canary.write_text(
        "LOGIN_FORM = {\n"
        '    "email": "owner@agora.local",\n'
        f'    "{key}": "{value}",\n'
        "}\n",
        encoding="utf-8",
    )
    try:
        status, detail = run_secret_scan()
        check(
            "secret_scan ловит литеральный пароль в evals/tests",
            status == "fail" and "_gate_canary_tmp" in detail,
            f"статус={status}; {detail}",
        )
    finally:
        canary.unlink(missing_ok=True)

    # Плейсхолдер утечкой не является: гейт, который краснеет на примерах,
    # начинают игнорировать, и он перестаёт ловить настоящее.
    canary2 = TESTS_DIR / "_gate_canary_ok_tmp.py"
    canary2.write_text(
        'EXAMPLE = {"password": "CHANGE_ME"}\n'
        'FROM_ENV = {"password": os.environ["MEMBER_PASSWORD"]}\n',
        encoding="utf-8",
    )
    try:
        status2, detail2 = run_secret_scan()
        check(
            "secret_scan не краснеет на плейсхолдере и переменной окружения",
            status2 == "pass",
            f"статус={status2}; {detail2}",
        )
    finally:
        canary2.unlink(missing_ok=True)


# ── 2. Пропуск обязан быть обусловлен проверкой среды ────────────────────────
# `skip("кейс", "требует запущенного сервера")` без единого обращения к
# окружению — это не отсутствие среды, а невыполненная работа. За проход таких
# нашлось три штуки в двух файлах, и обе задачи стояли `done`.

print("\n== Обусловленность пропусков ==")


def unconditional_skips(path: Path) -> list[int]:
    """
    Номера строк с вызовами skip(), не находящимися ни в одной ветке if/else,
    ни в except. Такой вызов исполняется всегда — среда на него не влияет.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    bad: list[int] = []

    class Walker(ast.NodeVisitor):
        def __init__(self) -> None:
            self.depth = 0  # вложенность в if / try-except / with

        def _guarded(self, node: ast.AST) -> None:
            self.depth += 1
            self.generic_visit(node)
            self.depth -= 1

        visit_If = _guarded
        visit_Try = _guarded
        visit_ExceptHandler = _guarded

        def visit_Call(self, node: ast.Call) -> None:
            is_skip = (
                isinstance(node.func, ast.Name) and node.func.id == "skip"
            )
            if is_skip and self.depth == 0:
                bad.append(node.lineno)
            self.generic_visit(node)

    Walker().visit(tree)
    return bad


offenders: list[str] = []
for test_file in sorted(TESTS_DIR.glob("test_task*.py")):
    lines = unconditional_skips(test_file)
    if lines:
        offenders.append(f"{test_file.name}:{','.join(map(str, lines))}")

check(
    "в тестах задач нет безусловных skip",
    not offenders,
    "; ".join(offenders) if offenders else "",
)


# ── 3. Пароли не хранятся в исходниках тестов ────────────────────────────────
# Отдельно от secret_scan: та метрика — гейт CI, а эта проверка объясняет, что
# именно не так, и держит правило видимым в самом наборе тестов.

print("\n== Учётные данные в тестах ==")

import re  # noqa: E402

literal_pw = re.compile(
    r'["\']password["\']\s*[:=]\s*["\'](?!CHANGE_ME|\$|<)[^"\']{6,}["\']'
)
pw_hits: list[str] = []
for test_file in sorted(TESTS_DIR.glob("*.py")):
    if test_file.name == Path(__file__).name:
        continue
    for i, line in enumerate(test_file.read_text(encoding="utf-8").splitlines(), 1):
        if literal_pw.search(line):
            pw_hits.append(f"{test_file.name}:{i}")

check(
    "паролей открытым текстом в тестах нет",
    not pw_hits,
    "; ".join(pw_hits) if pw_hits else "",
)


# ── Итог ─────────────────────────────────────────────────────────────────────

n_pass = sum(1 for _, s, _ in results if s == "OK")
n_fail = sum(1 for _, s, _ in results if s == "FAIL")
n_skip = sum(1 for _, s, _ in results if s == "SKIP")

if n_fail:
    print(f"\nRED — не выполнено условий: {n_fail}")
    for name, status, detail in results:
        if status == "FAIL":
            print(f"  · {name}" + (f" ({detail})" if detail else ""))
else:
    print(f"\nGREEN — гейты исправны (pass={n_pass} skip={n_skip})")

sys.exit(1 if n_fail else 0)
