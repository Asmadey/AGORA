"""
Схема ответа персоны строится ИЗ АНКЕТЫ, а не пишется рядом с ней.

─── Зачем схема, когда её однажды уже убрали ────────────────────────────────
Убрали по замеру, и замер стоит помнить: двенадцать боевых персон, один
промпт, температура 0.3, бок о бок — со строгой схемой разобрано 8 из 12, без
неё 12 из 12. Четыре ответа вырождались под грамматикой: модель залипала то на
пробельных токенах между значениями, то на счётчике внутри строки
(«, 4, 5, 6, … 675»), и шла до потолка, не дописав JSON.

Решение владельца 17.09.2026 — вернуть схему, вместе с правилом покрытия и
переспросом, все три в связке. Возвращается она не в прежнем виде, и это не
формальность: прежняя схема оставляла массивы и строки БЕЗ ГРАНИЦ, а названные
режимы вырождения — это ровно неограниченная длина. Здесь каждый массив несёт
`maxItems`, каждая свободная строка — `maxLength`.

Утверждать, что этого достаточно, я не могу: доказать может только замер тем
же прибором. Тест держит другое — что схема описывает ИМЕННО ту анкету,
которую задали, и не расходится с ней молча.

─── Почему схема генерируется, а не лежит файлом ────────────────────────────
Анкета у каждого исследования своя: оператор выбирает темы, добавляет свои
вопросы. Схема, написанная рядом с кодом, описывала бы одну анкету и тихо
разъезжалась бы со всеми остальными — это ровно то семейство дефектов, которое
в этом репозитории чинили четырежды.
"""
from __future__ import annotations

import json
import pathlib

from agent_core.respondent.answer_schema import answer_json_schema
from agent_core.survey import answerable_fields

REPO = pathlib.Path(__file__).resolve().parents[3]
SURVEY = json.loads((REPO / "data" / "survey" / "customer_2026.json").read_text("utf-8"))
QUESTIONS = SURVEY["questions"]


def _fields(schema: dict) -> dict:
    return schema["properties"]["survey_answers"]


def test_каждое_поле_анкеты_обязательно():
    """
    Ради этого схема и возвращается. Пропуск поля перестаёт быть возможным
    исходом: модель не может не назвать ключ, который грамматика требует.
    """
    schema = answer_json_schema(QUESTIONS)
    block = _fields(schema)
    expected = answerable_fields(QUESTIONS)
    assert sorted(block["required"]) == sorted(expected)
    assert len(expected) == 67, "пятнадцать вопросов дают шестьдесят семь полей"
    assert block["additionalProperties"] is False


def test_шкала_описана_своими_границами():
    schema = answer_json_schema(QUESTIONS)
    plot = _fields(schema)["properties"]["q01-plot"]
    assert plot["type"] == "integer"
    assert (plot["minimum"], plot["maximum"]) == (0, 10)


def test_закрытый_вопрос_описан_перечнем_идентификаторов():
    schema = answer_json_schema(QUESTIONS)
    q10 = _fields(schema)["properties"]["q10-importance"]
    assert q10["type"] == "string"
    assert q10["enum"] == ["i-1", "i-2", "i-s1"], "варианты вопроса 10, включая служебный"


def test_мультивыбор_ограничен_потолком_вопроса():
    """
    `maxChoices` перестаёт быть правилом, которое можно нарушить: он становится
    границей массива в грамматике.
    """
    schema = answer_json_schema(QUESTIONS)
    q7 = _fields(schema)["properties"]["q07-emotions"]
    assert q7["type"] == "array"
    assert q7["maxItems"] == 3
    assert q7["items"]["enum"][0] == "e-1"
    assert len(q7["items"]["enum"]) == 15


def test_строка_матрицы_становится_своим_полем():
    schema = answer_json_schema(QUESTIONS)
    props = _fields(schema)["properties"]
    assert "t1-1" in props, "поле адресуется идентификатором строки"
    assert props["t1-1"]["enum"] == ["m-1", "m-2", "m-3"]


def test_свободный_текст_ограничен_длиной():
    """
    Прямая заплатка на измеренный режим вырождения: «счётчик внутри строки»
    возможен ровно там, где у строки нет верхней границы.
    """
    schema = answer_json_schema(QUESTIONS)
    for key in ("why_impression", "memorable_elements", "character_opinions"):
        assert schema["properties"]["verbatims"]["properties"][key]["maxLength"] > 0
    refs = schema["properties"]["grounding_refs"]
    assert refs["maxItems"] > 0
    assert refs["items"]["maxLength"] > 0


def test_схема_строгая_насквозь():
    """
    `strict: true` у OpenAI-совместимых endpoint требует, чтобы в КАЖДОМ
    объекте были закрыты дополнительные поля и перечислены обязательные.
    Объект, который это нарушает, endpoint отвергает целиком — то есть прогон
    падает на первой персоне, а выглядит это как отказ провайдера.
    """
    def walk(node: dict, path: str = "$") -> None:
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False, f"{path}: не закрыт"
            assert sorted(node.get("required", [])) == sorted(node.get("properties", {})), (
                f"{path}: required не совпадает с properties"
            )
            for key, child in node.get("properties", {}).items():
                walk(child, f"{path}.{key}")
        elif node.get("type") == "array":
            walk(node.get("items") or {}, f"{path}[]")

    walk(answer_json_schema(QUESTIONS))


def test_анкета_без_матрицы_даёт_меньше_полей():
    """Схема следует за анкетой, а не за файлом заказчика."""
    small = [q for q in QUESTIONS if q["type"] != "matrix_single"]
    block = _fields(answer_json_schema(small))
    assert len(block["required"]) == 13
