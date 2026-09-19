"""Следует ли назначение ценностей таблице ВЦИОМ по возрасту.

Корпус больше не является источником назначения ценностей. ВЦИОМ сообщает
маргинальную долю каждого пункта в каждой возрастной группе, поэтому ожидаемый
состав строится по тем возрастам, которые получили сгенерированные персоны.
Метрика проверяет наблюдаемый исход выдачи, а не старый счетчик корпуса.

Абсолютное число ценностей не сравнивается с числом ответов реальных
респондентов: независимые розыгрыши и правило непустого набора дают выборочные
колебания. Проверяется порядок всех семнадцати значений.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any

#: Ниже этого порядок перестаёт считаться следующим таблице ВЦИОМ.
#:
#: Порог оставляет запас на колебания независимой выборки, но ловит подмену
#: возрастных долей равномерными.
MIN_RANK_CORRELATION = 0.8

#: Сколько персон нужно, чтобы отсутствие ценности значило дефект, а не невезение.
#:
#: На пятистах персонах даже самая редкая доля ВЦИОМ дает достаточно наблюдений,
#: чтобы отсутствие значения означало дефект, а не обычное невезение.
COVERAGE_SAMPLE = 500


def _ranks(values: Sequence[float]) -> list[float]:
    """
    Ранги со средним на связках.

    Связки — не редкость, а норма: в корпусе несколько пар ценностей с равной
    частотой («Милосердие» и «Приоритет духовного» по 10, «Жизнь» и
    «Взаимопомощь» по 9). Ранг по порядку сортировки дал бы им разные места и
    занизил корреляцию на ровном месте.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """
    Ранговая корреляция. `0.0` — когда считать нечего.

    Ноль, а не `NaN`, при вырожденном входе (все значения равны): `NaN`
    просочился бы в отчёт и сравнился бы с порогом непредсказуемо — `NaN < 0.8`
    ложно, то есть метрика молча стала бы зелёной.
    """
    if len(a) != len(b) or len(a) < 2:
        return 0.0

    ra, rb = _ranks(a), _ranks(b)
    if len(set(ra)) < 2 or len(set(rb)) < 2:
        return 0.0

    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((y - mb) ** 2 for y in rb) ** 0.5
    if da == 0 or db == 0:
        return 0.0
    return round(num / (da * db), 4)


def values_grounding(*, size: int, seed: int) -> dict[str, Any]:
    """
    Замер: генерирует персон и сверяет порядок ценностей с таблицей ВЦИОМ.

    Ожидаемая частота каждой ценности складывается из доли ее возрастной группы
    для каждой выданной персоны. Это важно: агрегирование по столбцу «всего»
    потеряло бы возрастной эффект, который и проверяет эта метрика.
    """
    from .generator import (
        TRADITIONAL_VALUES,
        VALUE_SHARES_BY_AGE,
        GenerationConfig,
        PersonaGenerator,
    )

    gen = PersonaGenerator.from_corpus()
    personas = gen.generate(GenerationConfig(size=size, seed=seed))

    counts = dict.fromkeys(TRADITIONAL_VALUES, 0)
    for p in personas:
        for v in (p.get("values_and_beliefs") or {}).get("important_values") or []:
            if v in counts:
                counts[v] += 1

    order = list(TRADITIONAL_VALUES)
    got = [counts[v] for v in order]
    expected_by_value = dict.fromkeys(order, 0.0)
    for persona in personas:
        age_group = persona.get("demographics", {}).get("age_group")
        source_group = {"14-17": "18-24"}.get(age_group, age_group)
        value_shares = VALUE_SHARES_BY_AGE.get(source_group, {})
        for value in order:
            expected_by_value[value] += value_shares.get(value, 0.0)
    expected = [expected_by_value[value] for value in order]

    missing = [v for v in order if counts[v] == 0]
    return {
        "personas": size,
        "rank_correlation": spearman(expected, got),
        "coverage": 17 - len(missing),
        "missing": missing,
        # Доля самой частой ценности. Ровно 1.0 означает, что она стоит у ВСЕХ
        # персон, — это константа, а не выборка.
        "max_share": round(max(got) / size, 4) if size else 0.0,
        "source": "values_by_age_vciom.json",
        "expected_counts": {
            value: round(expected_by_value[value], 4) for value in order
        },
    }
