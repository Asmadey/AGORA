"""
Расчёты по анкете заказчика: Приложение 2, посчитанное кодом.

─── Почему кодом, а не моделью ──────────────────────────────────────────────
По той же причине, по которой кодом считается `aggregate.py`: модель считает
среднее правдоподобно и неверно, и в отчёте её среднее ничем не отличается от
правильного — оба выглядят как число. Здесь та же арифметика, только по
пятнадцати вопросам вместо пяти критериев.

─── Почему отдельный модуль, а не строки в aggregate.py ─────────────────────
`aggregate.py` считает то, что было в системе до заказчика: пять критериев,
NPS, ретеншн, эмоциональный индекс, посегментный срез. Он стоит на фиксированной
схеме ответа. Здесь считается ПРОИЗВОЛЬНАЯ анкета — по одному редьюсеру на тип
вопроса, — и смешивать эти две вещи значило бы получить файл, в котором ни одна
из них не читается.

─── Один механизм среза, а не копипаста ─────────────────────────────────────
Заказчик требует колонку «14–35 лет» у КАЖДОГО показателя. Написать это
копированием значило бы удваивать каждую формулу и расходиться в половине из
них при первой же правке. Поэтому срез — это фильтр по персонам, а весь
подсчёт вызывается дважды. Следующий запрошенный срез (пол, город, гео) будет
стоить одной строки.

─── Порог и состав аудитории — разные вещи ──────────────────────────────────
Доля по группе из пяти человек шагает по двадцать процентных пунктов и выглядит
на экране ровно так же, как доля по сотне. Поэтому доли и средние в срезе
считаются от `min_segment` персон.

Но ОПИСАНИЕ состава аудитории порога не имеет: заказчик прямо требует разрез по
городам, а городов в корпусе семь, и при сотне персон в каждом около
четырнадцати. Порог, осмысленный для сравнения средних, здесь уничтожил бы само
требование. Поэтому `audience` считается всегда и целиком.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Iterable
from typing import Any

from ..survey import parse_field_answer, question_rows, survey_questions
from .aggregate import surviving

#: Целевая аудитория заказчика. Границы включительные.
#:
#: Считается по ТОЧНОМУ возрасту, а не по возрастной группе: группы корпуса —
#: 14-17, 18-24, 25-34, 35-44, 45-59, 60+ — и граница 35 режет `35-44` пополам.
#: По группам срез либо потерял бы тридцатипятилетних, либо прихватил
#: сорокалетних, и в обоих случаях число выглядело бы правильным.
TARGET_AGE = (14, 35)

#: Верхние баллы — «топ-бокс» заказчика: «доля респондентов, которые поставили
#: от 8 до 10 баллов».
TOP_BOX_MIN = 8

#: Границы NPS дословно по требованиям: промоутеры 9–10, детракторы 0–6.
NPS_PROMOTER_MIN = 9
NPS_DETRACTOR_MAX = 6

#: Пять критериев, по которым считается интегральный индекс удовлетворённости.
SATISFACTION_KEYS = ("plot", "acting", "cinematography", "music", "overall_impression")

#: Вариант вопроса 9, доля которого входит в интегральный показатель восприятия.
RAISED_OPTION = "m-1"


def _age(persona: dict[str, Any]) -> int | None:
    value = ((persona.get("dna") or {}).get("demographics") or {}).get("age")
    return value if isinstance(value, int) else None


def _demographic(persona: dict[str, Any], key: str) -> str:
    value = ((persona.get("dna") or {}).get("demographics") or {}).get(key)
    return str(value) if value else "не указано"


def in_target(persona: dict[str, Any]) -> bool:
    age = _age(persona)
    return age is not None and TARGET_AGE[0] <= age <= TARGET_AGE[1]


def _answers_of(answer: dict[str, Any]) -> dict[str, Any]:
    body = answer.get("answer") if isinstance(answer.get("answer"), dict) else answer
    raw = body.get("survey_answers")
    if isinstance(raw, dict):
        return raw
    out: dict[str, Any] = {}
    for pair in raw or []:
        if isinstance(pair, dict):
            key = str(pair.get("question") or "").strip()
            if key:
                out[key] = pair.get("answer")
    return out


# ─── Редьюсеры по типу вопроса ───────────────────────────────────────────────


def _scale(question: dict[str, Any], raw_values: Iterable[Any]) -> dict[str, Any]:
    values: list[int] = []
    for raw in raw_values:
        parsed = parse_field_answer(question, raw)
        if parsed.value is not None:
            values.append(parsed.value)
    if not values:
        return {"n": 0, "mean": None, "top_box": None, "distribution": {}, "groups": {}}

    top = sum(1 for v in values if v >= TOP_BOX_MIN) / len(values)
    distribution = {v: values.count(v) for v in sorted(set(values))}
    groups = {
        "9-10": sum(1 for v in values if v >= NPS_PROMOTER_MIN) / len(values),
        "7-8": sum(1 for v in values if 7 <= v <= 8) / len(values),
        "0-6": sum(1 for v in values if v <= NPS_DETRACTOR_MAX) / len(values),
    }
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 2),
        "top_box": round(top, 4),
        "distribution": distribution,
        "groups": groups,
    }


def _choice(question: dict[str, Any], raw_values: Iterable[Any]) -> dict[str, Any]:
    """
    Доли по вариантам.

    Знаменатель — число ОТВЕТИВШИХ персон, как подписано у заказчика
    («в % от опрошенных»), а не число выборов. При мультивыборе сумма долей
    поэтому больше единицы, и это не ошибка: персона называет до трёх эмоций.

    Невыбранный вариант получает ноль, а не исчезает из результата. Исчезнувшая
    строка на графике читается как «такого варианта не предлагали».
    """
    option_ids = [str(o.get("id")) for o in (question.get("options") or [])]
    counts = dict.fromkeys(option_ids, 0)
    answered = 0
    errors = 0
    for raw in raw_values:
        parsed = parse_field_answer(question, raw)
        if parsed.error:
            # Нарушение формы — не мнение. Персона, назвавшая два варианта там,
            # где разрешён один, не сказала «оба»: она не выполнила правило, и
            # какой из двух она имела в виду, не знает никто.
            #
            # Прежде такой ответ считался целиком: `errors` рос, но росли и оба
            # счётчика, и обе доли выходили по 100 %. На графике это выглядит
            # единодушием аудитории — то есть ошибка формы превращалась в
            # уверенный вывод.
            #
            # Счётчик остаётся: выброшенное должно быть ВИДНО, иначе доля
            # посчитается по трём ответам из двадцати и будет выглядеть так же
            # уверенно.
            errors += 1
            continue
        if not parsed.option_ids:
            continue
        answered += 1
        for oid in parsed.option_ids:
            if oid in counts:
                counts[oid] += 1
    shares = {
        oid: (round(counts[oid] / answered, 4) if answered else 0.0) for oid in option_ids
    }
    return {"n": answered, "counts": counts, "shares": shares, "errors": errors}


def _matrix(
    question: dict[str, Any], by_field: dict[str, list[Any]]
) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for row in question_rows(question):
        rid = str(row.get("id"))
        stats = _choice(question, by_field.get(rid, []))
        stats["themeId"] = row.get("themeId")
        rows[rid] = stats
    answered = max((r["n"] for r in rows.values()), default=0)
    return {"n": answered, "rows": rows}


def _open(_question: dict[str, Any], raw_values: Iterable[Any]) -> dict[str, Any]:
    texts = [str(v).strip() for v in raw_values if str(v or "").strip()]
    return {"n": len(texts), "texts": texts}


# ─── Интегральные показатели ─────────────────────────────────────────────────


def _satisfaction(questions: list[dict[str, Any]], per_question: dict[str, Any]) -> float | None:
    """
    Среднее арифметическое долей 8–10 по пяти критериям.

    При неполном наборе не считается вовсе. Среднее по четырём параметрам из
    пяти выглядит как среднее по пяти, и отличить их в отчёте нечем.
    """
    shares: list[float] = []
    found: set[str] = set()
    for q in questions:
        key = q.get("baseKey")
        if key not in SATISFACTION_KEYS:
            continue
        found.add(str(key))
        stats = per_question.get(str(q.get("id")), {})
        top = stats.get("top_box")
        if top is None:
            return None
        shares.append(top)
    if found != set(SATISFACTION_KEYS):
        return None
    return round(statistics.mean(shares), 4)


def _perception(questions: list[dict[str, Any]], per_question: dict[str, Any]) -> float | None:
    """
    Максимум доли «скорее поднималась» внутри темы, усреднённый по темам.

    Чтение формулы заказчика: «среднее арифметическое доли максимальных
    показателей "Скорее эта тема поднималась" по всем приоритетам, которые были
    заданы в анкете». Приоритет — тема, поэтому максимум берётся по её
    подтемам.

    Именно поэтому оператор выбирает темами, а не строками: при частичном
    выборе подтем максимум считался бы по разному их числу, и два прогона стали
    бы несравнимы по этому показателю.
    """
    tops: list[float] = []
    for q in questions:
        if str(q.get("type")) != "matrix_single" or not q.get("themes"):
            continue
        rows = (per_question.get(str(q.get("id"))) or {}).get("rows") or {}
        by_theme: dict[str, list[float]] = {}
        for stats in rows.values():
            theme = str(stats.get("themeId") or "")
            share = (stats.get("shares") or {}).get(RAISED_OPTION)
            if theme and share is not None and stats.get("n"):
                by_theme.setdefault(theme, []).append(share)
        tops.extend(max(v) for v in by_theme.values() if v)
    if not tops:
        return None
    return round(statistics.mean(tops), 4)


def _nps(questions: list[dict[str, Any]], per_question: dict[str, Any]) -> float | None:
    for q in questions:
        if q.get("number") != 15:
            continue
        groups = (per_question.get(str(q.get("id"))) or {}).get("groups") or {}
        if not groups:
            return None
        return round(groups["9-10"] - groups["0-6"], 4)
    return None


# ─── Сборка ──────────────────────────────────────────────────────────────────


def _tally_scope(
    questions: list[dict[str, Any]], answers: list[dict[str, Any]], base: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Подсчёт по одному охвату.

    `base` — сколько персон в охвате опрашивали. Он кладётся рядом с `n` в
    каждый результат намеренно: заказчик подписывает доли «в % от опрошенных»,
    а считаются они от ОТВЕТИВШИХ. При полной анкете это одно и то же, при
    замеренных 40 % пропусков — расходится вдвое. Выбирать знаменатель за
    читателя нельзя, поэтому в данных стоят оба числа.
    """
    by_field: dict[str, list[Any]] = {}
    for answer in answers:
        for key, value in _answers_of(answer).items():
            by_field.setdefault(key, []).append(value)

    per_question: dict[str, Any] = {}
    for q in questions:
        qid = str(q.get("id"))
        qtype = str(q.get("type") or "open")
        if qtype == "matrix_single":
            per_question[qid] = _matrix(q, by_field)
        elif qtype == "scale":
            per_question[qid] = _scale(q, by_field.get(qid, []))
        elif qtype == "open":
            per_question[qid] = _open(q, by_field.get(qid, []))
        else:
            per_question[qid] = _choice(q, by_field.get(qid, []))

    for stats in per_question.values():
        stats["base"] = base
        for row in (stats.get("rows") or {}).values():
            row["base"] = base

    indices = {
        "satisfaction": _satisfaction(questions, per_question),
        "perception": _perception(questions, per_question),
        "nps": _nps(questions, per_question),
    }
    return per_question, indices


