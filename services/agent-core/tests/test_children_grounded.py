"""
Наличие детей сэмплируется из корпуса, а не из прибитых весов.

─── Что было ─────────────────────────────────────────────────────────────────
`generator.py` разыгрывал `children` так:

    # Children — сэмплим из корпуса          ← комментарий
    children = rng.choices(
        ["Да, есть ребенок / дети", "Нет детей", "Не указано"],
        weights=[0.4, 0.4, 0.2],             ← веса прибиты
    )[0]

Комментарий обещал заземление, код его не делал. Замер 17.09.2026:

    в корпусе:              Не указано 73 %, Да, есть дети 27 %, Нет детей 0 %
    в выдаче генератора:    Да 42 %, Нет детей 40 %, Не указано 18 %

**«Нет детей» не встречается в корпусе ни разу**, а генератор выдавал его
сорока процентам персон. Доли двух оставшихся перевёрнуты почти зеркально.

Почему это не мелочь: `children` — четвёртое по частоте поле в претензиях судьи
связности на боевом (6 из 74). Часть отбраковок была про несогласованность
текста со значением, которого в исследовании не было вообще.

─── Почему проверяется распределение, а не одна персона ─────────────────────
Одна персона не отличает «сэмплим из корпуса» от «сэмплим из чего угодно».
Проверка идёт по выдаче достаточного размера и сверяет доли с корпусом с
допуском на случайность.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from agent_core.persona.generator import (
    CorpusDistribution,
    GenerationConfig,
    PersonaGenerator,
)

CORPUS = (
    Path(__file__).resolve().parents[3]
    / "data" / "grounding" / "unified_respondent_sessions.json"
)

#: Персон в выдаче. На четырёхстах доля с истинным значением 0.27 колеблется
#: примерно на ±0.04 (два стандартных отклонения), и допуск ниже берётся с
#: запасом к этому числу.
SAMPLE = 400

#: Допуск на долю. Не «на глаз»: 1/sqrt(400) ≈ 0.05, то есть чуть больше двух
#: стандартных отклонений для долей такого порядка.
TOLERANCE = 0.06


def corpus_shares() -> dict[str, float]:
    records = json.loads(CORPUS.read_text("utf-8"))
    counter = Counter(r["socio_demographics"].get("children", "Не указано") for r in records)
    return {k: v / len(records) for k, v in counter.items()}


def generated_shares() -> dict[str, float]:
    personas = PersonaGenerator.from_corpus().generate(
        GenerationConfig(size=SAMPLE, seed=99)
    )
    counter = Counter(p["demographics"]["children"] for p in personas)
    return {k: v / len(personas) for k, v in counter.items()}


def test_distribution_is_in_the_corpus_distribution():
    """Поле есть в разобранном корпусе — иначе сэмплировать не из чего."""
    dist = CorpusDistribution.from_file()
    assert hasattr(dist, "children"), (
        "CorpusDistribution не разбирает children — значит генератор берёт доли "
        "откуда-то ещё"
    )
    assert dist.children, "распределение children пусто"
    assert abs(sum(dist.children.values()) - 1.0) < 1e-6, "доли не нормированы"


def test_value_absent_from_the_corpus_is_never_generated():
    """
    «Нет детей» в корпусе ноль раз — значит и в выдаче ноль.

    Это главная проверка. Прежде такое значение получали 40 % персон.
    """
    shares = generated_shares()
    corpus = corpus_shares()
    invented = sorted(set(shares) - set(corpus))
    assert not invented, (
        f"сгенерированы значения, которых в корпусе нет: {invented}. "
        f"Персона с таким атрибутом не заземлена ничем"
    )


def test_shares_follow_the_corpus():
    """Доли совпадают с корпусными в пределах случайности выборки."""
    corpus = corpus_shares()
    shares = generated_shares()
    for value, expected in corpus.items():
        actual = shares.get(value, 0.0)
        assert abs(actual - expected) <= TOLERANCE, (
            f"«{value}»: в корпусе {expected:.0%}, в выдаче {actual:.0%} — "
            f"расхождение больше допуска {TOLERANCE:.0%}"
        )


def test_comment_no_longer_lies():
    """
    Прибитых весов в коде не осталось.

    Комментарий «сэмплим из корпуса» стоял над списком с весами `[0.4, 0.4, 0.2]`
    больше месяца. Проверка держит соответствие кода его собственному описанию.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "agent_core" / "persona" / "generator.py"
    ).read_text("utf-8")
    assert "weights=[0.4, 0.4, 0.2]" not in source, "прибитые веса children на месте"
    assert '"Нет детей"' not in source, (
        "значение «Нет детей» всё ещё перечислено в коде — в корпусе его нет"
    )
