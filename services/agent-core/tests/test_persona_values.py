"""
Проверки канонического пула и независимого возрастного розыгрыша ценностей.

─── Что было ────────────────────────────────────────────────────────────────
16.09.2026 у каждой персоны было ровно три ценности, и первые две совпадали у
ВСЕХ персон набора. Владелец правил `prompts/persona.generate.md` — «3-5» на
«5» — и это не давало ничего.

Семь слоёв, и ни один не пожаловался:

1. `_map_values(rng, n=3)` — тройка прибита в вызове, хотя функция умеет до 5.
2. `picked = values_pool[:2]` — топ-2 корпуса берутся ВСЕГДА. «Крепкая семья»
   (38.8 %) и «Справедливость» (32.7 %) стояли у каждой персоны, варьировалась
   одна ценность из трёх.
3. Пул — `most_common(15)` по корпусу, а не канонический список.
4. `VCIOM_TO_DNA` выглядел белым списком и им не был: `.get(v, v)` пропускает
   незнакомое насквозь. В пул попадало «Неравенство, разделение людей в
   соответствии с их способностями» — прямая противоположность ценности.
5. Схема: `important_values: list[str]` без перечня и без длины.
6. `persona_grounding` ценности не проверяет вовсе.
7. `prompts/persona.generate.md` не читается в боевом пути: и задача Celery, и
   CLI зовут детерминированный `generate_named`. Правка промпта не могла
   подействовать.

─── Чего этот тест НЕ утверждает ────────────────────────────────────────────
Что пять ценностей — это то, что сказали люди. Реальные респонденты называли
одну-две (среднее 1.45, максимум 2 из 165). Пять — осознанное обогащение
профиля ради генерации, а не результат опроса, и подпись «ВЦИОМ» на карточке
описывает происхождение СПИСКА, а не число выбранных.
"""
from __future__ import annotations

import collections
import json
import pathlib

from agent_core.persona.generator import (
    TRADITIONAL_VALUES,
    GenerationConfig,
    PersonaGenerator,
)

CANON = [
    "Жизнь",
    "Достоинство",
    "Права и свободы человека",
    "Патриотизм",
    "Гражданственность",
    "Служение Отечеству и ответственность за его судьбу",
    "Высокие нравственные идеалы",
    "Крепкая семья",
    "Созидательный труд",
    "Приоритет духовного над материальным",
    "Гуманизм",
    "Милосердие",
    "Справедливость",
    "Коллективизм",
    "Взаимопомощь и взаимоуважение",
    "Историческая память и преемственность поколений",
    "Единство народов России",
]


def _gen(size: int = 40, seed: int = 439112026):
    g = PersonaGenerator.from_corpus()
    return g.generate(GenerationConfig(size=size, seed=seed))


def _values(p):
    return p["values_and_beliefs"]["important_values"]


# ─── Справочник ─────────────────────────────────────────────────────────────


def test_справочник_лежит_в_данных_а_не_в_коде():
    """
    Канонический список — внешняя таксономия, а не константа программы.

    Он живёт в `data/`, рядом с корпусом, и несёт при себе происхождение. В
    коде рядом с ним стоял бы `VCIOM_TO_DNA`, который уже один раз обманул:
    выглядел белым списком, не будучи им.
    """
    root = pathlib.Path(__file__).resolve().parents[3]
    f = root / "data" / "values" / "traditional_values.json"
    assert f.exists(), f"нет справочника {f}"

    doc = json.loads(f.read_text("utf-8"))
    assert doc["values"] == CANON, "состав и порядок справочника"
    assert doc.get("source"), "у справочника назван источник"


def test_справочник_и_код_не_расходятся():
    assert list(TRADITIONAL_VALUES) == CANON
    assert len(TRADITIONAL_VALUES) == 17


# ─── Независимый розыгрыш по возрасту ───────────────────────────────────────


def test_число_ценностей_переменное_и_непустое():
    personas = _gen(size=500)
    lengths = [len(_values(p)) for p in personas]
    assert all(1 <= length <= 17 for length in lengths), lengths
    assert len(set(lengths)) > 1, lengths
    assert 6.5 <= sum(lengths) / len(lengths) <= 9.5


def test_персона_с_нулевым_розыгрышем_получает_самую_вероятную_ценность():
    class AlwaysFailRandom:
        def random(self):
            return 1.0

    generator = PersonaGenerator.from_corpus()
    values = generator._map_values(AlwaysFailRandom(), "18-24")
    assert values == ["Крепкая семья"]


def test_ценности_не_повторяются_внутри_персоны():
    for p in _gen():
        vs = _values(p)
        assert len(set(vs)) == len(vs), vs


def test_только_канонические_значения():
    """
    Пул — справочник, а не корпус. Раньше сюда попадало «Неравенство,
    разделение людей…» — оно входит в топ-15 корпуса (3.0 %) и проходило
    насквозь через `.get(v, v)`.
    """
    allowed = set(CANON)
    for p in _gen():
        assert set(_values(p)) <= allowed, set(_values(p)) - allowed


# ─── Разнообразие ───────────────────────────────────────────────────────────


def test_ни_одна_ценность_не_стоит_у_всех():
    """
    Жёсткий топ-2 убран. Раньше «Крепкая семья» и «Справедливость» были у
    каждой персоны без исключения — это не выборка, а константа.
    """
    personas = _gen(size=40)
    counts = collections.Counter(v for p in personas for v in _values(p))
    for value, n in counts.items():
        assert n < len(personas), f"«{value}» стоит у всех {n} персон"


def test_набор_покрывает_заметную_часть_справочника():
    personas = _gen(size=40)
    distinct = {v for p in personas for v in _values(p)}
    assert len(distinct) >= 12, f"на 40 персон встретилось только {len(distinct)}: {distinct}"


def test_частые_ценности_остаются_частыми():
    """
    Возрастные доли ВЦИОМ должны сохранять различие между частой и редкой
    ценностью, а не превращать выборку в равномерную.
    """
    personas = _gen(size=60)
    counts = collections.Counter(v for p in personas for v in _values(p))
    assert counts["Крепкая семья"] > counts["Коллективизм"]


def test_редкая_ценность_достижима():
    """
    Даже ценность с небольшой долей ВЦИОМ должна быть достижима.
    """
    personas = _gen(size=400)
    distinct = {v for p in personas for v in _values(p)}
    assert "Созидательный труд" in distinct


# ─── Воспроизводимость ──────────────────────────────────────────────────────


def test_один_seed_один_результат():
    """CDD задачи #4: diff == 0 на повторном прогоне. Правка его не отменяет."""
    a = [_values(p) for p in _gen(size=20, seed=12345)]
    b = [_values(p) for p in _gen(size=20, seed=12345)]
    assert a == b


def test_разные_seed_дают_разные_наборы():
    a = [_values(p) for p in _gen(size=20, seed=1)]
    b = [_values(p) for p in _gen(size=20, seed=2)]
    assert a != b
