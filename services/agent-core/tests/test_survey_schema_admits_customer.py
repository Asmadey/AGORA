"""
Схема анкеты принимает анкету заказчика.

─── Что это за проверка ─────────────────────────────────────────────────────
`packages/shared/schemas/survey.schema.json` — контракт между конструктором
анкеты и воркером; по нему же валидируется INSERT в `surveys.questions`. Если
схема не принимает анкету заказчика, её нельзя сохранить: пятнадцать вопросов
не доедут до прогона, и увидеть это можно будет только отказом при создании
исследования.

Проверка идёт против НАСТОЯЩЕГО файла анкеты, а не против выдуманной фикстуры.
Фикстура подтвердила бы, что схема принимает то, что я под неё подогнал.

─── Что схема не принимала на момент написания теста ────────────────────────
1. Типы `single_choice`, `multi_choice`, `matrix_single` — закрытый перечень
   `QuestionType` знал только шесть старых.
2. Вопрос без шкалы: `scaleMin` и `scaleMax` объявлены обязательными у КАЖДОГО
   вопроса, хотя у выбора из списка шкалы нет и быть не может.
3. Варианты ответа, строки матрицы, потолок выбора и взаимоисключения — этих
   полей в схеме нет вовсе, а `additionalProperties: false` означает, что
   вопрос с ними будет отвергнут.
4. Пять базовых критериев прибиты к шкале 1–10 блоками `contains`, а у
   заказчика шкала 0–10.

Пункт 4 вскрывает расхождение, которое уже было записано в
`apps/web/lib/server/survey-validator.test.ts:141`: «survey.schema.json всё ещё
требует пять вопросов, а валидатор — один». Схема и рукописный валидатор
разъехались, и разъехались молча — ни один прогон на этом не упал, потому что
валидатор мягче схемы.
"""
from __future__ import annotations

import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO / "packages" / "shared" / "schemas" / "survey.schema.json"
SURVEY_PATH = REPO / "data" / "survey" / "customer_2026.json"

jsonschema = pytest.importorskip(
    "jsonschema",
    reason="jsonschema объявлена в dev-зависимостях; без неё проверка контракта не идёт",
)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text("utf-8"))


def _customer_survey() -> dict:
    doc = json.loads(SURVEY_PATH.read_text("utf-8"))
    return {"name": "Анкета заказчика", "questions": doc["questions"]}


def _question_defs() -> dict:
    return _schema()["$defs"]["Question"]


def test_анкета_заказчика_проходит_схему():
    """Главная проверка. Остальные объясняют, чем именно она падает."""
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(_customer_survey()),
        key=lambda e: list(e.absolute_path),
    )
    assert not errors, "анкету заказчика нельзя сохранить:\n" + "\n".join(
        f"  {'/'.join(str(p) for p in e.absolute_path) or '<корень>'}: {e.message}"
        for e in errors[:10]
    )


def test_перечень_типов_содержит_пять_нужных():
    allowed = set(_schema()["$defs"]["QuestionType"]["enum"])
    need = {"scale", "single_choice", "multi_choice", "matrix_single", "open"}
    assert need <= allowed, f"в перечне нет типов: {sorted(need - allowed)}"


def test_шкала_обязательна_только_у_шкального_вопроса():
    """
    `scaleMin`/`scaleMax` у выбора из списка не значат ничего. Требовать их —
    значит заставлять конструктор писать числа, которых у вопроса нет, и
    хранить их в базе как настоящие границы.
    """
    required = set(_question_defs().get("required") or [])
    assert "scaleMin" not in required, "scaleMin требуется у каждого вопроса"
    assert "scaleMax" not in required, "scaleMax требуется у каждого вопроса"


def test_схема_знает_варианты_строки_и_потолок_выбора():
    props = _question_defs()["properties"]
    for field in ("options", "maxChoices", "exclusiveOptionIds", "rows", "themes", "block"):
        assert field in props, f"схема не знает поля {field!r}, и вопрос с ним будет отвергнут"


def test_вариант_несёт_идентификатор_и_подпись():
    """
    Ответ персоны адресует вариант идентификатором, а не подписью. Подпись
    правят, идентификатор — нет; на подписи держалось бы ровно то расхождение
    «писатель и читатель разошлись по строке», которое здесь чинили четырежды.
    """
    option = _schema()["$defs"]["Option"]
    assert set(option.get("required") or []) >= {"id", "label"}


def test_базовые_критерии_больше_не_прибиты_к_шкале_один_десять():
    """
    У заказчика шкала 0–10. Прежняя схема требовала присутствия пяти вопросов
    с baseKey и границами ровно 1 и 10 — то есть отвергала его анкету целиком.
    """
    raw = SCHEMA_PATH.read_text("utf-8")
    doc = json.loads(raw)
    for block in doc.get("allOf") or []:
        contains = (
            block.get("properties", {}).get("questions", {}).get("contains", {})
        )
        props = contains.get("properties") or {}
        assert props.get("scaleMin", {}).get("const") != 1, (
            "схема всё ещё требует базовый критерий на шкале 1–10"
        )