def _suppressed(stats: dict[str, Any], n: int) -> dict[str, Any]:
    """Срез ниже порога: числа убираются, размер остаётся."""
    out = {k: (None if k not in {"n", "base", "themeId"} else v) for k, v in stats.items()}
    out["n"] = n
    out["below_threshold"] = True
    return out


def survey_tally(
    questions: list[dict[str, Any]] | dict[str, Any],
    answers: list[dict[str, Any]],
    personas: list[dict[str, Any]],
    *,
    min_segment: int = 20,
    cut: Callable[[dict[str, Any]], bool] = in_target,
    qa_flags: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Все показатели Приложения 2 — по всей аудитории и по срезу.

    `min_segment` — порог показа долей в срезе; состав аудитории его не
    признаёт. `cut` вынесен параметром: срез 14–35 — умолчание заказчика, но
    механизм общий, и следующий разрез стоит одной строки.

    ─── Гейтинг ────────────────────────────────────────────────────────────
    Отбор выбывших делает `aggregate.surviving`, а не своя копия правила.
    Политика владельца 17.09.2026: судья информирует, детерминированные правила
    гейтят — балл вне шкалы в среднее не положишь, а субъективный вердикт судьи
    в трёх случаях из четырёх оказывался дефектом правила, а не качеством.

    Своя копия этого условия означала бы два числа в одном отчёте, посчитанные
    по разным выборкам, и разошлись бы они молча.
    """
    qs = survey_questions(questions)
    total_answers = len(answers)
    answers = surviving(list(answers), qa_flags)
    by_persona = {str(p.get("id")): p for p in personas}

    target_ids = {pid for pid, p in by_persona.items() if cut(p)}
    target_answers = [
        a for a in answers if str(a.get("persona_id")) in target_ids
    ]

    total_q, total_i = _tally_scope(qs, answers, len(personas))
    target_q, target_i = _tally_scope(qs, target_answers, len(target_ids))
    target_size = len(target_ids)
    below = target_size < min_segment

    questions_out: dict[str, Any] = {}
    for q in qs:
        qid = str(q.get("id"))
        target_stats = target_q[qid]
        questions_out[qid] = {
            "number": q.get("number"),
            "type": q.get("type"),
            "block": q.get("block"),
            "label": q.get("label"),
            "total": total_q[qid],
            "target": _suppressed(target_stats, target_size) if below else target_stats,
        }

    audience: dict[str, Any] = {
        "total": len(personas),
        "target": target_size,
        "target_range": f"{TARGET_AGE[0]}–{TARGET_AGE[1]}",
    }
    for key in ("gender", "geo", "city", "age_group"):
        counts: dict[str, int] = {}
        for p in personas:
            counts[_demographic(p, key)] = counts.get(_demographic(p, key), 0) + 1
        audience[key] = dict(sorted(counts.items()))

    return {
        "excluded_by_qa": total_answers - len(answers),
        "questions": questions_out,
        "indices": {
            name: {"total": total_i[name], "target": None if below else target_i[name]}
            for name in total_i
        },
        "audience": audience,
        "min_segment": min_segment,
    }
