#!/usr/bin/env python3
"""
CDD-тест задачи #19 — «QA-агент».

CDD (из tasks.json):
  подсаженный заведомо несогласованный ответ ловится;
  подсаженный выдуманный таймкод (вне длительности видео) ловится;
  ложноположительных на чистом наборе нет;
  каждый вердикт содержит confidence;
  при незаданном QA_ESCALATION_AGENT_ID прогон завершается успешно и эскалаций ноль;
  при заданном — эскалируются только ответы ниже порога.

─── Два слоя проверки, и они проверяются по-разному ──────────────────────────
QA у нас двухслойный, и это не украшение архитектуры, а следствие того, чем
подсаженные дефекты отличаются друг от друга.

Выдуманный таймкод — вопрос арифметики: ролик длится 100 секунд, ссылка ведёт
на 07:45, и никакой модели, чтобы это увидеть, не нужно. То же с внутренним
противоречием ответа: «десять из десяти» рядом с «выключил бы на второй минуте»
противоречиво независимо от того, что это за ролик. Такие дефекты ловит слой
детерминированных правил, и он обязан работать всегда — без ключа провайдера,
без сети, на ноутбуке.

Согласованность ответа с ХАРАКТЕРОМ персоны (пацифист в восторге от сцены
насилия) арифметикой не ловится. Это слой LLM-as-judge, и на поддельном судье
он не проверяется по существу: судья вернёт то, что в него заложили.

Поэтому проверок здесь три группы. Правила — всегда и полностью. Обвязка судьи
(сборка промптов, разбор confidence, политика эскалации) — на поддельном судье,
тоже всегда: это наш код, а не поведение модели. Сами суждения модели — только
при заданном OPENAI_API_KEY, по явному условию.

─── Почему правило важнее вердикта судьи ─────────────────────────────────────
Порядок слоёв здесь имеет значение и проверяется отдельно: если правило нашло
противоречие, к судье вопрос уже не идёт, и «ok» от судьи ничего не отменяет.
Обратный порядок означал бы, что арифметически доказанный дефект можно замять
мнением модели — и что за каждый такой ответ мы ещё и платим.

─── Почему QA не оценивает сам себя ──────────────────────────────────────────
Приёмка требует, чтобы QA-агент верифицировался подсадкой. Отсюда проверка,
которой на первый взгляд нет в CDD: вердикт QA не должен попадать во вход
следующего вызова судьи. Судья, видящий прежние вердикты, согласуется с ними, а
не с материалом, и набор быстро приходит к одному мнению — при этом метрика
qa_catches_injected остаётся зелёной, потому что подсадку он всё ещё ловит.
Проверяется тем же приёмом, что изоляция персон в #18: маркер в ответе судьи и
поиск этого маркера по всем последующим промптам.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "services" / "agent-core"
PROMPTS = REPO / "prompts"
#: Артефакт пишется во временный каталог по той же причине, что в тесте #18:
#: настоящий evals/artifacts/ читает check.py как результат ПРОГОНА, и фикстура,
#: положенная туда тестом, сделала бы метрику зелёной без прогона.
ARTIFACT = Path(tempfile.mkdtemp(prefix="agora19-")) / "qa_report.json"

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
# ═══════════════════════════════════════════════════════════════════════════

DURATION = 100.0

PACK = {
    "form": "compact",
    "title": "Ролик",
    "duration_sec": DURATION,
    "stitched": False,
    "timeline": [
        {"start": 0.0, "end": 50.0, "scene": "Двое спорят на кухне",
         "mood": "конфликт", "lines": []},
        {"start": 50.0, "end": 100.0, "scene": "Герой уходит под дождём",
         "mood": "грусть", "lines": []},
    ],
    "scenes": [
        {"timestamp_sec": 0.0, "scene_description": "Двое спорят на кухне"},
        {"timestamp_sec": 50.0, "scene_description": "Герой уходит под дождём"},
    ],
}

SURVEY = {"questions": [
    {"id": "q1", "type": "scale", "text": "Насколько понравилось?"},
    {"id": "q2", "type": "open", "text": "Что запомнилось?"},
]}

#: Вербатимы намеренно разные: одинаковые дали бы mode collapse на чистом
#: наборе, и проверка «ложноположительных нет» падала бы по делу — на дефекте
#: фикстуры, который читался бы как дефект QA.
CLEAN_VERBATIMS = [
    ("Зацепил спор на кухне, очень живо сыграно", "Разбитая посуда", "Герой раздражает"),
    ("Скучновато, бросил бы на середине", "Дождь в финале", "Героиня убедительна"),
    ("Красивая картинка, но сюжет провисает", "Тишина после ссоры", "Оба неприятны"),
    ("Не мой жанр совсем", "Крупный план в конце", "Никто не запомнился"),
    ("Неожиданно тронуло, хотя ждал банальности", "Уход под дождём", "Герою сочувствую"),
]


def answer(
    idx: int,
    *,
    overall: int | None = None,
    nps: int | None = None,
    retention: str | None = None,
    refs: list[str] | None = None,
    marker: str | None = None,
) -> dict:
    """Один ответ персоны в формате prompts/respondent.user.md."""
    why, memorable, characters = CLEAN_VERBATIMS[idx % len(CLEAN_VERBATIMS)]
    score = overall if overall is not None else (4 + idx)
    return {
        "persona_id": f"p{idx}",
        "persona_name": f"Персона {idx}",
        "replication": 0,
        "answer": {
            "scores": {
                "overall_impression": score,
                "plot": max(1, min(10, score - 1)),
                "acting": max(1, min(10, score + 1)),
                "music": max(1, min(10, score)),
                "cinematography": max(1, min(10, score)),
            },
            "perception": {
                "interest_level": "скорее интересен",
                "emotions_evoked": ["интерес"],
                "idea_comprehension": "понятно",
                "realism_perception": "скорее реалистичные",
                "retention_intent": retention or (
                    "скорее досмотреть" if score >= 5 else "скорее выключить"
                ),
                "recommendation_nps_1_to_10": nps if nps is not None else score,
            },
            "survey_answers": {"q1": score, "q2": memorable},
            "verbatims": {
                "why_impression": f"{why} {marker or ''}".strip(),
                "memorable_elements": memorable,
                "character_opinions": characters,
            },
            "grounding_refs": refs if refs is not None else [
                "00:10 спор на кухне", "01:20 герой уходит под дождём",
            ],
        },
    }


def persona(idx: int) -> dict:
    return {
        "id": f"p{idx}",
        "name": f"Персона {idx}",
        "dna": {
            "demographics": {"age_group": "25-34", "geo": "столицы"},
            "values_and_beliefs": {"important_values": ["Семья"]},
            "narrative": f"Портрет персоны номер {idx}.",
        },
    }


PEOPLE = [persona(i) for i in range(5)]
CLEAN = [answer(i) for i in range(5)]

#: Подсадка 1 — внутреннее противоречие. Десятка за впечатление и десятка за
#: рекомендацию рядом с «выключил бы»: несогласованность видна в самом ответе,
#: без модели и без знания материала.
POISON_INCONSISTENT = answer(0, overall=10, nps=10, retention="выключил бы")
POISON_INCONSISTENT["persona_id"] = "bad-consistency"
POISON_INCONSISTENT["persona_name"] = "Персона несогласованная"

#: Подсадка 2 — выдуманный таймкод. Ролик длится 100 секунд, ссылка ведёт на
#: 07:45. Это арифметика, а не суждение.
POISON_TIMECODE = answer(1, refs=["07:45 сцена в лесу", "00:20 спор на кухне"])
POISON_TIMECODE["persona_id"] = "bad-grounding"
POISON_TIMECODE["persona_name"] = "Персона выдумавшая"


# ═══════════════════════════════════════════════════════════════════════════
# СТАТИЧЕСКИЙ УРОВЕНЬ
# ═══════════════════════════════════════════════════════════════════════════

print("== Статический уровень ==")

run_module = CORE / "agent_core" / "qa" / "run.py"
checks_module = CORE / "agent_core" / "qa" / "checks.py"
check("модуль QA-агента существует", run_module.is_file(),
      "нет services/agent-core/agent_core/qa/run.py")
check("детерминированные правила выделены отдельно", checks_module.is_file(),
      "нет agent_core/qa/checks.py — правила не должны жить внутри обвязки судьи")

for name in ("qa.consistency", "qa.grounding", "qa.diversity"):
    path = PROMPTS / f"{name}.md"
    text = path.read_text("utf-8") if path.is_file() else ""
    check(f"промпт {name} требует confidence в ответе", "confidence" in text,
          f"в {path.name} нет поля confidence — вердикт без него не выполняет приёмку")


# ═══════════════════════════════════════════════════════════════════════════
# СЛОЙ ПРАВИЛ — работает без модели и без сети
# ═══════════════════════════════════════════════════════════════════════════

print("== Правила (без модели) ==")

RULE_CASES = [
    "подсаженный несогласованный ответ пойман",
    "подсаженный выдуманный таймкод пойман",
    "на чистом наборе ложноположительных нет",
    "каждый вердикт содержит confidence",
    "вердикт каждого ответа привязан к persona_id и повтору",
    "три вида проверки присутствуют: consistency, grounding, diversity",
    "вход не мутируется прогоном",
    "артефакт qa_report.json записывается",
    "без судьи прогон отмечает неполноту в degraded",
]

sys.path.insert(0, str(CORE))
run_qa = None
QaConfig = None
try:
    from agent_core.config import QaConfig
    from agent_core.qa.run import run_qa
except Exception as e:  # noqa: BLE001
    reason = f"модуль не импортируется: {type(e).__name__}: {str(e)[:70]}"
    exists = run_module.is_file()
    for n in RULE_CASES:
        skip(n, reason) if exists else check(n, False, reason)


def flags_of(outcome, persona_id: str, kind: str | None = None) -> list[dict]:
    out = [f for f in outcome.flagged if f.get("persona_id") == persona_id]
    return [f for f in out if kind is None or f.get("kind") == kind]


if run_qa is not None:
    try:
        poisoned = CLEAN + [POISON_INCONSISTENT, POISON_TIMECODE]
        before = copy.deepcopy(poisoned)

        outcome = run_qa(
            answers=poisoned, personas=PEOPLE, pack=PACK, survey=SURVEY,
            judge=None, artifact_path=ARTIFACT,
        )

        caught_consistency = flags_of(outcome, "bad-consistency", "consistency")
        check(RULE_CASES[0], bool(caught_consistency),
              "правила не отметили ответ с 10/10 и «выключил бы»")

        caught_grounding = flags_of(outcome, "bad-grounding", "grounding")
        check(RULE_CASES[1], bool(caught_grounding),
              f"таймкод 07:45 при длительности {DURATION} с не отмечен")

        false_positives = [
            f for f in outcome.flagged
            if f.get("persona_id") in {a["persona_id"] for a in CLEAN}
        ]
        check(RULE_CASES[2], not false_positives,
              f"на чистом наборе поднято флагов: {len(false_positives)} "
              f"({[f.get('kind') for f in false_positives][:4]})")

        no_conf = [v for v in outcome.verdicts if not isinstance(v.get("confidence"), (int, float))]
        check(RULE_CASES[3], not no_conf,
              f"вердиктов без числового confidence: {len(no_conf)}")

        per_answer = [v for v in outcome.verdicts if v.get("kind") in ("consistency", "grounding")]
        addressed = all(
            v.get("persona_id") and isinstance(v.get("replication"), int) for v in per_answer
        )
        check(RULE_CASES[4], addressed, "не у каждого вердикта есть persona_id и replication")

        kinds = {v.get("kind") for v in outcome.verdicts}
        check(RULE_CASES[5], {"consistency", "grounding", "diversity"} <= kinds,
              f"виды проверок в вердиктах: {sorted(k for k in kinds if k)}")

        check(RULE_CASES[6], poisoned == before, "прогон изменил входные ответы")

        check(RULE_CASES[7], ARTIFACT.is_file(), f"артефакт не записан: {ARTIFACT}")

        check(RULE_CASES[8], any("суд" in d.lower() for d in outcome.degraded),
              f"degraded={outcome.degraded} — прогон без судьи обязан сказать, "
              f"что проверены только правила")

    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        for n in RULE_CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")


# ═══════════════════════════════════════════════════════════════════════════
# ОБВЯЗКА СУДЬИ — на поддельном судье, без ключа и без денег
# ═══════════════════════════════════════════════════════════════════════════

print("== Обвязка судьи (поддельный судья) ==")

JUDGE_CASES = [
    "судья получает промпт consistency с DNA персоны и её ответом",
    "судья получает промпт grounding с материалом видео",
    "судья получает промпт diversity со всей выборкой",
    "confidence судьи попадает в вердикт",
    "вердикт судьи «regenerate» поднимает флаг",
    "правило сильнее судьи: пойманный правилом дефект судья не отменяет",
    "пойманный правилом ответ судье не отправляется",
    "вердикт QA не попадает во вход следующего вызова судьи",
]

JUDGE_MARKER = "СУДЕЙСКИЙ-МАРКЕР-914"


class RecordingJudge:
    """Записывает всё отправленное и отдаёт вердикт по заданной таблице."""

    def __init__(self, confidence: float = 0.9, verdict: str = "ok",
                 by_marker: dict[str, float] | None = None):
        self.prompts: list[tuple[str, str]] = []
        self.confidence = confidence
        self.verdict = verdict
        self.by_marker = by_marker or {}

    def complete(self, *, system: str, user: str) -> str:
        self.prompts.append((system, user))
        confidence = self.confidence
        for marker, value in self.by_marker.items():
            if marker in system or marker in user:
                confidence = value
                break
        return json.dumps({
            "verdict": self.verdict,
            "confidence": confidence,
            "flags": [f"замечание судьи {JUDGE_MARKER}"],
            "hallucinations": [],
            "consistency_score": 8,
            "grounded": True,
        }, ensure_ascii=False)


if run_qa is None:
    for n in JUDGE_CASES:
        skip(n, "модуль QA не импортируется")
else:
    try:
        judge = RecordingJudge()
        judged = run_qa(
            answers=CLEAN + [POISON_INCONSISTENT], personas=PEOPLE, pack=PACK,
            survey=SURVEY, judge=judge, artifact_path=None,
        )
        blob = "\n".join(s + u for s, u in judge.prompts)

        check(JUDGE_CASES[0],
              any("Портрет персоны номер" in u or "Портрет персоны номер" in s
                  for s, u in judge.prompts),
              "ни в одном промпте судьи нет DNA персоны")

        scene = PACK["scenes"][0]["scene_description"]
        check(JUDGE_CASES[1], scene in blob,
              f"материал видео ({scene!r}) не дошёл до судьи grounding")

        # Промпт diversity получает выборку целиком — по нему судья и видит,
        # схлопнулись ли ответы. Признак: в одном промпте вербатимы двух персон.
        together = [
            (s, u) for s, u in judge.prompts
            if CLEAN_VERBATIMS[0][0] in (s + u) and CLEAN_VERBATIMS[1][0] in (s + u)
        ]
        check(JUDGE_CASES[2], bool(together), "нет промпта, где видна вся выборка сразу")

        judged_verdicts = [v for v in judged.verdicts if v.get("source") == "judge"]
        check(JUDGE_CASES[3],
              bool(judged_verdicts) and all(v.get("confidence") == 0.9 for v in judged_verdicts),
              f"confidence судьи не дошёл до вердикта: "
              f"{[v.get('confidence') for v in judged_verdicts][:4]}")

        strict = RecordingJudge(verdict="regenerate", confidence=0.95)
        strict_out = run_qa(
            answers=CLEAN, personas=PEOPLE, pack=PACK, survey=SURVEY,
            judge=strict, artifact_path=None,
        )
        check(JUDGE_CASES[4], bool(strict_out.flagged),
              "судья сказал regenerate, а флагов нет")

        # Судья говорит «всё хорошо» на ответе, который правило уже отвергло.
        lenient = RecordingJudge(verdict="ok", confidence=1.0)
        lenient_out = run_qa(
            answers=[POISON_INCONSISTENT, POISON_TIMECODE], personas=PEOPLE, pack=PACK,
            survey=SURVEY, judge=lenient, artifact_path=None,
        )
        check(JUDGE_CASES[5],
              bool(flags_of(lenient_out, "bad-consistency"))
              and bool(flags_of(lenient_out, "bad-grounding")),
              "вердикт судьи «ok» отменил дефект, найденный правилом")

        lenient_blob = "\n".join(s + u for s, u in lenient.prompts)
        check(JUDGE_CASES[6], "07:45" not in lenient_blob,
              "ответ, забракованный правилом, всё равно ушёл судье — это оплаченный "
              "вызов за уже известный ответ")

        check(JUDGE_CASES[7], JUDGE_MARKER not in blob,
              "вердикт судьи попал во вход следующего вызова: судья согласуется "
              "с собой, а не с материалом")

    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        for n in JUDGE_CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")


# ═══════════════════════════════════════════════════════════════════════════
# ЭСКАЛАЦИЯ (Decision Log #16, PRD §14.1)
# ═══════════════════════════════════════════════════════════════════════════

print("== Эскалация ==")

ESC_CASES = [
    "QA_ESCALATION_AGENT_ID не задан: прогон завершается, эскалаций ноль",
    "QA_ESCALATION_AGENT_ID не задан: это штатный режим, а не деградация",
    "QA_ESCALATION_AGENT_ID задан: эскалируются только вердикты ниже порога",
    "эскалированный вердикт помечен и заменяет исходный",
    "вердикт правила не эскалируется: у арифметики нет неуверенности",
]

if run_qa is None or QaConfig is None:
    for n in ESC_CASES:
        skip(n, "модуль QA не импортируется")
else:
    saved = {k: os.environ.get(k) for k in ("QA_ESCALATION_AGENT_ID", "QA_ESCALATION_CONFIDENCE")}
    try:
        os.environ.pop("QA_ESCALATION_AGENT_ID", None)
        os.environ["QA_ESCALATION_CONFIDENCE"] = "0.7"

        off_judge = RecordingJudge(confidence=0.1)  # заведомо ниже порога
        off = run_qa(
            answers=CLEAN, personas=PEOPLE, pack=PACK, survey=SURVEY,
            judge=off_judge, policy=QaConfig.from_env(), artifact_path=None,
        )
        check(ESC_CASES[0], off.escalated == 0,
              f"эскалаций {off.escalated} при незаданном QA_ESCALATION_AGENT_ID")
        check(ESC_CASES[1],
              not any("эскал" in d.lower() for d in off.degraded),
              f"отсутствие эскалации записано как деградация: {off.degraded}")

        # Порог 0.7. Две персоны получают 0.4 (ниже), остальные 0.9 (выше).
        os.environ["QA_ESCALATION_AGENT_ID"] = "agent-big"
        low = {"маркер-p0": 0.4, "маркер-p1": 0.4}
        marked = [answer(i, marker=f"маркер-p{i}") for i in range(5)]
        main_judge = RecordingJudge(confidence=0.9, by_marker=low)
        big_judge = RecordingJudge(confidence=0.99)

        on = run_qa(
            answers=marked, personas=PEOPLE, pack=PACK, survey=SURVEY,
            judge=main_judge, escalation_judge=big_judge,
            policy=QaConfig.from_env(), artifact_path=None,
        )
        # Вердикт разнообразия считается по выборке целиком, его persona_id
        # пуст, и он эскалируется по своему confidence — сравнение идёт только
        # по адресуемым вердиктам, иначе None попадает в sorted вместе со
        # строками и проверка падает типом, а не существом.
        def ids(escalated: bool) -> list[str]:
            return sorted({
                v["persona_id"] for v in on.verdicts
                if v.get("persona_id") and bool(v.get("escalated")) is escalated
            })

        check(ESC_CASES[2], ids(True) == ["p0", "p1"] and ids(False) == ["p2", "p3", "p4"],
              f"эскалированы {ids(True)} (ожидались ['p0', 'p1'] — у них confidence 0.4 "
              f"при пороге 0.7), не эскалированы {ids(False)}")

        escalated_verdicts = [v for v in on.verdicts if v.get("escalated")]
        check(ESC_CASES[3],
              bool(escalated_verdicts) and all(
                  v.get("source") == "escalated" and v.get("confidence") == 0.99
                  for v in escalated_verdicts
              ),
              f"вердикт после эскалации: "
              f"{[(v.get('source'), v.get('confidence')) for v in escalated_verdicts][:4]}")

        rule_escalated = [
            v for v in on.verdicts if v.get("source") == "rule" and v.get("escalated")
        ]
        check(ESC_CASES[4], not rule_escalated,
              f"эскалировано вердиктов правил: {len(rule_escalated)}")

    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        for n in ESC_CASES:
            if not any(r[0] == n for r in results):
                check(n, False, f"{type(e).__name__}: {str(e)[:90]}")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ═══════════════════════════════════════════════════════════════════════════
# УЗЕЛ КОНВЕЙЕРА
# ═══════════════════════════════════════════════════════════════════════════

print("== Узел конвейера ==")

NODE_CASES = [
    "узел qa отрабатывает без ключа провайдера, а не отказывает",
    "узел qa возвращает qa_flags с подсаженными дефектами",
    "узел qa пишет в degraded, что судьи не было",
    "узел qa на пустом входе отказывает по существу, а не как ненаписанный этап",
]

#: Узел проверяется вызовом, а не чтением исходника. Грепом по тексту функции
#: первая редакция проверяла написание: комментарий «ValueError, а не
#: StageNotImplemented» ронял её при полностью правильном коде. Вызов же ловит
#: то, ради чего проверка заведена, и работает целиком офлайн: судья без ключа
#: не поднимается, персоны без DATABASE_URL приходят пустым списком.
try:
    from agent_core.pipeline import nodes as pipeline_nodes
    from agent_core.pipeline.state import new_state
except Exception as e:  # noqa: BLE001
    for n in NODE_CASES:
        skip(n, f"nodes.py не импортируется: {type(e).__name__}: {str(e)[:60]}")
else:
    saved_key = os.environ.pop("OPENAI_API_KEY", None)
    saved_workdir = os.environ.get("PIPELINE_WORKDIR")
    os.environ["PIPELINE_WORKDIR"] = tempfile.mkdtemp(prefix="agora19-node-")
    try:
        state = new_state(task_id="t19", tenant_id="tenant-19")
        state["persona_answers"] = CLEAN + [POISON_INCONSISTENT, POISON_TIMECODE]
        state["content_pack_compact"] = PACK
        state["survey"] = SURVEY

        update = pipeline_nodes.qa(state)
        check(NODE_CASES[0], isinstance(update, dict), f"узел вернул {type(update).__name__}")

        flags = update.get("qa_flags") or []
        flagged_ids = {f.get("persona_id") for f in flags}
        check(NODE_CASES[1], {"bad-consistency", "bad-grounding"} <= flagged_ids,
              f"в qa_flags попали {sorted(str(i) for i in flagged_ids)}")

        check(NODE_CASES[2], any("суд" in d.lower() for d in update.get("degraded") or []),
              f"degraded={update.get('degraded')}")

        try:
            pipeline_nodes.qa(new_state(task_id="t19-empty", tenant_id="tenant-19"))
            check(NODE_CASES[3], False, "пустой persona_answers не вызвал отказа")
        except pipeline_nodes.StageNotImplemented:
            check(NODE_CASES[3], False,
                  "пустой вход отказывает как ненаписанный этап — читающий лог пойдёт "
                  "искать задачу вместо отказавшего evaluate_personas")
        except ValueError:
            check(NODE_CASES[3], True)
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
#
# Безусловного пропуска здесь нет: проверка сама решает, может ли она
# выполниться. С ключом идёт в модель, без ключа пропускается по явному условию,
# и день, когда ключ появится, ничего не требует от человека.
# ═══════════════════════════════════════════════════════════════════════════

print("== Живая модель ==")

LIVE_CASES = [
    "живой судья ловит подсаженную несогласованность с профилем персоны",
    "живой судья не бракует чистый набор целиком",
]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import worker_deps_missing  # noqa: E402

# Среда проверяется раньше ключа — см. пояснение в test_task18_respondents.py.
# У судьи нехватка `openai` выглядит ещё безобиднее и оттого хуже: клиент не
# отвечает, вердикты остаются пустыми, и проверка печатает «судья не увидел
# противоречия» — то есть обвиняет модель в том, чего она не делала.
deps = worker_deps_missing("openai")
live_key = os.environ.get("OPENAI_API_KEY")
if deps:
    for n in LIVE_CASES:
        skip(n, deps)
elif not live_key:
    for n in LIVE_CASES:
        skip(n, "OPENAI_API_KEY не задан — на поддельном судье проверяется обвязка, "
                "а не суждение модели")
elif run_qa is None:
    for n in LIVE_CASES:
        skip(n, "модуль QA не импортируется")
else:
    try:
        from agent_core.qa.judge import QwenJudgeClient

        # Персона-пацифист в восторге от сцены насилия: противоречие с профилем,
        # арифметикой не обнаружимое. Ровно то, ради чего судья и заведён.
        pacifist = persona(9)
        pacifist["dna"]["values_and_beliefs"]["important_values"] = [
            "Ненасилие", "Пацифизм", "Мир любой ценой",
        ]
        pacifist["dna"]["narrative"] = (
            "Убеждённый пацифист, физически не переносит сцены агрессии и драк."
        )
        violent = answer(2, overall=10, nps=10)
        violent["persona_id"] = pacifist["id"]
        violent["persona_name"] = pacifist["name"]
        violent["answer"]["verbatims"]["why_impression"] = (
            "Восхитила драка на кухне — чем жёстче, тем лучше, обожаю насилие на экране."
        )
        violent["answer"]["perception"]["emotions_evoked"] = ["восторг", "азарт"]

        live = run_qa(
            answers=[violent], personas=[pacifist], pack=PACK, survey=SURVEY,
            judge=QwenJudgeClient(), artifact_path=None,
        )
        check(LIVE_CASES[0], bool(flags_of(live, pacifist["id"], "consistency")),
              f"судья не увидел противоречия с профилем; вердикты: "
              f"{[(v.get('kind'), v.get('verdict')) for v in live.verdicts]}")

        live_clean = run_qa(
            answers=CLEAN, personas=PEOPLE, pack=PACK, survey=SURVEY,
            judge=QwenJudgeClient(), artifact_path=None,
        )
        rejected = {f.get("persona_id") for f in live_clean.flagged}
        check(LIVE_CASES[1], len(rejected) < len(CLEAN),
              f"судья забраковал весь чистый набор ({len(rejected)} из {len(CLEAN)}) — "
              f"порог придирчивости требует калибровки")
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
