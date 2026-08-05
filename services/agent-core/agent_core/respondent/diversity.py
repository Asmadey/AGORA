"""
Разнообразие ответов: distinct-2 и дисперсия баллов (метрика response_diversity).

Обе величины ловят одно и то же — mode collapse, — но с разных сторон, и обе
нужны, потому что каждая по отдельности обманывается.

distinct-2 меряет лексику. Модель, свалившаяся в один голос, выдаёт двадцать
пересказов одной фразы: биграммы повторяются, доля уникальных падает. Но
distinct-2 высок и тогда, когда персоны пишут разными словами одно и то же —
двадцать способов сказать «понравилось».

Дисперсия баллов меряет позицию. Она ловит ровно тот случай, который проходит
мимо distinct-2: разный текст, одинаковая оценка. Но она высока и у модели,
которая ставит случайные баллы, не связанные с текстом.

Вместе они закрывают обе дыры. Порознь любая даёт зелёную метрику на
бесполезном прогоне.
"""

from __future__ import annotations

import re
import statistics
from typing import Any

#: Порог доли уникальных биграмм. Значение ПРЕДВАРИТЕЛЬНОЕ и требует калибровки
#: на живом прогоне: оно выбрано из общей практики (осмысленно разный русский
#: текст держится в районе 0.7–0.9, вырожденный проваливается ниже 0.3), а не
#: измерено на нашей модели и нашем промпте.
#:
#: Калибровать так: прогнать 20 персон на реальном материале, посчитать
#: distinct_2 по вербатимам, затем испортить промпт (убрать из respondent.system
#: пункт про право не понравиться) и посчитать снова. Порог ставится между
#: полученными значениями, ближе к нижнему.
DISTINCT2_MIN = 0.55

#: Порог стандартного отклонения баллов. По той же причине предварительный.
#: Ориентир: реальная аудитория по корпусу даёт разброс около 1.5–2.0 балла по
#: десятибалльной шкале; всё, что ниже единицы, — признак того, что персоны
#: перестали отличаться друг от друга.
SCORE_STDEV_MIN = 1.0

#: Что считается словом. Дефис внутри слова сохраняется («научно-популярный»),
#: пунктуация отбрасывается: иначе точка в конце фразы порождала бы уникальную
#: биграмму на каждом ответе и завышала distinct-2 тем сильнее, чем короче
#: ответы.
_WORD = re.compile(r"[\w]+(?:-[\w]+)*", re.UNICODE)


def _bigrams(text: str) -> list[tuple[str, str]]:
    words = [w.lower() for w in _WORD.findall(text)]
    return list(zip(words, words[1:], strict=False))


def distinct_2(texts: list[str]) -> float:
    """
    Доля уникальных биграмм среди всех биграмм корпуса ответов.

    Считается по объединённому корпусу, а не усреднением по ответам. Разница
    принципиальная: усреднение по ответам меряет, насколько разнообразен каждый
    ответ сам по себе, и на двадцати одинаковых, но внутренне богатых текстах
    даёт высокий балл. Нас же интересует, отличаются ли ответы ДРУГ ОТ ДРУГА, —
    а это видно только на общем корпусе.

    Пустой вход даёт 0.0, а не единицу: «нет данных» ближе к «нет разнообразия»,
    чем к «идеальное разнообразие», и зелёная метрика на пустом прогоне была бы
    хуже красной.
    """
    all_bigrams: list[tuple[str, str]] = []
    for text in texts:
        all_bigrams.extend(_bigrams(text or ""))
    if not all_bigrams:
        return 0.0
    return len(set(all_bigrams)) / len(all_bigrams)


def score_stdev(score_dicts: list[dict[str, Any]], field: str = "overall_impression") -> float:
    """
    Стандартное отклонение одного балла по всем ответам.

    По умолчанию берётся overall_impression: он единственный, который персона
    ставит всегда, и по нему считается сводная оценка в отчёте. Остальные баллы
    (сюжет, игра, музыка) осмысленны не для всякого материала — у ролика без
    музыки дисперсия music равна нулю по делу, а не по вырождению.
    """
    values = [
        float(d[field]) for d in score_dicts
        if isinstance(d, dict) and isinstance(d.get(field), (int, float))
        and not isinstance(d.get(field), bool)
    ]
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def diversity_report(answers: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Сводка по набору ответов — то, что кладётся в артефакт и читает check.py.

    Вербатимы склеиваются в один текст на персону: три поля (почему такое
    впечатление, что запомнилось, мнение о героях) — это один голос, и считать
    их разными ответами значило бы утроить корпус биграмм одной персоны.
    """
    texts: list[str] = []
    scores: list[dict[str, Any]] = []
    for item in answers:
        body = item.get("answer") if "answer" in item else item
        if not isinstance(body, dict):
            continue
        verbatims = body.get("verbatims") or {}
        if isinstance(verbatims, dict):
            texts.append(" ".join(str(v) for v in verbatims.values() if v))
        if isinstance(body.get("scores"), dict):
            scores.append(body["scores"])

    d2 = distinct_2(texts)
    sd = score_stdev(scores)
    return {
        "distinct_2": round(d2, 4),
        "score_stdev": round(sd, 4),
        "distinct_2_threshold": DISTINCT2_MIN,
        "score_stdev_threshold": SCORE_STDEV_MIN,
        "mode_collapse": bool(d2 < DISTINCT2_MIN or sd < SCORE_STDEV_MIN),
        "samples": len(texts),
    }
