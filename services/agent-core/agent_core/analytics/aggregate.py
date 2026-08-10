"""
Агрегат по ответам персон — задача #20, арифметическая часть.

Всё в этом модуле считается кодом и не спрашивается у модели. Причина та же,
по которой QA-правила (#19) стоят перед судьёй: модель считает среднее
правдоподобно и неверно, и в отчёте её среднее ничем не отличается от
правильного — оба выглядят как число. Сид-промпт analytics.report просил у
модели `core_scores_mean`, `nps` и `retention_rate`; это исправлено вместе с
этой задачей.

Модель получает то, что здесь посчитано, и делает работу, которой код не
умеет: называет темы, разногласия и связывает числа в текст.

─── Забракованные QA ответы в агрегат не идут ────────────────────────────────
Отчёт, построенный на ответах, которые сам же пометил на перегенерацию,
противоречит себе. Исключённые считаются и попадают в отчёт числом: читатель
обязан знать, на скольких ответах стоит вывод.

─── Повторы ──────────────────────────────────────────────────────────────────
`replication_count > 1` — это «Перекрытие» из #11: одна персона отвечает
несколько раз. Разброс её собственных ответов показывает, сколько в оценке
шума модели, а сколько позиции персоны, и именно поэтому границы считаются по
персоне, а не по всей выборке: разброс между разными людьми — это не шум, это
и есть результат.

При одном повторе границ нет вовсе. Вернуть mean == min == max и нулевое
отклонение было бы хуже пустоты: отчёт показал бы идеальную стабильность там,
где её просто не измеряли.
"""

from __future__ import annotations

import copy
import re
import statistics
from typing import Any

#: Пять критериев AGORA. Список закрыт схемой persona-ответа и продублирован в
#: evals/check.py — расхождение здесь означало бы, что отчёт и гейт считают
#: калибровку по разным наборам.
CRITERIA = ("overall_impression", "plot", "acting", "music", "cinematography")

#: Границы стандартной шкалы NPS в переводе на десятибалльную оценку
#: рекомендации: 9–10 промоутеры, 1–6 детракторы, 7–8 нейтралы.
NPS_PROMOTER_MIN = 9
NPS_DETRACTOR_MAX = 6

#: Сколько эмоций показывать в топе. Больше — хвост из единичных упоминаний,
#: который читается как разнообразие, хотя это шум одной персоны.
TOP_EMOTIONS = 5

#: Отклонение баллов персоны между её повторами, при котором стабильность
#: считается нулевой. Три балла из десяти — это «понравилось» и «не
#: понравилось» от одного человека на один материал.
#:
#: Значение ПРЕДВАРИТЕЛЬНОЕ: оно выбрано как половина шкалы удовлетворённости,
#: а не измерено. Калибруется на первых прогонах с replication_count = 3.
STABILITY_ZERO_STDEV = 3.0

_TIMECODE = re.compile(r"(?<![\d:])(\d{1,2}):([0-5]\d)(?::([0-5]\d))?(?![\d:])")


def _body(item: dict[str, Any]) -> dict[str, Any]:
    inner = item.get("answer")
    return inner if isinstance(inner, dict) else item


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _looks_numeric(text: str) -> bool:
    """
    Строка целиком является числом.

    Нужно отдельно от `_num`: тот принимает только настоящие числа, а из
    корпуса эмоции приходят строками, и «10» среди них — не эмоция, а подпись
    шкалы, затесавшаяся в список (data/grounding/corpus.meta.json). В топ
    эмоций такое попадать не должно: «десять» рядом с «интересом» читается как
    эмоция, которой никто не называл.
    """
    try:
        float(text.replace(",", "."))
    except ValueError:
        return False
    return True


def _flag_keys(qa_flags: list[dict[str, Any]] | None) -> set[tuple[str, int]]:
    """Адреса ответов, помеченных QA на перегенерацию."""
    out: set[tuple[str, int]] = set()
    for flag in qa_flags or []:
        if not isinstance(flag, dict) or flag.get("verdict") != "regenerate":
            continue
        persona_id = flag.get("persona_id")
        if persona_id is None:
            # Вердикт по выборке целиком (diversity) не адресует отдельный
            # ответ — исключать по нему нечего.
            continue
        out.add((str(persona_id), int(flag.get("replication") or 0)))
    return out


