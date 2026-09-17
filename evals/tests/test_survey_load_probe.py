"""
Замерочный инструмент проверяется сам, прежде чем им что-то мерить.

─── Почему ──────────────────────────────────────────────────────────────────
В этом проекте уже дважды число с виду работало и означало не то. `persona_
grounding` сверял маргиналы корпуса с генератором, который из этого же корпуса
и сэмплирует, — обе стороны сравнения были одним источником. `emotional_index`
считал долю персон, назвавших хоть одну эмоцию, и подписывался как «насколько
задело».

`survey_load_probe` даёт два числа, по которым принимаются решения: доля
пропущенных полей и наличие эха между ценностями персоны и её ответом на
вопрос 8. Оба считаются кодом, у которого нет внешней сверки, — значит нужна
своя.

─── Что проверяется ─────────────────────────────────────────────────────────
Что перестановочный тест отличает подстроенное эхо от независимости, и что
счётчик покрытия считает матрицу построчно. Не «работает без ошибок», а
«отвечает разное на разные входы» — метрика, дающая один и тот же ответ на
всё, выглядит работающей ровно так же.
"""
from __future__ import annotations

import json
import pathlib
import random
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "evals" / "analysis"))
sys.path.insert(0, str(REPO / "services" / "agent-core"))

import survey_load_probe as probe
from agent_core.survey import answerable_fields

SURVEY = json.loads((REPO / "data" / "survey" / "customer_2026.json").read_text("utf-8"))
FIELDS = answerable_fields(SURVEY["questions"])
VALUES = [f"V{i}" for i in range(17)]


def _pairs(kind: str, n: int = 20, seed: int = 1):
    rng = random.Random(seed)
    own = [set(rng.sample(VALUES, 5)) for _ in range(n)]
    if kind == "echo":
        return [(o, set(rng.sample(sorted(o), 2))) for o in own]
    if kind == "half":
        return [
            (o, set(rng.sample(sorted(o), 1)) | set(rng.sample(VALUES, 1)))
            for o in own
        ]
    return [(o, set(rng.sample(VALUES, 2))) for o in own]


def test_перестановочный_тест_видит_подстроенное_эхо():
    result = probe.echo_test(_pairs("echo"), rounds=5000)
    assert result["p"] < 0.01, f"эхо, собранное вручную, не поймано: {result}"


def test_перестановочный_тест_видит_половинное_эхо():
    """Половина ответа своя, половина случайная — эхо всё ещё должно ловиться."""
    result = probe.echo_test(_pairs("half"), rounds=5000)
    assert result["p"] < 0.05, f"половинное эхо не поймано: {result}"


def test_перестановочный_тест_молчит_на_независимых_ответах():
    """
    Главная проверка. Тест, который всегда говорит «эхо есть», не отличается от
    отсутствующего — и именно так выглядела бы ошибка в статистике.
    """
    result = probe.echo_test(_pairs("independent"), rounds=5000)
    assert result["p"] > 0.05, f"ложная тревога на независимых ответах: {result}"


def test_мало_наблюдений_называется_прямо():
    """Четыре персоны — не выборка. Число по ним хуже отсутствия числа."""
    result = probe.echo_test(_pairs("echo", n=4), rounds=100)
    assert result["p"] is None
    assert "мало" in result["note"]


# ─── Покрытие ────────────────────────────────────────────────────────────────


def test_покрытие_считает_матрицу_построчно():
    """
    Ответ «на вопрос 9» целиком не закрывает сорок три подтемы. Считать его за
    один закрытый вопрос значило бы не заметить сорок два пропуска.
    """
    answer = {"survey_answers": [{"question": "q09-themes", "answer": "m-1"}]}
    done, missing = probe.coverage(answer, FIELDS)
    assert done == 0, "матрица целиком не закрывает ни одного поля"
    assert len([m for m in missing if m.startswith("q09-themes/")]) == 43


def test_покрытие_принимает_идентификатор_строки():
    answer = {"survey_answers": [
        {"question": "t1-1", "answer": "m-1"},
        {"question": "imp-4", "answer": "y-1"},
        {"question": "q01-plot", "answer": "8"},
    ]}
    done, _ = probe.coverage(answer, FIELDS)
    assert done == 3


def test_покрытие_читает_обе_формы_ответа():
    """
    Промпт объявляет список пар, модель возвращает и объект. Счётчик, знающий
    одну форму, показал «закрыто 0 из 67» на ответе, где закрыты все 67, — и
    это выглядело результатом замера, а не дефектом чтения.
    """
    as_list = {"survey_answers": [{"question": "q01-plot", "answer": "8"}]}
    as_map = {"survey_answers": {"q01-plot": 8}}
    assert probe.coverage(as_list, FIELDS)[0] == 1
    assert probe.coverage(as_map, FIELDS)[0] == 1
    assert probe.answer_for(as_list, "q01-plot") == "8"
    assert probe.answer_for(as_map, "q01-plot") == 8


def test_полный_ответ_в_форме_объекта_закрывает_все_поля():
    answer = {"survey_answers": {f.split("/")[-1]: "x" for f in FIELDS}}
    done, missing = probe.coverage(answer, FIELDS)
    assert missing == []
    assert done == 67


def test_полный_ответ_закрывает_все_поля():
    answer = {"survey_answers": [
        {"question": f.split("/")[-1], "answer": "x"} for f in FIELDS
    ]}
    done, missing = probe.coverage(answer, FIELDS)
    assert missing == []
    assert done == len(FIELDS) == 67
