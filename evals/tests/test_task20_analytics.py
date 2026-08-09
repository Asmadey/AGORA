#!/usr/bin/env python3
"""
CDD-тест задачи #20 — «Analytics-агент (агрегат + групповой синтез)».

CDD (из tasks.json):
  агрегат считается корректно на синтетическом наборе ответов;
  при replication_count > 1 присутствуют доверительные границы (минимум
  mean + min/max/стд) и показатель стабильности между повторами;
  точки риска прекращения просмотра привязаны к таймкодам;
  каждое утверждение синтеза имеет ссылку на таймкод или цитату.

─── Арифметику считает код, а не модель ──────────────────────────────────────
Сид-промпт analytics.report просил модель вернуть `core_scores_mean`, `nps` и
`retention_rate`. Это и есть та ошибка, ради которой написан первый пункт CDD:
модель считает среднее правдоподобно и неверно, а отличить её среднее от
правильного в отчёте нечем — оба выглядят как число.

Поэтому агрегат считается в `agent_core/analytics/aggregate.py` и проверяется
здесь до последнего знака на наборе, где ответ известен заранее. Модель
получает УЖЕ посчитанные числа и делает то, чего код не умеет: связывает их в
текст, называет темы и разногласия.

─── Ссылка у каждого утверждения — проверка кода, а не просьба к модели ──────
«Каждое утверждение синтеза имеет ссылку на таймкод или цитату» нельзя оставить
пунктом промпта: промпт — это просьба, а требование, которое только просят,
выполняется через раз и незаметно. Утверждение без ссылки обязано отсеиваться
кодом, и здесь проверяется именно отсев.
"""
from __future__ import annotations

import copy
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "services" / "agent-core"
PROMPTS = REPO / "prompts"
ARTIFACT = Path(tempfile.mkdtemp(prefix="agora20-")) / "report.json"

PASS, FAIL, SKIP = "OK", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"  →  {detail}" if not ok and detail else ""))


def skip(name: str, reason: str) -> None:
    results.append((name, SKIP, reason))
    print(f"  SKIP  {name}  →  {reason}")


# ═══════════════════════════════════════════════════════════════════════════
# ФИКСТУРЫ
#
# Числа подобраны так, чтобы правильный ответ считался в уме и был записан
# рядом. Набор, где ожидаемое значение вычисляется тем же кодом, что и
# проверяемое, не проверяет ничего.
# ═══════════════════════════════════════════════════════════════════════════

DURATION = 600.0

PACK = {
    "form": "compact", "title": "Ролик", "duration_sec": DURATION,
    "timeline": [
        {"start": 0.0, "end": 300.0, "scene": "Двое спорят на кухне"},
        {"start": 300.0, "end": 600.0, "scene": "Герой уходит под дождём"},
    ],
}

#: Пять персон. overall: 9, 10, 7, 6, 3 → среднее 7.0.
#: NPS по стандартной формуле: промоутеры 9–10 (двое = 40%), детракторы 1–6
#: (двое = 40%), нейтралы 7–8 (один). NPS = 40 − 40 = 0.
#: Досмотреть намерены трое из пяти → retention_rate 60.0.
OVERALL = [9, 10, 7, 6, 3]
RETENTION = ["скорее досмотреть", "скорее досмотреть", "скорее досмотреть",
             "скорее выключить", "выключил бы"]
EMOTIONS = [["интерес"], ["интерес", "радость"], ["скука"], ["раздражение"], []]

EXPECTED_OVERALL_MEAN = 7.0
EXPECTED_NPS = 0.0
EXPECTED_RETENTION_RATE = 60.0

#: Двое, кто выключил бы, называют, где именно бросили. Оба таймкода в
#: пределах ролика — точки риска обязаны привязаться к ним.
DROP_TIMECODES = ["04:10", "04:30"]


