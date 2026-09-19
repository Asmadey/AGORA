#!/usr/bin/env python3
"""CDD checks for the persona judge's omission and skeleton boundaries.

The static level is deterministic and runs in every environment. The behavioral
level uses the real persona-validation client only when the worker dependencies
and model credentials are present; otherwise it reports SKIP honestly.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROMPT = REPO / "prompts" / "persona.validate.md"
VALIDATOR = REPO / "services" / "agent-core" / "agent_core" / "persona" / "validate.py"
TASK26 = REPO / "evals" / "tests" / "test_task26_prompt_studio.py"


def fail(message: str) -> None:
    raise AssertionError(message)


def static_checks() -> None:
    prompt = PROMPT.read_text(encoding="utf-8")
    normalized_prompt = " ".join(prompt.split())
    validator = VALIDATOR.read_text(encoding="utf-8")

    required_rules = (
        "Отсутствие упоминания атрибута в тексте само по себе не является расхождением",
        "Судья ищет сказанное НЕ ТО, а не несказанное",
        "Атрибуты не оцениваются между собой",
        "Атрибуты - источник истины",
        "Если два атрибута кажутся несовместимыми",
        "свойство сэмплирования, а не дефект текста",
        "Сравнивай текст с атрибутами, а не атрибуты между собой",
    )
    for phrase in required_rules:
        if phrase not in normalized_prompt:
            fail(f"в prompt persona.validate отсутствует правило: {phrase}")

    for heading in ("Противоречие атрибуту", "Досочинённый факт", "Обезличенность"):
        if heading not in prompt:
            fail(f"в prompt persona.validate исчез класс расхождений: {heading}")

    for invariant in (
        "{{verbatim_pool}}",
        '"consistent": true',
        '"issues": []',
        '"confidence": 0.0',
    ):
        if invariant not in prompt:
            fail(f"в prompt persona.validate исчез обязательный контракт: {invariant}")

    if "MIN_CONFIDENCE = 0.9" not in validator:
        fail("MIN_CONFIDENCE = 0.9 изменён или исчез")
    if "MAX_ATTEMPTS = 3" not in validator:
        fail("MAX_ATTEMPTS изменён или исчез")
    if "После исчерпания попыток персона остаётся в наборе с пометкой" not in validator:
        fail("потеряно правило сохранять персону после исчерпания попыток")

    measurement = (
        "35%",
        "40%",
        "50%",
        "74 претензий",
        "27",
        "класс 1",
        "класс 2",
        "класс 3",
    )
    for phrase in measurement:
        if phrase not in validator:
            fail(f"в докстринге validate.py отсутствует замер: {phrase}")

    task26 = subprocess.run(
        [sys.executable, str(TASK26)],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    sync_marker = "тексты в засеве совпадают с файлами"
    if task26.returncode != 0 or "OK" not in task26.stdout or sync_marker not in task26.stdout:
        detail = (task26.stdout + task26.stderr)[-4000:]
        fail(f"task26 не подтвердил синхронизацию файла и засева:\n{detail}")

    print("STATIC PERSONA JUDGE CHECKS PASSED")


class LivePersonaJudge:
    """Adapter from the production QwenTextClient to validate_persona."""

    def __init__(self) -> None:
        from agent_core.persona.enrich import QwenTextClient
        from agent_core.schemas.responses import MAX_TOKENS, PERSONA_VALIDATION

        self.client = QwenTextClient(
            temperature=0.0,
            response_schema=("PersonaValidation", PERSONA_VALIDATION),
            max_tokens=MAX_TOKENS["persona_validation"],
        )

    def complete(self, *, prompt: str) -> str:
        return self.client.complete(prompt=prompt)


def behavioral_checks() -> None:
    sys.path.insert(0, str(REPO / "services" / "agent-core"))
    from _harness import worker_deps_missing  # noqa: E402

    missing = worker_deps_missing("openai")
    required_env = ("OPENAI_BASE_URL", "OPENAI_API_KEY", "AI_MODEL")
    absent = [name for name in required_env if not os.environ.get(name)]
    if missing or absent:
        reason = missing or "нет переменных: " + ", ".join(absent)
        print(f"BEHAVIORAL PERSONA JUDGE SKIP: {reason}")
        return

    from agent_core.persona.validate import validate_persona  # noqa: E402

    template = PROMPT.read_text(encoding="utf-8")
    cases = (
        (
            "omitted attribute",
            {
                "name": "Мария",
                "lifestyle_and_interests": {
                    "education_level": "среднее специальное",
                    "hobbies": ["спорт", "фотография"],
                },
                "narrative": "Мария любит спорт и фотографию, а свободное время проводит с близкими.",
            },
            True,
        ),
        (
            "age contradiction",
            {
                "name": "Мария",
                "age": 25,
                "age_group": "25-34",
                "narrative": "Девятнадцатилетняя Мария выбирает спокойные истории и внимательно следит за сюжетом.",
            },
            False,
        ),
        (
            "independent sampled attributes",
            {
                "name": "Мария",
                "viewer_behavior": {
                    "attention_span": "длинный",
                    "length_tolerance": "короткие ролики",
                },
                "narrative": "Мария внимательно относится к содержанию и ценит выразительную визуальную подачу.",
            },
            True,
        ),
    )

    judge = LivePersonaJudge()
    results = []
    for label, persona, expected in cases:
        verdict = validate_persona(persona, client=judge, template=template)
        actual = verdict.consistent
        results.append(
            {
                "case": label,
                "expected": expected,
                "actual": actual,
                "checked": verdict.checked,
                "confidence": verdict.confidence,
            }
        )
        if not verdict.checked or actual is not expected:
            fail(f"live case failed: {json.dumps(results[-1], ensure_ascii=False)}")

    print("BEHAVIORAL PERSONA JUDGE PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static", action="store_true")
    parser.add_argument("--behavior", action="store_true")
    args = parser.parse_args()
    # Без флагов выполняются ОБА уровня. Обязательный флаг здесь стоил красного
    # CI: гейт гоняет каждый evals/tests/test_*.py голым `python3 <файл>`, и
    # argparse отвечал ему ошибкой разбора, а не результатом проверки. Уровень
    # выбирается флагом только когда его выбирают осознанно.
    if args.static:
        static_checks()
    elif args.behavior:
        behavioral_checks()
    else:
        static_checks()
        behavioral_checks()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
