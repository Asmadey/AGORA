#!/usr/bin/env python3
"""
Судья `grounding` бракует выдумку, а не мнение.

─── Как это нашлось ──────────────────────────────────────────────────────────
Golden-сет 17.08.2026, три прогона после починки покрытия анкеты и подписей
сцен. Весь остаток отбраковок — `grounding`, по три-шесть на прогон. Разбор
претензий по сохранённому content pack показал: из тринадцати претензий
СПРАВЕДЛИВА ОДНА (деталь про команду из 150 человек привязана к 0:22–0:29, где
речь об отказе от DJI). Остальные двенадцать — придирки к языку:

    «цифры в 5,6 миллиарда выглядят как маркетинг»  → мнение о сумме
    «склейка стоковых кадров»                       → оценка монтажа
    «стоят у доски и считают деньги»                → пересказ «работы в финансах»
    «просчитался наперёд»                           → ирония о предвидении
    «отказался от DJI»                              → упрощение «отказа от предложения»

По трём из них судья прямо пишет в тексте претензии «это не явная выдумка»,
«допустимое упрощение», «это мнение» — и всё равно возвращает `regenerate`. Он
различает мнение и выдумку; ему нигде не сказано, что мнение законно.

─── Почему это дефект, а не строгость ────────────────────────────────────────
Продукт производит МНЕНИЯ синтетической аудитории. Вербатимы субъективны по
своему назначению. Судья, бракующий оценочную речь, требует от персоны
пересказывать транскрипт — и тогда продукт не производит ничего.

Оговорка, без которой этот тест читался бы нечестно: правка ПОДНИМАЕТ долю
выживших ответов, то есть двигает метрику, по которой нас же и меряют. Поэтому
граница задана перечнем случаев с обеих сторон, а не словом «мягче»: перечень
видно в дифференциале и можно оспорить построчно.

─── Два уровня ───────────────────────────────────────────────────────────────
Статический — по файлу миграции: граница описана, обе стороны названы,
идемпотентность по маркеру. Работает где угодно.

Поведенческий — настоящим судьёй на живой модели: мнение обязано пройти,
выдуманный факт обязан быть забракован. Без ключа и без образа воркера уходит
в SKIP, а не выдумывает результат (CLAUDE.md §9).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "infra" / "postgres" / "init" / "25_prompts_seed_grounding_opinion.sql"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if detail and not ok else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


print("== Статический уровень ==")

sql = MIGRATION.read_text("utf-8") if MIGRATION.exists() else ""
check("миграция 25 существует", bool(sql))

check(
    "правится именно qa.grounding",
    "key = 'qa.grounding'" in sql,
    "миграция не адресована судье grounding",
)
check(
    "миграция идемпотентна по маркеру",
    "template NOT LIKE '%Где проходит граница%'" in sql,
    "повторный прогон допишет границу второй раз — промпт станет противоречить сам себе",
)
check(
    "названо, что бракуется",
    "которых в материале нет вовсе" in sql and "привязывает реальную деталь к таймкоду" in sql,
    "проверка на выдумку размыта — правка превратилась бы в отключение судьи",
)

# Обе стороны границы обязаны быть перечнем, а не пожеланием: «будь мягче»
# нечего проверить и нечего оспорить.
for phrase in ("оценка и мнение", "пересказ своими словами", "упрощение без искажения"):
    check(f"названо, что законно: «{phrase}»", phrase in sql,
          "сторона «ok» не перечислена — судья снова забракует оценочную речь")

check(
    "рассуждение судьи не идёт в отчёт",
    "Не клади туда" in sql and "рассуждение" in sql,
    "цепочка размышлений судьи попадала в поле hallucinations и уезжала в отчёт "
    "человеку — целыми абзацами самоспора",
)

print()
print("== Поведенческий уровень ==")

CASES = [
    "мнение о материале судья пропускает",
    "выдуманный факт судья бракует",
]

missing = _harness.worker_deps_missing("openai")
if missing:
    for case in CASES:
        skip(case, missing)
elif not os.environ.get("OPENAI_API_KEY"):
    for case in CASES:
        skip(case, "нет OPENAI_API_KEY — судья не поднимется")
else:
    sys.path.insert(0, str(REPO / "services" / "agent-core"))
    from agent_core.config import ModelConfig
    from agent_core.qa.judge import QwenJudgeClient

    PACK = {
        "duration_sec": 42.0,
        "timeline": [
            {"time": "0:00–0:20", "scene": "Мужчина у доски рассказывает о запуске стартапа",
             "lines": [{"text": "Он основал хедж-фонд, и через пять лет под управлением было 14 миллиардов."}]},
            {"time": "0:20–0:42", "scene": "Экран телефона с рейтингом приложений",
             "lines": [{"text": "Приложение стало номером один в AppStore в США."}]},
        ],
    }
    TEMPLATE = (
        "Проверь, что персона ссылается ТОЛЬКО на реально существующие детали.\n"
        "Материал: {{video_understanding}}\nОтвет персоны: {{persona_answer}}\n"
        "Верни JSON: {\"grounded\": <bool>, \"hallucinations\": [], "
        "\"verdict\": \"<ok|regenerate>\", \"confidence\": <0..1>}"
    )

    judge = QwenJudgeClient(config=ModelConfig.from_env(), temperature=0.0)

    opinion = {
        "verbatims": {
            "why_impression": "Цифра в 14 миллиардов выглядит как маркетинг, а не как факт.",
            "memorable_elements": "Запомнилось, как он стоит у доски и считает деньги.",
        },
        "grounding_refs": ["0:00–0:20"],
    }
    invented = {
        "verbatims": {
            "why_impression": "Зацепила сцена, где он идёт по берегу моря с собакой.",
            "memorable_elements": "Понравился разговор с матерью на кухне.",
        },
        "grounding_refs": ["0:20–0:42"],
    }

    def verdict_of(answer: dict) -> str:
        out = judge.judge(template=TEMPLATE, variables={
            "persona_answer": answer, "video_understanding": PACK,
        })
        return str(out.get("verdict") or "")

    got = verdict_of(opinion)
    check(CASES[0], got == "ok",
          f"мнение забраковано ({got}) — судья по-прежнему требует пересказа транскрипта")

    got = verdict_of(invented)
    check(CASES[1], got == "regenerate",
          f"выдуманная сцена пропущена ({got}) — граница сдвинута слишком далеко, "
          f"и проверка превратилась в декорацию")

print()
n_fail = sum(1 for _, s, _ in results if s == FAIL)
n_skip = sum(1 for _, s, _ in results if s == SKIP)
print(f"Итог: OK={len(results) - n_fail - n_skip} FAIL={n_fail} SKIP={n_skip}")
if n_fail:
    print("\nНевыполненные условия:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  · {name}" + (f" — {detail}" if detail else ""))
sys.exit(1 if n_fail else 0)