def answer(idx: int, *, replication: int = 0, overall: int | None = None) -> dict:
    score = OVERALL[idx] if overall is None else overall
    why = f"Впечатление персоны {idx}, обоснование её словами"
    if idx >= 3:
        why = f"Бросил бы на {DROP_TIMECODES[idx - 3]}, дальше не тянет"
    return {
        "persona_id": f"p{idx}",
        "persona_name": f"Персона {idx}",
        "replication": replication,
        "answer": {
            "scores": {"overall_impression": score, "plot": score, "acting": score,
                       "music": score, "cinematography": score},
            "perception": {
                "interest_level": "скорее интересен",
                "emotions_evoked": EMOTIONS[idx],
                "idea_comprehension": "понятно",
                "realism_perception": "скорее реалистичные",
                "retention_intent": RETENTION[idx],
                "recommendation_nps_1_to_10": score,
            },
            "survey_answers": {"q1": score},
            "verbatims": {"why_impression": why,
                          "memorable_elements": f"деталь {idx}",
                          "character_opinions": f"герой {idx}"},
            "grounding_refs": ["00:10 спор на кухне"],
        },
    }


ANSWERS = [answer(i) for i in range(5)]
SURVEY = {"questions": [{"id": "q1", "type": "scale", "text": "Насколько понравилось?"}]}


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

agg_module = CORE / "agent_core" / "analytics" / "aggregate.py"
rep_module = CORE / "agent_core" / "analytics" / "report.py"
check("расчёт агрегата выделен отдельным модулем", agg_module.is_file(),
      "нет services/agent-core/agent_core/analytics/aggregate.py")
check("сборка отчёта выделена отдельно", rep_module.is_file(),
      "нет agent_core/analytics/report.py")

prompt_text = (PROMPTS / "analytics.report.md").read_text("utf-8") \
    if (PROMPTS / "analytics.report.md").is_file() else ""
check("промпт получает готовый агрегат, а не считает его",
      "{{aggregate}}" in prompt_text,
      "в analytics.report.md нет переменной {{aggregate}}: модель просят считать "
      "средние и NPS, а её арифметику в отчёте нечем отличить от правильной")
check("промпт требует ссылку у каждого утверждения",
      "таймкод" in prompt_text and "цитат" in prompt_text,
      "в analytics.report.md не сказано, что утверждение без опоры не принимается")


# ═══════════════════════════════════════════════════════════════════════════
# АГРЕГАТ — арифметика, проверяется без модели
# ═══════════════════════════════════════════════════════════════════════════

print("== Агрегат (без модели) ==")

AGG_CASES = [
    "средние по пяти критериям совпадают с посчитанными вручную",
    "NPS считается по стандартной формуле промоутеры минус детракторы",
    "ретеншн — доля намеренных досмотреть",
    "эмоциональный индекс в шкале 0–10",
    "топ-эмоции отсортированы по убыванию и с процентами",
    "ответы, забракованные QA, из агрегата исключены и посчитаны",
    "вход не мутируется расчётом",
]

sys.path.insert(0, str(CORE))
aggregate = None
try:
    from agent_core.analytics.aggregate import aggregate
except Exception as e:  # noqa: BLE001
    reason = f"модуль не импортируется: {type(e).__name__}: {str(e)[:70]}"
    for n in AGG_CASES:
        skip(n, reason) if agg_module.is_file() else check(n, False, reason)