def surviving(
    answers: list[dict[str, Any]], qa_flags: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Ответы, не помеченные QA на перегенерацию."""
    dropped = _flag_keys(qa_flags)
    return [
        a for a in answers
        if (str(a.get("persona_id")), int(a.get("replication") or 0)) not in dropped
    ]


def aggregate(
    answers: list[dict[str, Any]],
    *,
    survey: dict[str, Any] | None = None,
    qa_flags: list[dict[str, Any]] | None = None,
    replication_count: int = 1,
) -> dict[str, Any]:
    """Числовая часть отчёта. Ничего не спрашивает у модели и ничего не меняет во входе."""
    answers = copy.deepcopy(list(answers))
    kept = surviving(answers, qa_flags)
    bodies = [_body(a) for a in kept]

    result: dict[str, Any] = {
        "core_scores_mean": _core_means(bodies),
        "nps": _nps(bodies),
        "retention_rate": _retention_rate(bodies),
        "emotional_index": _emotional_index(bodies),
        "top_emotions": _top_emotions(bodies),
        "sample_size": len(kept),
        "excluded_by_qa": len(answers) - len(kept),
        "replication_count": replication_count,
        "per_persona": {},
        "replication_stability": None,
    }
    _ = survey  # разбор ответов анкеты — задача отчёта (#21), не агрегата

    if replication_count > 1:
        result["per_persona"] = _per_persona_bounds(kept)
        result["replication_stability"] = _stability(result["per_persona"])
    return result


def _core_means(bodies: list[dict[str, Any]]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for field in CRITERIA:
        values = [
            v for v in (_num((b.get("scores") or {}).get(field)) for b in bodies)
            if v is not None
        ]
        out[field] = round(statistics.fmean(values), 4) if values else None
    return out


def _nps(bodies: list[dict[str, Any]]) -> float | None:
    """
    Стандартный NPS: доля промоутеров минус доля детракторов, в процентах.

    Считается по десятибалльной шкале рекомендации, а не по одиннадцатибалльной
    оригинальной (0–10): в анкете AGORA поле объявлено как 1..10. Границы
    сохранены классическими (9–10 и 1–6), потому что смысл в них, а не в нуле.
    """
    values = [
        v for v in (_num((b.get("perception") or {}).get("recommendation_nps_1_to_10"))
                    for b in bodies)
        if v is not None
    ]
    if not values:
        return None
    promoters = sum(1 for v in values if v >= NPS_PROMOTER_MIN)
    detractors = sum(1 for v in values if v <= NPS_DETRACTOR_MAX)
    return round((promoters - detractors) * 100.0 / len(values), 4)


def _retention_rate(bodies: list[dict[str, Any]]) -> float | None:
    """Доля намеренных досмотреть, в процентах. Затруднившиеся в числитель не идут."""
    from ..qa.checks import retention_stance

    stances = [retention_stance((b.get("perception") or {}).get("retention_intent"))
               for b in bodies]
    known = [s for s in stances if s != "unknown"]
    if not known:
        return None
    return round(sum(1 for s in known if s == "continue") * 100.0 / len(known), 4)


def _emotional_index(bodies: list[dict[str, Any]]) -> float | None:
    """
    Насколько материал вообще задел зрителя, в шкале 0–10.

    Определение здесь — решение, а не измерение, и его стоит знать читающему
    отчёт. Берётся доля персон, назвавших хотя бы одну эмоцию, умноженная на
    десять. Если же в `emotions_evoked` пришли числа — а в реальном корпусе
    туда затесались подписи шкалы «10 – вызвал очень сильные эмоции», см.
    data/grounding/corpus.meta.json, — считается их среднее: это и есть
    исходная форма показателя в корпусе, и подменять её долей значило бы
    считать по другой шкале, не сказав об этом.
    """
    numeric: list[float] = []
    mentioned = 0
    for body in bodies:
        emotions = (body.get("perception") or {}).get("emotions_evoked")
        if not isinstance(emotions, list):
            continue
        values = [_num(e) for e in emotions]
        values = [v for v in values if v is not None]
        if values:
            numeric.append(statistics.fmean(values))
        elif any(str(e).strip() for e in emotions):
            mentioned += 1
    if numeric:
        return round(min(10.0, max(0.0, statistics.fmean(numeric))), 4)
    if not bodies:
        return None
    return round(mentioned * 10.0 / len(bodies), 4)


def _top_emotions(bodies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for body in bodies:
        emotions = (body.get("perception") or {}).get("emotions_evoked")
        if not isinstance(emotions, list):
            continue
        # Внутри одного ответа эмоция считается один раз: персона, назвавшая
        # «интерес» дважды, не даёт двух наблюдений.
        for name in {str(e).strip().lower() for e in emotions if str(e).strip()}:
            if _looks_numeric(name):
                continue  # число в списке эмоций — дефект данных, не эмоция
            counts[name] = counts.get(name, 0) + 1
    if not bodies:
        return []
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [
        {"name": name, "count": count, "pct": round(count * 100.0 / len(bodies), 4)}
        for name, count in ordered[:TOP_EMOTIONS]
    ]


def _per_persona_bounds(answers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Границы разброса по каждой персоне: mean, min, max, стандартное отклонение."""
    by_persona: dict[str, list[dict[str, Any]]] = {}
    for item in answers:
        by_persona.setdefault(str(item.get("persona_id")), []).append(_body(item))

    out: dict[str, dict[str, Any]] = {}
    for persona_id, bodies in by_persona.items():
        entry: dict[str, Any] = {"replications": len(bodies)}
        for field in CRITERIA:
            values = [
                v for v in (_num((b.get("scores") or {}).get(field)) for b in bodies)
                if v is not None
            ]
            if not values:
                continue
            entry[field] = {
                "mean": round(statistics.fmean(values), 4),
                "min": min(values),
                "max": max(values),
                "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
            }
        out[persona_id] = entry
    return out


def _stability(per_persona: dict[str, dict[str, Any]]) -> float | None:
    """
    Насколько повторы одной персоны сходятся между собой: 1.0 — совпали.

    Считается по overall_impression: он единственный, который персона ставит
    всегда, и по нему же считается сводная оценка. Отклонение переводится в
    шкалу 0..1 линейно до STABILITY_ZERO_STDEV.
    """
    stdevs = [
        entry["overall_impression"]["stdev"]
        for entry in per_persona.values()
        if isinstance(entry.get("overall_impression"), dict)
        and entry.get("replications", 0) > 1
    ]
    if not stdevs:
        return None
    mean_stdev = statistics.fmean(stdevs)
    return round(max(0.0, 1.0 - mean_stdev / STABILITY_ZERO_STDEV), 4)


def retention_risk_points(
    answers: list[dict[str, Any]],
    *,
    pack: dict[str, Any] | None = None,
    qa_flags: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Где зрители бросают просмотр, с привязкой к таймкодам.

    Берутся только персоны, заявившие намерение прекратить просмотр: таймкод в
    вербатиме довольного зрителя — это отсылка к понравившейся сцене, и считать
    её точкой риска значило бы получить риск ровно там, где сильнее всего
    зацепило.

    Таймкоды за пределами ролика отбрасываются. Это тот же выдуманный таймкод,
    который ловит QA (#19); сюда он может дойти, если QA шёл без судьи и ответ
    прошёл по остальным правилам — но точкой риска выдумка быть не может.
    """
    from ..qa.checks import retention_stance

    duration = (pack or {}).get("duration_sec")
    limit = float(duration) if isinstance(duration, (int, float)) and duration > 0 else None

    counts: dict[float, set[str]] = {}
    for item in surviving(list(answers), qa_flags):
        body = _body(item)
        if retention_stance((body.get("perception") or {}).get("retention_intent")) != "stop":
            continue
        verbatims = body.get("verbatims") if isinstance(body.get("verbatims"), dict) else {}
        for text in verbatims.values():
            for seconds in _seconds(str(text)):
                if limit is not None and seconds > limit:
                    continue
                counts.setdefault(seconds, set()).add(str(item.get("persona_id")))

    return [
        {"timestamp_sec": seconds, "personas": len(ids),
         "scene": _scene_at(seconds, pack)}
        for seconds, ids in sorted(counts.items())
    ]


def _seconds(text: str) -> list[float]:
    out: list[float] = []
    for first, second, third in _TIMECODE.findall(text or ""):
        if third:
            out.append(float(int(first) * 3600 + int(second) * 60 + int(third)))
        else:
            out.append(float(int(first) * 60 + int(second)))
    return out


def _scene_at(seconds: float, pack: dict[str, Any] | None) -> str | None:
    for entry in (pack or {}).get("timeline") or []:
        if not isinstance(entry, dict):
            continue
        start, end = _num(entry.get("start")), _num(entry.get("end"))
        if start is not None and end is not None and start <= seconds <= end:
            return entry.get("scene")
    return None
