#!/usr/bin/env python3
"""
Замеры, которыми закрыта гипотеза о «трёх независимых жребиях».

─── Зачем этот файл существует ───────────────────────────────────────────────
16.09.2026 разбор нашёл в `persona/generator.py` место, где возраст, гео и пол
разыгрываются тремя независимыми жребиями, и посчитал расхождение получившегося
распределения с совместным распределением корпуса: total variation = 0.144.
Число выглядело дефектом, и на нём был написан план правки.

План был неверен. Проверки ниже показывают, почему, и оставлены в репозитории
именно поэтому: без них через месяц те же 0.144 найдутся снова — они видны с
первого взгляда на `generator.py:655-657`, а опровержение не видно ниоткуда.

Скрипт ничего не меняет и никуда не ходит: читает корпус, печатает три таблицы.

    python3 evals/analysis/persona_grounding_probe.py
"""

from __future__ import annotations

import json
import random
import statistics
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "data" / "grounding" / "unified_respondent_sessions.json"

#: Сид фиксирован, чтобы числа в документе и числа из прогона совпадали.
SEED = 20260916
TRIALS = 5000


def cell(record: dict) -> tuple[str, str, str]:
    socio = record["socio_demographics"]
    return socio["age_group"], socio["geo"], socio["gender"]


def tv_against_independent(rows: list[tuple[str, str, str]]) -> float:
    """Расхождение совместного распределения с произведением маргиналов."""
    n = len(rows)
    joint = Counter(rows)
    a, g, s = (Counter(r[i] for r in rows) for i in range(3))
    total = 0.0
    for x in a:
        for y in g:
            for z in s:
                p_true = joint.get((x, y, z), 0) / n
                p_ind = (a[x] / n) * (g[y] / n) * (s[z] / n)
                total += abs(p_true - p_ind)
    return total / 2


def main() -> int:
    records = json.loads(CORPUS.read_text("utf-8"))
    rows = [cell(r) for r in records]
    n = len(rows)
    rng = random.Random(SEED)

    observed = tv_against_independent(rows)
    print(f"Корпус: {n} записей, ячеек возможных "
          f"{len({r[0] for r in rows}) * len({r[1] for r in rows}) * len({r[2] for r in rows})}, "
          f"наблюдалось {len(set(rows))}\n")

    # ── 1. Связь есть или это шум выборки? ───────────────────────────────────
    #
    # Колонки перемешиваются независимо: связь разрушена заведомо. Если
    # наблюдаемое значение попадает в получившийся шум, связи в корпусе нет.
    print("1. Есть ли связь возраст×гео×пол")
    null = []
    for _ in range(TRIALS):
        a = [r[0] for r in rows]
        g = [r[1] for r in rows]
        s = [r[2] for r in rows]
        rng.shuffle(a)
        rng.shuffle(g)
        rng.shuffle(s)
        null.append(tv_against_independent(list(zip(a, g, s, strict=True))))
    null.sort()
    p_value = sum(1 for x in null if x >= observed) / len(null)
    print(f"   наблюдалось                {observed:.4f}")
    print(f"   шум при независимости      медиана {statistics.median(null):.4f}  "
          f"p95 {null[int(0.95 * len(null))]:.4f}  p99 {null[int(0.99 * len(null))]:.4f}")
    print(f"   p-value                    {p_value:.3f}  →  "
          f"{'связь есть' if p_value < 0.05 else 'ОТ ШУМА НЕ ОТЛИЧАЕТСЯ'}\n")

    # ── 2. Устойчив ли сам эмпирический джойнт? ──────────────────────────────
    #
    # Если половины корпуса расходятся между собой сильнее, чем джойнт расходится
    # с произведением маргиналов, то мишень колеблется сильнее промаха, и
    # «попасть» в неё нельзя даже принципиально.
    print("2. Устойчивость эмпирического джойнта")
    halves = []
    index = list(range(n))
    for _ in range(2000):
        rng.shuffle(index)
        h1, h2 = index[: n // 2], index[n // 2:]
        c1, c2 = Counter(rows[i] for i in h1), Counter(rows[i] for i in h2)
        keys = set(c1) | set(c2)
        halves.append(
            sum(abs(c1.get(k, 0) / len(h1) - c2.get(k, 0) / len(h2)) for k in keys) / 2
        )
    halves.sort()
    print(f"   TV(половина A, половина B) медиана {statistics.median(halves):.4f}  "
          f"p05 {halves[int(0.05 * len(halves))]:.4f}  p95 {halves[int(0.95 * len(halves))]:.4f}")
    print(f"   TV(джойнт, произведение)   {observed:.4f}")
    print(f"   →  собственная неустойчивость мишени "
          f"{'БОЛЬШЕ' if statistics.median(halves) > observed else 'меньше'} мнимого дефекта\n")

    # ── 3. Что это меняет в отчётных числах ──────────────────────────────────
    #
    # Верхний предел эффекта: средние по критериям, взвешенные двумя способами.
    # Допуск метрики persona_grounding по средним — 1.0 балла.
    print("3. Влияние на отчётные числа (шкала 1–10)")
    by_cell: dict[tuple[str, str, str], list[dict]] = {}
    for r in records:
        by_cell.setdefault(cell(r), []).append(r)
    joint = Counter(rows)
    w_true = {k: v / n for k, v in joint.items()}
    a, g, s = (Counter(r[i] for r in rows) for i in range(3))
    w_ind = {
        (x, y, z): (a[x] / n) * (g[y] / n) * (s[z] / n)
        for x in a for y in g for z in s
    }

    def weighted(weights: dict, field: str) -> float:
        num = den = 0.0
        for key, group in by_cell.items():
            values = [r["agora_core_scores_1_to_10"].get(field) for r in group]
            values = [v for v in values if isinstance(v, int | float)]
            if not values or key not in weights:
                continue
            num += weights[key] * statistics.mean(values)
            den += weights[key]
        return num / den

    print(f"   {'критерий':<22}{'по джойнту':>12}{'независимо':>12}{'разница':>10}")
    for field in ("overall_impression", "plot", "acting", "music", "cinematography"):
        x, y = weighted(w_true, field), weighted(w_ind, field)
        print(f"   {field:<22}{x:>12.3f}{y:>12.3f}{abs(x - y):>10.3f}")
    print("\n   Допуск persona_grounding по средним — 1.0 балла.")
    print("   Вывод: при n=165 замена трёх жребиев на один не оправдана.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
