"""
Отчёт обязан доезжать до Mongo целиком — прогон 0093.

Прогон отработал семь минут, посчитал девятнадцать ответов и потерял отчёт
целиком:

    analytics: отчёт не сохранён (InvalidDocument: Invalid document: documents
    must have only string keys, key was 3); интерфейс его не покажет

Ключ 3 — это балл по шкале. `_scale` строил распределение как
`{балл: сколько раз}`, то есть с ЦЕЛЫМИ ключами, а Mongo целые ключи в документе
не принимает вовсе.

Заметить это раньше было нечем по двум причинам сразу.

Первая: рядом лежит `_write`, который кладёт тот же отчёт в `report.json`, и
`json.dumps` превращает целый ключ в строку молча. Файл на диске выглядел
безупречно — в нём уже `"3"`, — и по нему дефект не виден.

Вторая: запись в Mongo обёрнута в `except Exception`, чтобы недоступная база не
роняла посчитанный прогон. Задача при этом завершилась успехом, статус стал
REPORT_READY, а экран отчёта сказал «ещё не готов или принадлежит другой
команде».

Поэтому тестов здесь два, и они про разное:

* `test_scale_distribution_keys_are_strings` — про источник: распределение
  обязано быть строковым на выходе расчёта;
* `test_save_report_survives_non_string_keys` — про границу: один посторонний
  ключ, откуда бы он ни взялся завтра, не имеет права стоить целого отчёта.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.analytics.store import save_report  # noqa: E402
from agent_core.analytics.survey_stats import survey_tally  # noqa: E402

SCALE_SURVEY = {
    "questions": [
        {
            "id": "q01-plot",
            "number": 1,
            "type": "scale",
            "block": "b1",
            "baseKey": "plot",
            "label": "Насколько понравился сюжет",
            "scaleMin": 0,
            "scaleMax": 10,
        }
    ]
}


def _answer(persona_id: str, value: int) -> dict:
    return {
        "persona_id": persona_id,
        "replication": 0,
        "answer": {"survey_answers": [{"question": "q01-plot", "answer": value}]},
    }


def _persona(persona_id: str, age: int) -> dict:
    return {"id": persona_id, "dna": {"demographics": {"age": age}}}


def _non_string_keys(node: object, path: str = "") -> list[str]:
    """Все места, где ключ документа не строка. Пусто — документ доедет."""
    bad: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                bad.append(f"{path}/{key!r} ({type(key).__name__})")
            bad.extend(_non_string_keys(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            bad.extend(_non_string_keys(value, f"{path}[{index}]"))
    return bad


def test_scale_distribution_keys_are_strings() -> None:
    answers = [_answer(f"p{i}", 3 + (i % 5)) for i in range(10)]
    personas = [_persona(f"p{i}", 20 + i) for i in range(10)]

    tally = survey_tally(SCALE_SURVEY, answers, personas)

    distribution = tally["questions"]["q01-plot"]["total"]["distribution"]
    assert distribution, "распределение пустое — тест не о том"
    bad = _non_string_keys(tally)
    assert not bad, "нестроковые ключи в расчёте анкеты: " + ", ".join(bad)


class _FakeCollection:
    """Mongo, но строгая ровно в том, в чём строга настоящая."""

    def __init__(self) -> None:
        self.docs: list[dict] = []

    def update_one(self, filt: dict, update: dict, upsert: bool = False) -> None:
        body = update["$set"]
        bad = _non_string_keys(body)
        if bad:
            raise TypeError(
                "Invalid document: documents must have only string keys, "
                f"key was {bad[0]}"
            )
        self.docs.append({**filt, **body})


class _FakeDb(dict):
    def __missing__(self, name: str) -> _FakeCollection:
        collection = _FakeCollection()
        self[name] = collection
        return collection


def test_save_report_survives_non_string_keys() -> None:
    db = _FakeDb()
    report = {"aggregate": {"survey": {"distribution": {3: 2, 4: 5}}}}
    answers = [
        {
            "persona_id": "p1",
            "replication": 0,
            "persona_name": "Аня",
            "segment": {"age_group": "18-24"},
            "answer": {"scores": {1: "низко"}},
        }
    ]

    saved = save_report(
        db,
        tenant_id="11111111-1111-1111-1111-111111111111",
        task_id="22222222-2222-2222-2222-222222222222",
        report=report,
        answers=answers,
    )

    assert saved == 1
    stored = db["reports"].docs[0]["report"]
    assert stored["aggregate"]["survey"]["distribution"] == {"3": 2, "4": 5}
