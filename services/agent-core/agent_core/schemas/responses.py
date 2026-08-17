"""
Схемы ответов модели для строгого режима (Structured Outputs).

─── Зачем ───────────────────────────────────────────────────────────────────
До этого модуля формат ответа описывался словами в промпте, а ответ разбирался
вручную: снять ```json, попробовать `json.loads`, при неудаче положить ВЕСЬ
текст модели в поле описания под флагом `parse_failed`. Модель могла
«поболтать в ответ», и её болтовня уезжала в таймлайн, который видит персона.
Судья потом сверял ответ персоны с этой болтовнёй и признавал его заземлённым.

Схема со `strict: true` делает такой ответ невозможным на стороне провайдера:
токены вне грамматики просто не сэмплируются. Это отличается от проверки после
факта — та ловит дефект, уже оплаченный вызовом, и оставляет выбор между
повтором (дороже) и пропуском (дыра в материале).

─── Поддержка провайдера ────────────────────────────────────────────────────
Проверена на боевом endpoint 17.08.2026 (Cloud.ru Foundation Models): и
`Qwen/Qwen3.6-35B-A3B`, и `qwen/qwen3-vl-30b-a3b-instruct` вернули все восемь
полей пробной схемы на провокацию «Как дела?».

Запасного пути `guided_json` здесь намеренно нет: та же проба показала, что
параметр молча игнорируется — модель вернула обычную болтовню. Путь, который
выглядит работающим и ничего не делает, хуже отсутствующего.

─── Ограничение строгого режима, из которого следует форма ──────────────────
Словарь с произвольными ключами в строгом режиме невыразим: `additionalProperties
: false` и «ключи заранее неизвестны» — противоречие. Поэтому ответы персоны на
анкету едут СПИСКОМ ПАР, а не объектом «идентификатор → ответ». К словарю их
приводит `respondent/run.py` сразу после разбора, поэтому всё, что ниже по
течению — правила QA, отчёт, — устройства не заметило.
"""

from __future__ import annotations

from typing import Any


def assert_strict(schema: dict[str, Any], path: str = "") -> None:
    """
    Проверяет схему на правила строгого режима.

    Два правила, оба обязательные: у каждого объекта `additionalProperties:
    false`, и КАЖДОЕ свойство перечислено в `required`. Провайдер отвергает
    нарушение кодом 400 — и приходит этот отказ посреди прогона, после
    расшифровки и разбора кадров, то есть в самом дорогом месте. Дешевле
    убедиться на сборке.
    """
    where = path or "корень"
    if not isinstance(schema, dict):
        return

    if schema.get("type") == "object":
        if schema.get("additionalProperties") is not False:
            raise ValueError(f"{where}: у объекта нет additionalProperties: false")
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        missing = set(properties) - required
        if missing:
            raise ValueError(
                f"{where}: свойства не перечислены в required: {sorted(missing)}"
            )
        for name, sub in properties.items():
            assert_strict(sub, f"{where}.{name}")

    if schema.get("type") == "array":
        assert_strict(schema.get("items") or {}, f"{where}[]")


def response_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Конверт `response_format` для OpenAI-совместимого endpoint."""
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": True, "schema": schema},
    }


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    """Объект со всеми полями обязательными и закрытым составом."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


def _str_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


# ─── Разбор кадра ────────────────────────────────────────────────────────────
#
# Состав повторяет prompts/content.frame_analysis.md. Расхождение отрежет поле
# молча: модель физически не сможет его вернуть, а выглядеть это будет как
# «модель не описала сцену».

FRAME_ANALYSIS: dict[str, Any] = _obj({
    "timestamp": {"type": "string"},
    "scene_description": {"type": "string"},
    "actions": _str_array(),
    "characters": {
        "type": "array",
        "items": _obj({
            "appearance": {"type": "string"},
            "emotion": {"type": "string"},
        }),
    },
    "setting": {"type": "string"},
    "mood": {"type": "string"},
    "cinematography": _obj({
        "shot": {"type": "string"},
        "lighting": {"type": "string"},
        "camera": {"type": "string"},
    }),
    # Пустая строка вместо null: строгий режим требует объявить тип, а
    # ["string", "null"] поддержан не везде. «Текста на экране нет» и «поле не
    # заполнено» здесь совпадают, и различать их незачем.
    "on_screen_text": {"type": "string"},
    "notable": {"type": "string"},
})


# ─── Ответ персоны ───────────────────────────────────────────────────────────

_PERCEPTION = _obj({
    "interest_level": {"type": "string"},
    "emotions_evoked": _str_array(),
    "idea_comprehension": {"type": "string"},
    "realism_perception": {"type": "string"},
    "retention_intent": {"type": "string"},
    "watched_share_pct": {"type": "integer"},
    "recommendation_nps_1_to_10": {"type": "integer"},
})

RESPONDENT: dict[str, Any] = _obj({
    "scores": _obj({
        "overall_impression": {"type": "integer"},
        "plot": {"type": "integer"},
        "acting": {"type": "integer"},
        "music": {"type": "integer"},
        "cinematography": {"type": "integer"},
    }),
    "perception": _PERCEPTION,
    # Список пар, а не словарь — см. модульный докстринг. У пары есть место и
    # под идентификатор вопроса, и под его текст: промпт разрешает персоне
    # отвечать любым из двух, и правило покрытия принимает оба.
    "survey_answers": {
        "type": "array",
        "items": _obj({
            "question": {"type": "string"},
            "answer": {"type": "string"},
        }),
    },
    # Все три поля, а не одно: карточка ответа берёт why_impression, но при
    # пустом откатывается на первое непустое из остальных
    # (`report-view.ts:360`). Схема, забывшая их, отрезала бы этот запасной
    # путь молча — модель физически не смогла бы вернуть поле.
    "verbatims": _obj({
        "why_impression": {"type": "string"},
        "memorable_elements": {"type": "string"},
        "character_opinions": {"type": "string"},
    }),
    "grounding_refs": _str_array(),
})


# ─── Вердикты QA ─────────────────────────────────────────────────────────────
#
# Три промпта возвращают разные профильные поля; общего у них ровно два —
# verdict и confidence. На них стоит parse_verdict, и схема, забывшая
# confidence, обнулила бы эскалацию: порог сравнивать было бы не с чем.

_VERDICT = {"type": "string", "enum": ["ok", "regenerate"]}
_CONFIDENCE = {"type": "number"}

JUDGE_SCHEMAS: dict[str, dict[str, Any]] = {
    "qa.consistency": _obj({
        "consistency_score": {"type": "integer"},
        "flags": _str_array(),
        "verdict": _VERDICT,
        "confidence": _CONFIDENCE,
    }),
    "qa.grounding": _obj({
        "grounded": {"type": "boolean"},
        "hallucinations": _str_array(),
        "verdict": _VERDICT,
        "confidence": _CONFIDENCE,
    }),
    "qa.diversity": _obj({
        # score_variance в промпте — словарь «критерий → разброс», то есть
        # ровно тот случай, который строгий режим не выражает. Список пар: имя
        # критерия и число.
        "score_variance": {
            "type": "array",
            "items": _obj({
                "criterion": {"type": "string"},
                "variance": {"type": "number"},
            }),
        },
        "text_diversity": {"type": "number"},
        "collapsed": {"type": "boolean"},
        "note": {"type": "string"},
        "verdict": _VERDICT,
        "confidence": _CONFIDENCE,
    }),
}