if aggregate is not None:
    try:
        before = copy.deepcopy(ANSWERS)
        agg = aggregate(ANSWERS, survey=SURVEY)

        means = agg.get("core_scores_mean") or {}
        check(AGG_CASES[0],
              means.get("overall_impression") == EXPECTED_OVERALL_MEAN
              and means.get("plot") == EXPECTED_OVERALL_MEAN,
              f"overall_impression={means.get('overall_impression')}, "
              f"ожидалось {EXPECTED_OVERALL_MEAN}")

        check(AGG_CASES[1], agg.get("nps") == EXPECTED_NPS,
              f"nps={agg.get('nps')}, ожидался {EXPECTED_NPS} "
              f"(промоутеры 9–10: двое, детракторы 1–6: двое из пяти)")

        check(AGG_CASES[2], agg.get("retention_rate") == EXPECTED_RETENTION_RATE,
              f"retention_rate={agg.get('retention_rate')}, "
              f"ожидался {EXPECTED_RETENTION_RATE}")

        ei = agg.get("emotional_index")
        check(AGG_CASES[3], isinstance(ei, (int, float)) and 0.0 <= ei <= 10.0,
              f"emotional_index={ei}")

        top = agg.get("top_emotions") or []
        pcts = [e.get("pct") for e in top if isinstance(e, dict)]
        check(AGG_CASES[4],
              bool(top) and pcts == sorted(pcts, reverse=True)
              and all(isinstance(p, (int, float)) for p in pcts),
              f"top_emotions={top[:3]}")

        # Забракованный QA ответ в агрегат не идёт: отчёт, построенный на
        # ответах, которые сам же пометил на перегенерацию, противоречит себе.
        flags = [{"kind": "grounding", "persona_id": "p1", "replication": 0,
                  "verdict": "regenerate"}]
        filtered = aggregate(ANSWERS, survey=SURVEY, qa_flags=flags)
        expected_wo_p1 = round(statistics.fmean([9, 7, 6, 3]), 4)
        check(AGG_CASES[5],
              (filtered.get("core_scores_mean") or {}).get("overall_impression")
              == expected_wo_p1 and filtered.get("excluded_by_qa") == 1,
              f"среднее без p1={(filtered.get('core_scores_mean') or {}).get('overall_impression')}"
              f" (ожидалось {expected_wo_p1}), исключено {filtered.get('excluded_by_qa')}")

        check(AGG_CASES[6], ANSWERS == before, "расчёт изменил входные ответы")
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        for n in AGG_CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")


# ═══════════════════════════════════════════════════════════════════════════
# ПОВТОРЫ: доверительные границы и стабильность
# ═══════════════════════════════════════════════════════════════════════════

print("== Повторы (Перекрытие) ==")

REP_CASES = [
    "при повторах у каждой персоны есть mean, min, max и стандартное отклонение",
    "показатель стабильности между повторами присутствует и лежит в 0..1",
    "без повторов границы не выдумываются, а отсутствуют явно",
    "разошедшиеся повторы дают стабильность ниже, чем совпавшие",
]

if aggregate is None:
    for n in REP_CASES:
        skip(n, "модуль агрегата не импортируется")
else:
    try:
        # Персона 0 отвечает трижды: 9, 9, 9 — совпали. Персона 1: 10, 4, 7 —
        # разошлись. Разброс собственных ответов персоны и есть то, ради чего
        # заведено «Перекрытие» (#11): он показывает, сколько в оценке шума
        # модели, а сколько позиции персоны.
        stable = [answer(0, replication=r, overall=9) for r in range(3)]
        shaky = [answer(1, replication=r, overall=v) for r, v in enumerate((10, 4, 7))]

        agg_rep = aggregate(stable + shaky, survey=SURVEY, replication_count=3)
        per_persona = agg_rep.get("per_persona") or {}
        p0 = per_persona.get("p0") or {}
        bounds = p0.get("overall_impression") or {}
        check(REP_CASES[0],
              all(k in bounds for k in ("mean", "min", "max", "stdev")),
              f"границы персоны p0: {sorted(bounds)}")

        stability = agg_rep.get("replication_stability")
        check(REP_CASES[1],
              isinstance(stability, (int, float)) and 0.0 <= stability <= 1.0,
              f"replication_stability={stability}")

        agg_single = aggregate(ANSWERS, survey=SURVEY, replication_count=1)
        check(REP_CASES[2],
              agg_single.get("replication_stability") is None
              and not agg_single.get("per_persona"),
              f"без повторов вернулись границы: stability="
              f"{agg_single.get('replication_stability')}")

        only_stable = aggregate(stable, survey=SURVEY, replication_count=3)
        only_shaky = aggregate(shaky, survey=SURVEY, replication_count=3)
        check(REP_CASES[3],
              only_shaky["replication_stability"] < only_stable["replication_stability"],
              f"совпавшие {only_stable.get('replication_stability')} против "
              f"разошедшихся {only_shaky.get('replication_stability')}")
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        for n in REP_CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")


# ═══════════════════════════════════════════════════════════════════════════
# ТОЧКИ РИСКА
# ═══════════════════════════════════════════════════════════════════════════

print("== Точки риска прекращения просмотра ==")

RISK_CASES = [
    "точки риска привязаны к таймкодам из ответов",
    "у точки риска есть число персон, которые её назвали",
    "таймкод за пределами ролика в точку риска не попадает",
]

