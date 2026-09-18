"""
Модель ответа персоны, построенная из анкеты этого исследования.

─── Зачем она, если схему однажды уже убрали ────────────────────────────────
Убрали по замеру, и замер надо держать перед глазами, а не в истории коммитов.
Двенадцать боевых персон, один промпт, температура 0.3, бок о бок:

    со схемой   8 из 12 разобрано
    без схемы  12 из 12 разобрано

Четыре ответа вырождались под грамматикой: после нормального начала модель
залипала — то на пробельных токенах (JSON разрешает их между значениями), то
на счётчике внутри строки («, 4, 5, 6, … 675») — и шла до потолка, не дописав
JSON. Терялось не поле, а весь оплаченный ответ.

Владелец решил 17.09.2026 вернуть схему — вместе с правилом покрытия и
переспросом, все три в связке, потому что неполный ответ объявлен ошибкой.

─── Что здесь сделано иначе, и почему это не формальность ───────────────────
Оба названных режима вырождения — это отсутствие верхней границы. Пробельное
залипание и счётчик внутри строки возможны ровно там, где грамматика не знает,
когда пора остановиться. Прежняя схема (`schemas/responses.RESPONDENT`)
описывала `survey_answers` массивом пар БЕЗ `maxItems`, а вербатимы и
`grounding_refs` — строками и массивами без длины.

Здесь границы стоят везде: у каждого массива `maxItems`, у каждой свободной
строки `maxLength`, а `survey_answers` вообще перестал быть массивом — это
объект с известным набором ключей.

Обещать, что этого достаточно, нельзя: доказать может только замер тем же
прибором (`evals/analysis/survey_load_probe.py`). До замера схема включается
переключателем и по умолчанию выключена — см. `respondent/run.py`.

─── Почему схема генерируется, а не лежит файлом ────────────────────────────
Анкета у каждого исследования своя: оператор выбирает темы вопроса 9 и
добавляет свои вопросы. Схема, написанная рядом с кодом, описывала бы одну
анкету и молча расходилась бы со всеми прочими — это то самое семейство
дефектов, которое в этом репозитории чинили четырежды.

Поэтому источник один: документ анкеты. Из него же берёт поля `survey.py`,
им же адресуют ответ выгрузка и расчёты.

─── Почему pydantic, а не словарь ───────────────────────────────────────────
Модель нужна дважды. Первый раз — чтобы отдать провайдеру JSON Schema. Второй
раз — чтобы проверить пришедший ответ У СЕБЯ: провайдер может грамматику не
поддержать, поддержать частично или молча её проигнорировать, и полагаться на
одно лишь его обещание значит не иметь проверки вовсе.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from ..schemas.answer import RETENTION_VALUES
from ..survey import question_rows, row_max_choices, row_options, survey_questions

#: Границы свободных полей.
#:
#: Числа не из воздуха: замеренный размер ответа персоны — 2197–2769 знаков на
#: весь JSON, медиана 2384. Вербатим в две фразы укладывается в 600 с запасом
#: втрое, а ссылка на сцену — это «0:44–0:48» плюс пара слов.
#:
#: Граница здесь не экономия токенов, а лечение названного режима вырождения:
#: счётчик внутри строки возможен ровно там, где у строки нет конца.
VERBATIM_MAX = 600
REF_MAX = 120
MAX_REFS = 10
MAX_EMOTIONS = 10
OPEN_ANSWER_MAX = 800

INTEREST_VALUES = ("не интересен", "скорее не интересен", "скорее интересен", "интересен")
COMPREHENSION_VALUES = ("понятно", "скорее понятно", "скорее непонятно", "непонятно")
REALISM_VALUES = (
    "реалистичные", "скорее реалистичные", "скорее нереалистичные", "нереалистичные",
)

BASE_KEYS = ("overall_impression", "plot", "acting", "music", "cinematography")


def _literal(values: tuple[str, ...] | list[str]) -> Any:
    """`Literal["a", "b"]` из значений, известных только в рантайме."""
    return Literal[tuple(values)]  # type: ignore[valid-type]


def _field_for(question: dict[str, Any], row: dict[str, Any] | None = None) -> tuple[Any, Any]:
    """
    Тип одного поля ответа: (аннотация, Field).

    Матричная строка описывается СВОИМИ вариантами, а при их отсутствии —
    общими у вопроса. Так вопрос 9 заказчика (один список на сорок три подтемы)
    и своя матрица оператора (свой список у каждого вопроса темы) описываются
    одним правилом, и схема ответа не разрешает ответить на вопрос вариантом
    соседнего.
    """
    qtype = str(question.get("type") or "open")
    label = str(row.get("label") if row else question.get("label") or "")

    if qtype == "scale":
        low = int(question.get("scaleMin", 0))
        high = int(question.get("scaleMax", 10))
        return Annotated[int, Field(ge=low, le=high, description=label)], ...

    if qtype == "open":
        return Annotated[str, Field(max_length=OPEN_ANSWER_MAX, description=label)], ...

    ids = [str(o.get("id")) for o in row_options(question, row) if o.get("id")]
    if not ids:
        # Закрытый вопрос без вариантов невалиден по схеме анкеты, но схема
        # ответа не то место, где об этом сообщать: упасть здесь значило бы
        # уронить прогон вместо внятного отказа валидатора.
        return Annotated[str, Field(max_length=OPEN_ANSWER_MAX, description=label)], ...

    if qtype == "matrix_single" and row_max_choices(question, row) > 1:
        cap = row_max_choices(question, row)
        return (
            Annotated[
                list[_literal(ids)],
                Field(min_length=1, max_length=cap, description=label),
            ],
            ...,
        )

    if qtype == "multi_choice":
        cap = int(question.get("maxChoices") or len(ids))
        return (
            Annotated[
                list[_literal(ids)],
                Field(min_length=1, max_length=cap, description=label),
            ],
            ...,
        )

    return Annotated[_literal(ids), Field(description=label)], ...


class Verbatims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    why_impression: Annotated[str, Field(max_length=VERBATIM_MAX)]
    memorable_elements: Annotated[str, Field(max_length=VERBATIM_MAX)]
    character_opinions: Annotated[str, Field(max_length=VERBATIM_MAX)]


class Perception(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interest_level: _literal(INTEREST_VALUES)  # type: ignore[valid-type]
    emotions_evoked: Annotated[list[str], Field(max_length=MAX_EMOTIONS)]
    idea_comprehension: _literal(COMPREHENSION_VALUES)  # type: ignore[valid-type]
    realism_perception: _literal(REALISM_VALUES)  # type: ignore[valid-type]
    retention_intent: _literal(RETENTION_VALUES)  # type: ignore[valid-type]
    #: Необязательное с 17.09.2026: вопрос о доле просмотра вышел из
    #: обязательной анкеты по решению владельца. `None` — «не спрашивали», и
    #: это законный ответ, а не пропуск.
    watched_share_pct: int | None
    recommendation_nps_1_to_10: Annotated[int, Field(ge=1, le=10)]


def build_answer_model(questions: Any) -> type[BaseModel]:
    """Модель ответа для КОНКРЕТНОЙ анкеты."""
    fields: dict[str, Any] = {}
    for question in survey_questions(questions):
        qid = str(question.get("id") or "").strip()
        if not qid:
            continue
        rows = question_rows(question)
        if rows:
            for row in rows:
                rid = str(row.get("id") or "").strip()
                if rid:
                    fields[rid] = _field_for(question, row)
        else:
            fields[qid] = _field_for(question)

    answers = create_model(
        "SurveyAnswers", __config__=ConfigDict(extra="forbid"), **fields
    )

    scores = create_model(
        "Scores",
        __config__=ConfigDict(extra="forbid"),
        **{key: (Annotated[int, Field(ge=0, le=10)], ...) for key in BASE_KEYS},
    )

    return create_model(
        "PersonaAnswer",
        __config__=ConfigDict(extra="forbid"),
        scores=(scores, ...),
        perception=(Perception, ...),
        survey_answers=(answers, ...),
        verbatims=(Verbatims, ...),
        grounding_refs=(
            Annotated[list[Annotated[str, Field(max_length=REF_MAX)]], Field(max_length=MAX_REFS)],
            ...,
        ),
    )


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    """
    Разворачивает `$ref` на месте.

    Провайдеры поддерживают `$defs` неодинаково, а главное — схема со ссылками
    не читается глазами при разборе отказа. Здесь она самодостаточна.
    """
    if isinstance(node, list):
        return [_inline(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        return _inline(defs[ref.split("/")[-1]], defs)
    return {k: _inline(v, defs) for k, v in node.items() if k != "$defs"}


def _strict(node: Any) -> Any:
    """
    Приводит к тому, чего требует `strict: true`.

    У OpenAI-совместимого endpoint это не рекомендация: объект, где не закрыты
    дополнительные поля или `required` не совпадает с `properties`, отвергается
    целиком. Выглядит это как отказ провайдера на первой же персоне.

    Здесь же снимается `anyOf` вокруг необязательных полей: pydantic пишет
    `int | None` как `anyOf`, а строгий режим ждёт `type: [..., "null"]`.
    """
    if isinstance(node, list):
        return [_strict(item) for item in node]
    if not isinstance(node, dict):
        return node

    out = {k: _strict(v) for k, v in node.items()}

    variants = out.get("anyOf")
    if isinstance(variants, list) and len(variants) == 2:
        kinds = [v.get("type") for v in variants if isinstance(v, dict)]
        if "null" in kinds:
            other = next(v for v in variants if isinstance(v, dict) and v.get("type") != "null")
            out = {k: v for k, v in out.items() if k != "anyOf"}
            out.update(other)
            out["type"] = [str(other.get("type")), "null"]

    if out.get("type") == "object" and "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out["properties"].keys())
    return out


def answer_json_schema(questions: Any) -> dict[str, Any]:
    """JSON Schema ответа для этой анкеты — самодостаточная и строгая."""
    model = build_answer_model(questions)
    raw = model.model_json_schema()
    return _strict(_inline(raw, raw.get("$defs") or {}))
