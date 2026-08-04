#!/usr/bin/env python3
"""
Тест метрики `build_worker` в evals/check.py — различение «ruff не установлен» и
«ruff нашёл замечания».

Запуск (stdlib-only, как и остальные тесты):
    python evals/tests/test_check_build_worker.py

Exit 0 = green. Exit 1 = red, с перечнем невыполненных условий.

Почему этот тест существует. `python -m ruff` при отсутствии модуля выходит с
кодом 1 — ровно тем же кодом, каким ruff сообщает о найденных замечаниях. Guard
`if lint.returncode not in (0, 1)` поэтому недостижим, и на машине без ruff
метрика писала `build_worker = fail / "ruff findings"`: читателя отправляли
искать несуществующие замечания линтера вместо того, чтобы поставить ruff.
По §9 CLAUDE.md вводящая в заблуждение метрика хуже отсутствующей, так что
контракт здесь такой: нет инструмента — skip (контракт неполон), есть замечания
— fail.

Что НЕ проверяется здесь: реальный прогон pytest и ruff в services/agent-core —
это делает сам check.py в среде пользователя и джоба «Воркер» в CI. Здесь
проверяется только классификация результата, поэтому граница с внешним миром
(subprocess.run) подменяется, а сама логика check.py исполняется настоящая.
"""
from __future__ import annotations
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK_PY = ROOT / "evals" / "check.py"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(f"{name}{': ' + detail if detail else ''}")


def load_check_module():
    spec = importlib.util.spec_from_file_location("agora_check", CHECK_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeRun:
    """Подменяет subprocess.run: pytest всегда зелёный, ruff — по сценарию.

    Настоящий CompletedProcess, а не самодельный объект: check.py читает у него
    returncode/stdout/stderr, и подмена не должна расходиться с реальным типом.
    """

    def __init__(self, ruff_result: subprocess.CompletedProcess):
        self.ruff_result = ruff_result
        self.calls: list[list[str]] = []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        if "ruff" in args:
            return self.ruff_result
        # pytest
        return subprocess.CompletedProcess(args, 0, stdout="1 passed\n", stderr="")


def run_worker_build(mod, ruff_result: subprocess.CompletedProcess) -> dict:
    fake = _FakeRun(ruff_result)
    real = subprocess.run
    subprocess.run = fake  # type: ignore[assignment]
    try:
        return mod._worker_build()
    finally:
        subprocess.run = real  # type: ignore[assignment]


if not CHECK_PY.is_file():
    check("evals/check.py существует", False, str(CHECK_PY))
else:
    mod = load_check_module()

    if not mod.CORE.exists():
        # Без services/agent-core метрика честно уходит в skip раньше ruff —
        # проверять здесь нечего, но и молчать нельзя.
        check("services/agent-core присутствует", False,
              "без воркера ветку ruff не пройти")
    else:
        # ── 1. ruff не установлен ─────────────────────────────────────────────
        # Точный вывод CPython: код возврата 1, stdout пуст, сообщение в stderr.
        missing = subprocess.CompletedProcess(
            ["python", "-m", "ruff", "check", "."], 1,
            stdout="", stderr=f"{sys.executable}: No module named ruff\n")
        res = run_worker_build(mod, missing)
        check("нет ruff → status=skip", res["status"] == "skip",
              f"получено {res['status']}")
        check("нет ruff → actual не говорит о замечаниях линтера",
              "findings" not in (res.get("actual") or ""),
              f"actual={res.get('actual')!r}")
        check("нет ruff → в отчёте видно, что инструмент отсутствует",
              "ruff" in (res.get("actual") or "").lower()
              or "ruff" in (res.get("detail") or "").lower(),
              f"actual={res.get('actual')!r} detail={res.get('detail')!r}")

        # ── 2. ruff установлен и нашёл замечания ─────────────────────────────
        findings = subprocess.CompletedProcess(
            ["python", "-m", "ruff", "check", "."], 1,
            stdout="agent_core/x.py:1:1: F401 unused import\nFound 1 error.\n",
            stderr="")
        res = run_worker_build(mod, findings)
        check("замечания ruff → status=fail", res["status"] == "fail",
              f"получено {res['status']}")
        check("замечания ruff → actual говорит о замечаниях",
              "findings" in (res.get("actual") or ""),
              f"actual={res.get('actual')!r}")

        # ── 3. ruff установлен и чист ────────────────────────────────────────
        clean = subprocess.CompletedProcess(
            ["python", "-m", "ruff", "check", "."], 0,
            stdout="All checks passed!\n", stderr="")
        res = run_worker_build(mod, clean)
        check("чистый ruff → status=pass", res["status"] == "pass",
              f"получено {res['status']}")

        # ── 4. ruff упал сам (не 0 и не 1) ───────────────────────────────────
        # Ошибка запуска инструмента — это не «замечания линтера»: отчёт не
        # должен отправлять читателя искать несуществующие findings.
        broken = subprocess.CompletedProcess(
            ["python", "-m", "ruff", "check", "."], 2,
            stdout="", stderr="ruff failed: invalid configuration\n")
        res = run_worker_build(mod, broken)
        check("ruff завершился с кодом 2 → это не 'ruff findings'",
              "findings" not in (res.get("actual") or ""),
              f"actual={res.get('actual')!r}")
        check("ruff завершился с кодом 2 → статус не pass",
              res["status"] != "pass", f"получено {res['status']}")

# ── итог ─────────────────────────────────────────────────────────────────
print()
if failures:
    print(f"RED — не выполнено условий: {len(failures)}")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)

print("GREEN — build_worker различает отсутствие ruff и замечания ruff")
sys.exit(0)