risk_points = None
try:
    from agent_core.analytics.aggregate import retention_risk_points as risk_points
except Exception as e:  # noqa: BLE001
    reason = f"нет retention_risk_points: {type(e).__name__}: {str(e)[:60]}"
    for n in RISK_CASES:
        skip(n, reason) if agg_module.is_file() else check(n, False, reason)

if risk_points is not None:
    try:
        points = risk_points(ANSWERS, pack=PACK)
        seconds = sorted(p.get("timestamp_sec") for p in points)
        check(RISK_CASES[0], seconds == [250.0, 270.0],
              f"точки риска на {seconds}, ожидались [250.0, 270.0] "
              f"(04:10 и 04:30 у двоих, кто выключил бы)")

        check(RISK_CASES[1], all(isinstance(p.get("personas"), int) for p in points),
              f"точки без счётчика персон: {points[:2]}")

        far = copy.deepcopy(ANSWERS)
        far[3]["answer"]["verbatims"]["why_impression"] = "Бросил бы на 47:00"
        beyond = risk_points(far, pack=PACK)
        check(RISK_CASES[2],
              all(p.get("timestamp_sec", 0) <= DURATION for p in beyond),
              f"таймкод вне ролика попал в точки риска: {beyond}")
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        for n in RISK_CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")


# ═══════════════════════════════════════════════════════════════════════════
# СИНТЕЗ — на поддельной модели
# ═══════════════════════════════════════════════════════════════════════════

print("== Синтез (поддельная модель) ==")

SYN_CASES = [
    "модель получает уже посчитанный агрегат",
    "утверждение без ссылки на таймкод или цитату отсеивается",
    "утверждение с таймкодом остаётся",
    "утверждение с цитатой персоны остаётся",
    "отчёт несёт дисклеймер «требует экспертной проверки»",
    "отчёт сообщает, на скольких ответах он построен",
    "без модели агрегат всё равно собирается, а нарратив помечен отсутствующим",
    "артефакт report.json записывается",
]

build_report = None
try:
    from agent_core.analytics.report import build_report
except Exception as e:  # noqa: BLE001
    reason = f"модуль не импортируется: {type(e).__name__}: {str(e)[:70]}"
    for n in SYN_CASES:
        skip(n, reason) if rep_module.is_file() else check(n, False, reason)


class RecordingModel:
    """Возвращает синтез, где часть утверждений без опоры — их обязан отсеять код."""

    def __init__(self, narrative: list[str] | None = None):
        self.prompts: list[tuple[str, str]] = []
        self.narrative = narrative

    def complete(self, *, system: str, user: str) -> str:
        self.prompts.append((system, user))
        return json.dumps({
            "narrative": self.narrative if self.narrative is not None else [
                "Ролик держит внимание до 04:10, дальше часть зрителей отваливается.",
                "Персона 4 говорит: «Бросил бы на 04:30, дальше не тянет».",
                "Аудитория в целом настроена положительно.",
            ],
            "themes": [{"theme": "спор на кухне", "agreement": "высокое"}],
            "disagreements": ["оценка героя расходится"],
            "strengths": ["живой конфликт на 00:10"],
            "weaknesses": ["провисание после 04:10"],
        }, ensure_ascii=False)


if build_report is not None:
    try:
        model = RecordingModel()
        report = build_report(
            answers=ANSWERS, pack=PACK, survey=SURVEY, qa_flags=[],
            model=model, artifact_path=ARTIFACT,
        )

        blob = "\n".join(s + u for s, u in model.prompts)
        check(SYN_CASES[0], str(EXPECTED_OVERALL_MEAN) in blob,
              "посчитанный агрегат не дошёл до модели")

        narrative = report.get("narrative") or []
        check(SYN_CASES[1],
              not any("настроена положительно" in s for s in narrative),
              f"утверждение без опоры осталось в нарративе: {narrative}")
        check(SYN_CASES[2], any("04:10" in s for s in narrative),
              f"утверждение с таймкодом пропало: {narrative}")
        check(SYN_CASES[3], any("«" in s for s in narrative),
              f"утверждение с цитатой пропало: {narrative}")

        check(SYN_CASES[4],
              "экспертной проверки" in str(report.get("disclaimer", "")),
              f"disclaimer={report.get('disclaimer')!r}")

        check(SYN_CASES[5], report.get("based_on_answers") == len(ANSWERS),
              f"based_on_answers={report.get('based_on_answers')}, "
              f"ответов {len(ANSWERS)}")

        offline = build_report(
            answers=ANSWERS, pack=PACK, survey=SURVEY, qa_flags=[],
            model=None, artifact_path=None,
        )
        check(SYN_CASES[6],
              bool(offline.get("aggregate"))
              and any("нарратив" in d.lower() for d in offline.get("degraded") or []),
              f"degraded={offline.get('degraded')}")

        check(SYN_CASES[7], ARTIFACT.is_file(), f"артефакт не записан: {ARTIFACT}")
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        for n in SYN_CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")


