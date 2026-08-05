#!/usr/bin/env python3
"""
CDD-тест задачи #18 — «Respondent-агенты (изоляция)».

CDD (из tasks.json):
  утечка контекста между персонами == 0 (маркер, подсаженный в контекст
  персоны A, не появляется у B);
  distinct-2 и дисперсия баллов выше порога — нет mode collapse.

─── Две половины, и они проверяются по-разному ───────────────────────────────
Первая половина — про структуру. Утечка контекста не зависит от того, что
ответила модель: она либо есть в отправленном промпте, либо её там нет. Это
проверяется поддельным клиентом, который записывает всё отправленное, и
проверяется ПОЛНОСТЬЮ, без среды и без денег.

Вторая половина — про поведение модели. distinct-2 и дисперсия баллов на
поддельном клиенте не значат ничего: клиент вернёт то, что в него заложили.
Поэтому проверок две. Машинка расчёта проверяется всегда и без среды: метрика
обязана считаться правильно и ловить подсунутый ей mode collapse. Сам порог
проверяется на живой модели и только при заданном OPENAI_API_KEY — проверка сама
решает, может ли она выполниться, и без ключа пропускается по явному условию.

Безусловного пропуска здесь нет намеренно. Первая редакция ставила именно его, с
честным объяснением в строке, и мета-проверка test_gates.py её отвергла — верно:
безусловный skip не отличим от проверки, которую забыли дописать, а объяснение
живёт там, где его никто не перечитывает.

Разделение не уловка. Оно ровно повторяет, чем эти два требования отличаются:
изоляция — свойство нашего кода и обязана держаться всегда; разнообразие —
свойство модели и промпта, и меняется оно при каждой правке промпта в Студии.

─── Почему маркер сажается в DNA, а не в отдельное поле ──────────────────────
Утечка, которой стоит бояться, — не «мы случайно склеили два промпта». Она
выглядит иначе: общий изменяемый объект (список messages, словарь контекста,
шаблон с подстановкой на месте), который переиспользуется между вызовами и
копит данные предыдущей персоны. Такой дефект не виден на двух персонах и
проявляется на двадцатой, причём только на второй репликации.

Поэтому маркер кладётся внутрь DNA — туда, откуда он гарантированно попадёт в
промпт, — а проверка идёт по ВСЕМ отправленным промптам всех остальных персон,
включая повторы.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "services" / "agent-core"
#: Тест пишет артефакт во ВРЕМЕННЫЙ каталог, а не в evals/artifacts/.
#: Настоящий путь читает check.py как результат прогона: положив туда фикстуру
#: из одинаковых поддельных ответов, тест сделал бы метрику response_diversity
#: красной на пустом месте — и отличить это от настоящего mode collapse было
#: бы нечем. Приёмка требует, чтобы артефакт клал ПРОГОН, а не тест.
ARTIFACT = Path(tempfile.mkdtemp(prefix="agora18-")) / "persona_answers.json"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    shown = "" if ok else detail
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {shown}" if shown else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


MARKER = "ЗЕЛЁНЫЙ-НОСОРОГ-741"


def persona(idx: int, *, marker: str | None = None) -> dict:
    dna = {
        "demographics": {
            "gender": "жен" if idx % 2 else "муж", "age": 25 + idx,
            "age_group": "25-34", "geo": "столицы",
            "city": "Москва", "children": "Нет детей",
        },
        "big_five": {"openness": 3, "conscientiousness": 3, "extraversion": 3,
                     "agreeableness": 3, "neuroticism": 3},
        "values_and_beliefs": {
            "important_values": ["Семья", marker or "Здоровье"],
            "worldview": "прагматическая", "political_orientation": "аполитичен",
            "religious_attitude": "нерелигиозен",
        },
        "viewer_behavior": {"genres": ["драма"]},
        "communication_style": {"tone": "спокойный"},
        "decision_making": {"style": "взвешенный"},
        "technology_usage": {"devices": ["смартфон"]},
        "lifestyle_and_interests": {"hobbies": ["бег"], "work_status": "работает"},
        "narrative": f"Портрет персоны номер {idx}, достаточно длинный для схемы валидации.",
        "seed": 42,
    }
    return {"id": f"p{idx}", "name": f"Персона {idx}", "dna": dna}


PACK = {
    "form": "compact", "title": "Ролик", "duration_sec": 100.0, "stitched": False,
    "timeline": [{"start": 0.0, "end": 100.0, "scene": "Двое спорят на кухне",
                  "mood": "конфликт", "lines": []}],
    "scenes": [{"timestamp_sec": 0.0, "scene_description": "Двое спорят на кухне"}],
}

SURVEY = {"questions": [
    {"id": "q1", "type": "scale", "text": "Насколько понравилось?"},
    {"id": "q2", "type": "open", "text": "Что запомнилось?"},
]}


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

module = CORE / "agent_core" / "respondent" / "run.py"
check("модуль respondent-агентов существует", module.is_file(),
      "нет services/agent-core/agent_core/respondent/run.py")

metrics = CORE / "agent_core" / "respondent" / "diversity.py"
check("расчёт разнообразия выделен отдельно", metrics.is_file(),
      "нет agent_core/respondent/diversity.py")


# ═══════════════════════════════════════════════════════════════════════════
# ПОВЕДЕНЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Изоляция (структурная) ==")

ISO_CASES = [
    "прогон возвращает ответ на каждую персону × replication_count",
    "маркер персоны A не попал ни в один промпт других персон",
    "в срезе персоны нет DNA других персон",
    "в срезе персоны нет ответов других персон",
    "в срезе есть материал видео и анкета",
    "вход не мутируется прогоном",
    "отказ модели на одной персоне не роняет прогон",
    "пачки по 5 — размер партии соблюдён",
    "артефакт persona_answers.json записывается",
]

DIV_CASES = [
    "distinct-2 считается по вербатимам",
    "mode collapse ловится: одинаковые ответы дают низкий distinct-2",
    "разнообразные ответы дают distinct-2 выше порога",
    "дисперсия баллов считается",
    "нулевая дисперсия ловится как mode collapse",
]

sys.path.insert(0, str(CORE))
run_survey = None
try:
    from agent_core.respondent.run import BATCH_SIZE, run_survey
except Exception as e:  # noqa: BLE001
    verdict = skip if module.is_file() else check
    reason = f"модуль не импортируется: {type(e).__name__}: {str(e)[:60]}"
    for n in ISO_CASES:
        verdict(n, reason) if verdict is skip else verdict(n, False, reason)

if run_survey is not None:
    class RecordingClient:
        """Записывает всё отправленное и отдаёт валидный ответ."""

        def __init__(self):
            self.prompts: list[tuple[str, str]] = []

        def complete(self, *, system: str, user: str) -> str:
            self.prompts.append((system, user))
            return json.dumps({
                "scores": {"overall_impression": 7, "plot": 6, "acting": 8,
                           "music": 5, "cinematography": 7},
                "perception": {
                    "interest_level": "скорее интересен",
                    "emotions_evoked": ["интерес"],
                    "idea_comprehension": "понятно",
                    "realism_perception": "скорее реалистичные",
                    "retention_intent": "скорее досмотреть",
                    "recommendation_nps_1_to_10": 7,
                },
                "survey_answers": {"q1": 7, "q2": "Спор на кухне"},
                "verbatims": {"why_impression": "Зацепил спор на кухне",
                              "memorable_elements": "Разбитая посуда",
                              "character_opinions": "Герой раздражает"},
                "grounding_refs": ["00:00 спор на кухне"],
            }, ensure_ascii=False)

    people = [persona(0, marker=MARKER)] + [persona(i) for i in range(1, 6)]
    import copy
    people_before = copy.deepcopy(people)

    try:
        client = RecordingClient()
        outcome = run_survey(
            personas=people, pack=PACK, survey=SURVEY,
            client=client, replication_count=2, artifact_path=ARTIFACT,
        )

        check(ISO_CASES[0], len(outcome.answers) == len(people) * 2,
              f"ответов {len(outcome.answers)}, ожидалось {len(people) * 2}")

        # ── Главная проверка cdd ────────────────────────────────────────────
        # Промпты персоны A исключаются из поиска: маркер там законно.
        others = [
            (s, u) for i, (s, u) in enumerate(client.prompts)
            if outcome.answers[i]["persona_id"] != "p0"
        ]
        leaked = [i for i, (s, u) in enumerate(others) if MARKER in s or MARKER in u]
        check(ISO_CASES[1], not leaked,
              f"маркер персоны p0 найден в {len(leaked)} промптах других персон")

        # Ни одного чужого имени в промпте — более широкая сеть, чем один маркер.
        cross = []
        for i, (s, u) in enumerate(client.prompts):
            own = outcome.answers[i]["persona_id"]
            blob = s + u
            for p in people:
                if p["id"] != own and p["name"] in blob:
                    cross.append((own, p["id"]))
        check(ISO_CASES[2], not cross, f"чужие персоны в срезе: {cross[:4]}")

        # Ответ предыдущей персоны в промпте следующей — вторая форма утечки.
        answered_marks = [a["answer"]["verbatims"]["why_impression"] for a in outcome.answers]
        echo = [
            i for i, (s, u) in enumerate(client.prompts[1:], start=1)
            if any(m and m in (s + u) for m in answered_marks[:i])
        ]
        check(ISO_CASES[3], not echo, f"ответы других персон в срезе: {len(echo)} промптов")

        # Сверяется с самими фикстурами, а не с набранной руками подстрокой:
        # первая версия искала «спор на кухне» при фикстуре «Двое спорят на
        # кухне» и падала на расхождении теста с собой, а не кода с требованием.
        first_user = client.prompts[0][1]
        scene_text = PACK["scenes"][0]["scene_description"]
        question_text = SURVEY["questions"][1]["text"]
        check(ISO_CASES[4],
              scene_text in first_user and question_text in first_user,
              f"в срезе нет материала видео ({scene_text!r}) или анкеты ({question_text!r})")

        check(ISO_CASES[5], people == people_before, "прогон изменил входные персоны")

        # ── Отказ модели ────────────────────────────────────────────────────
        class FlakyClient(RecordingClient):
            def complete(self, *, system: str, user: str) -> str:
                if len(self.prompts) == 2:
                    self.prompts.append((system, user))
                    raise RuntimeError("провайдер недоступен")
                return super().complete(system=system, user=user)

        flaky = run_survey(
            personas=people, pack=PACK, survey=SURVEY,
            client=FlakyClient(), replication_count=1, artifact_path=None,
        )
        check(ISO_CASES[6],
              len(flaky.answers) == len(people) - 1 and flaky.failures == 1,
              f"ответов {len(flaky.answers)}, отказов {flaky.failures}")

        check(ISO_CASES[7], BATCH_SIZE == 5, f"BATCH_SIZE={BATCH_SIZE}, ожидалось 5")

        check(ISO_CASES[8], ARTIFACT.is_file(), f"артефакт не записан: {ARTIFACT}")

    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        for n in ISO_CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")


print("== Разнообразие (машинка расчёта) ==")

try:
    from agent_core.respondent.diversity import (
        DISTINCT2_MIN,
        SCORE_STDEV_MIN,
        distinct_2,
        score_stdev,
    )
except Exception as e:  # noqa: BLE001
    verdict = skip if metrics.is_file() else check
    reason = f"модуль не импортируется: {type(e).__name__}: {str(e)[:60]}"
    for n in DIV_CASES:
        verdict(n, reason) if verdict is skip else verdict(n, False, reason)
else:
    varied = [
        "Зацепил спор на кухне, очень живо сыграно",
        "Скучно, ничего нового, бросил бы на середине",
        "Красивая картинка, но сюжет провисает во второй половине",
        "Герой раздражает, а вот музыка отличная",
        "Не мой жанр совсем, смотреть не стал бы",
    ]
    collapsed = ["Зацепил спор на кухне, очень живо сыграно"] * 5

    d_varied, d_collapsed = distinct_2(varied), distinct_2(collapsed)
    check(DIV_CASES[0], 0.0 <= d_varied <= 1.0, f"distinct_2={d_varied}")
    check(DIV_CASES[1], d_collapsed < DISTINCT2_MIN,
          f"на одинаковых ответах distinct_2={d_collapsed:.3f}, порог {DISTINCT2_MIN}")
    check(DIV_CASES[2], d_varied >= DISTINCT2_MIN,
          f"на разных ответах distinct_2={d_varied:.3f}, порог {DISTINCT2_MIN}")

    s_varied = score_stdev([{"overall_impression": v} for v in (3, 5, 7, 9, 6)])
    s_flat = score_stdev([{"overall_impression": 7}] * 5)
    check(DIV_CASES[3], s_varied > 0, f"stdev={s_varied}")
    check(DIV_CASES[4], s_flat < SCORE_STDEV_MIN,
          f"на одинаковых баллах stdev={s_flat:.3f}, порог {SCORE_STDEV_MIN}")

# ═══════════════════════════════════════════════════════════════════════════
# ЖИВАЯ МОДЕЛЬ
#
# Первая редакция ставила здесь два безусловных skip с честным объяснением «нет
# ключа». Мета-проверка test_gates.py их отвергла, и справедливо: безусловный
# пропуск не отличим от проверки, которую забыли дописать, а объяснение живёт в
# строке, которую никто не перечитывает.
#
# Правильная форма — проверка, которая САМА решает, может ли она выполниться. С
# ключом она идёт в модель и меряет то, что и должна; без ключа пропускается по
# явному условию. Тогда день, когда ключ появится, ничего не требует от человека.
# ═══════════════════════════════════════════════════════════════════════════

print("== Разнообразие (живая модель) ==")

LIVE_CASES = [
    "distinct-2 живой модели выше порога",
    "дисперсия баллов живой модели выше порога",
]

live_key = os.environ.get("OPENAI_API_KEY")
if not live_key:
    for n in LIVE_CASES:
        skip(n, "OPENAI_API_KEY не задан — на поддельном клиенте метрика меряет "
                "фикстуру, а не модель")
elif run_survey is None:
    for n in LIVE_CASES:
        skip(n, "модуль прогона не импортируется")
else:
    try:
        from agent_core.respondent.diversity import (
            DISTINCT2_MIN,
            SCORE_STDEV_MIN,
            diversity_report,
        )
        from agent_core.respondent.run import QwenRespondentClient

        # Восемь персон: меньше — и дисперсия считается по слишком малой выборке,
        # больше — и проверка становится заметной статьёй расхода на каждом CI.
        live_people = [persona(i) for i in range(8)]
        live = run_survey(
            personas=live_people, pack=PACK, survey=SURVEY,
            client=QwenRespondentClient(), replication_count=1, artifact_path=None,
        )
        if not live.answers:
            for n in LIVE_CASES:
                check(n, False, f"модель не дала ни одного ответа: {live.failure_reasons[:2]}")
        else:
            rep = diversity_report(live.answers)
            check(LIVE_CASES[0], rep["distinct_2"] >= DISTINCT2_MIN,
                  f"distinct-2={rep['distinct_2']:.3f} < {DISTINCT2_MIN} "
                  f"(ответов {len(live.answers)}, отказов {live.failures})")
            check(LIVE_CASES[1], rep["score_stdev"] >= SCORE_STDEV_MIN,
                  f"stdev={rep['score_stdev']:.3f} < {SCORE_STDEV_MIN} "
                  f"(ответов {len(live.answers)}, отказов {live.failures})")
    except Exception as e:  # noqa: BLE001
        for n in LIVE_CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:120]}")


# ═══════════════════════════════════════════════════════════════════════════

print()
n_fail = sum(1 for _, s, _ in results if s == FAIL)
n_skip = sum(1 for _, s, _ in results if s == SKIP)
n_ok = sum(1 for _, s, _ in results if s == PASS)
print(f"Итог: OK={n_ok} FAIL={n_fail} SKIP={n_skip}")
if n_fail:
    print("\nНевыполненные условия:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  · {name}" + (f" — {detail}" if detail else ""))
sys.exit(1 if n_fail else 0)