# ═══════════════════════════════════════════════════════════════════════════
# УЗЕЛ КОНВЕЙЕРА
# ═══════════════════════════════════════════════════════════════════════════

print("== Узел конвейера ==")

NODE_CASES = [
    "узел analytics отрабатывает без ключа провайдера",
    "узел analytics кладёт report в состояние",
    "узел analytics на пустом входе отказывает по существу",
]

try:
    from agent_core.pipeline import nodes as pipeline_nodes
    from agent_core.pipeline.state import new_state
except Exception as e:  # noqa: BLE001
    for n in NODE_CASES:
        skip(n, f"nodes.py не импортируется: {type(e).__name__}: {str(e)[:60]}")
else:
    saved_key = os.environ.pop("OPENAI_API_KEY", None)
    saved_workdir = os.environ.get("PIPELINE_WORKDIR")
    os.environ["PIPELINE_WORKDIR"] = tempfile.mkdtemp(prefix="agora20-node-")
    try:
        state = new_state(task_id="t20", tenant_id="tenant-20")
        state["persona_answers"] = ANSWERS
        state["content_pack_compact"] = PACK
        state["survey"] = SURVEY

        update = pipeline_nodes.analytics(state)
        check(NODE_CASES[0], isinstance(update, dict), f"узел вернул {type(update).__name__}")

        report = update.get("report") or {}
        check(NODE_CASES[1],
              bool((report.get("aggregate") or {}).get("core_scores_mean")),
              f"report={sorted(report)}")

        try:
            pipeline_nodes.analytics(new_state(task_id="t20-empty", tenant_id="tenant-20"))
            check(NODE_CASES[2], False, "пустой persona_answers не вызвал отказа")
        except pipeline_nodes.StageNotImplemented:
            check(NODE_CASES[2], False, "пустой вход отказывает как ненаписанный этап")
        except ValueError:
            check(NODE_CASES[2], True)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        for n in NODE_CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")
    finally:
        if saved_key is not None:
            os.environ["OPENAI_API_KEY"] = saved_key
        if saved_workdir is None:
            os.environ.pop("PIPELINE_WORKDIR", None)
        else:
            os.environ["PIPELINE_WORKDIR"] = saved_workdir


# ═══════════════════════════════════════════════════════════════════════════
# ЖИВАЯ МОДЕЛЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Живая модель ==")

LIVE_CASES = ["живая модель даёт нарратив, переживающий отсев по ссылкам"]

if not os.environ.get("OPENAI_API_KEY"):
    for n in LIVE_CASES:
        skip(n, "OPENAI_API_KEY не задан — на поддельной модели проверяется отсев, "
                "а не качество синтеза")
elif build_report is None:
    for n in LIVE_CASES:
        skip(n, "модуль сборки отчёта не импортируется")
else:
    try:
        from agent_core.analytics.report import QwenAnalystClient

        live = build_report(
            answers=ANSWERS, pack=PACK, survey=SURVEY, qa_flags=[],
            model=QwenAnalystClient(), artifact_path=None,
        )
        check(LIVE_CASES[0], bool(live.get("narrative")),
              f"после отсева нарратив пуст; degraded={live.get('degraded')}")
    except Exception as e:  # noqa: BLE001
        check(LIVE_CASES[0], False, f"{type(e).__name__}: {str(e)[:120]}")


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
