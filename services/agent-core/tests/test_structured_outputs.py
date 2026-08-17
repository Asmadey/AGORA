"""
Модель отвечает по схеме, а не прозой.

─── Что было ────────────────────────────────────────────────────────────────
Ни `response_format`, ни `json_schema` не использовались нигде. Формат ответа
описывался словами в промпте, а ответ разбирался вручную: снять ```json,
попробовать `json.loads`, при неудаче — положить ВЕСЬ текст модели в поле
`scene_description` под флагом `parse_failed`.

То есть модель могла «поболтать в ответ», и её болтовня уезжала в таймлайн,
который видит персона, — под видом описания сцены. Судья потом сверял ответ
персоны с этой болтовнёй и признавал его заземлённым.

─── Почему schema, а не проверка после ──────────────────────────────────────
Проверка после факта ловит дефект, уже оплаченный вызовом, и оставляет вопрос
«что делать»: повторять (дороже) или пропускать (дыра в материале). Схема со
`strict: true` делает неправильный ответ невозможным на стороне провайдера —
токены просто не сэмплируются вне грамматики.

Поддержка проверена на боевом endpoint 17.08.2026: обе модели вернули все восемь
полей на провокацию «Как дела?». Запасной путь `guided_json` там же оказался
пустышкой — параметр молча игнорируется, — и потому его здесь нет: путь,
который выглядит работающим и ничего не делает, хуже отсутствующего.

─── Что проверяется ─────────────────────────────────────────────────────────
Схема, отвергнутая провайдером, роняет прогон ПОСЛЕ расшифровки и разбора
кадров — то есть в самом дорогом месте. Поэтому правила строгого режима
проверяются здесь, на сборке, а не выясняются в бою.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_core.schemas.responses import (
    FRAME_ANALYSIS,
    JUDGE_SCHEMAS,
    RESPONDENT,
    assert_strict,
    response_format,
)

REPO = Path(__file__).resolve().parents[3]

ALL_SCHEMAS = {
    "frame_analysis": FRAME_ANALYSIS,
    "respondent": RESPONDENT,
    **{f"judge:{k}": v for k, v in JUDGE_SCHEMAS.items()},
}


# ─── Правила строгого режима ─────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(ALL_SCHEMAS))
def test_schema_satisfies_strict_mode(name: str):
    """
    Каждая схема обязана быть валидной для `strict: true`.

    Правила провайдера: у каждого объекта `additionalProperties: false`, и КАЖДОЕ
    свойство перечислено в `required`. Нарушение — отказ 400 посреди прогона.
    """
    assert_strict(ALL_SCHEMAS[name])


def test_assert_strict_actually_catches_violations():
    """
    Проверка обязана ловить нарушения, а не проходить на всём подряд.

    Без этого случая `assert_strict` могла бы оказаться пустой функцией, и все
    проверки выше были бы зелёными ни о чём.
    """
    missing_required = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        "required": ["a"],
    }
    with pytest.raises(ValueError, match="required"):
        assert_strict(missing_required)

    open_object = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
    }
    with pytest.raises(ValueError, match="additionalProperties"):
        assert_strict(open_object)


def test_no_free_form_maps_anywhere():
    """
    Словарь с произвольными ключами в строгом режиме невыразим.

    `additionalProperties: false` и «ключи заранее неизвестны» — противоречие.
    Именно поэтому ответы на анкету едут списком пар, а не объектом
    «идентификатор → ответ»: последний пришлось бы объявить открытым, а открытый
    объект отвергнет провайдер.
    """
    def walk(node: object, path: str = "") -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and node.get("additionalProperties") is not False:
                raise AssertionError(f"открытый объект в {path or 'корне'}")
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    for name, schema in ALL_SCHEMAS.items():
        walk(schema, name)


# ─── Форма конверта ──────────────────────────────────────────────────────────


def test_response_format_envelope():
    """Конверт — тот, что понимает OpenAI-совместимый endpoint."""
    envelope = response_format("SceneAnalysis", FRAME_ANALYSIS)

    assert envelope["type"] == "json_schema"
    assert envelope["json_schema"]["name"] == "SceneAnalysis"
    assert envelope["json_schema"]["strict"] is True
    assert envelope["json_schema"]["schema"] is FRAME_ANALYSIS


# ─── Состав полей ────────────────────────────────────────────────────────────


def test_frame_analysis_keeps_the_fields_the_timeline_reads():
    """
    Схема не должна потерять поля, на которых стоит таймлайн.

    `scene_description` читает `content/pack.py`, `mood` — карточка сцены. Схема,
    забывшая поле, отрежет его молча: модель физически не сможет его вернуть, а
    выглядеть это будет как «модель не описала».
    """
    props = FRAME_ANALYSIS["properties"]
    for field in ("timestamp", "scene_description", "actions", "mood", "setting"):
        assert field in props, f"схема разбора кадра потеряла поле {field}"


def test_respondent_answers_are_a_list_of_pairs():
    """
    Ответы анкеты — список пар, а не словарь.

    Причина в строгом режиме (см. выше), но следствие содержательное: у пары
    есть место и под идентификатор вопроса, и под его текст, а промпт разрешает
    персоне отвечать любым из двух.
    """
    answers = RESPONDENT["properties"]["survey_answers"]
    assert answers["type"] == "array"
    item = answers["items"]
    assert set(item["required"]) == {"question", "answer"}


# ─── Схема не ходит без потолка токенов ──────────────────────────────────────


def test_every_schema_has_a_token_ceiling():
    """
    У каждой схемы объявлен потолок вывода.

    Замер на боевом ключе: один и тот же запрос ответа персоны без схемы занял
    1.6 секунды и 121 токен, со схемой без потолка — 214 секунд и 32768 токенов,
    то есть предел контекста. Ответ при этом оборвался на полуслове и JSON'ом не
    являлся: схема без потолка не просто медленнее отсутствия схемы, она
    БЕСПОЛЕЗНЕЕ — гарантирует форму, которую сама же не даёт дописать.

    Причина в грамматике: массивы (`survey_answers`, `grounding_refs`,
    `actions`) не ограничены по длине, и модель выдаёт их элементы, пока есть
    куда. На клиенте это выглядело зависанием — 214 секунд больше таймаута в
    120, и узел уходил в круг повторов.
    """
    from agent_core.schemas.responses import MAX_TOKENS

    assert set(MAX_TOKENS) == {"frame_analysis", "respondent", "judge", "persona_validation"}
    for role, ceiling in MAX_TOKENS.items():
        assert 200 <= ceiling <= 16000, f"{role}: потолок {ceiling} вне разумного"

    # Респондент — единственная роль с включённым размышлением, и оно считается
    # теми же токенами вывода: замер дал 4738–4844 против 581–622 без него.
    # Потолок, равный соседним, обрезал бы ответ посередине рассуждения — так и
    # вышло, восемь ответов из двенадцати.
    from dataclasses import fields

    from agent_core.config import ModelConfig

    # Связь названа явно: потолок велик ПОТОМУ ЧТО у роли включено размышление.
    # Уберут размышление — этот assert напомнит, что потолок можно снизить.
    default_thinking = next(
        f.default for f in fields(ModelConfig) if f.name == "thinking_roles"
    )
    assert "respondent" in default_thinking, (
        "у респондента выключили размышление — потолок в MAX_TOKENS можно снижать"
    )
    assert MAX_TOKENS["respondent"] >= 3 * max(
        MAX_TOKENS["frame_analysis"], MAX_TOKENS["judge"], MAX_TOKENS["persona_validation"]
    ), "потолок респондента обязан вмещать рассуждение, а не только ответ"


def test_truncated_answer_is_named_as_truncated():
    """
    Обрыв по потолку сообщается отдельно от плохого ответа.

    Три сквозных прогона подряд упали с двенадцатью отказами «ответ не
    разобран». Причина была в потолке — 2000 токенов при расходе 1331–1783, —
    но по сообщению этого понять было нельзя: обрезанный JSON и плохой JSON
    ломаются одинаково. Диагноз пришлось добывать, воспроизводя запрос вручную,
    хотя провайдер сообщает его сам полем `finish_reason`.
    """
    from agent_core.schemas.responses import content_of

    class Truncated:
        choices = [type("C", (), {
            "finish_reason": "length",
            "message": type("M", (), {"content": '{"scores": {"overall'})(),
        })()]
        usage = type("U", (), {"completion_tokens": 2000})()

    with pytest.raises(ValueError, match="оборван потолком"):
        content_of(Truncated(), role="respondent")


def test_complete_answer_passes_through():
    """Законченный ответ возвращается как есть, без лишних проверок."""
    from agent_core.schemas.responses import content_of

    class Complete:
        choices = [type("C", (), {
            "finish_reason": "stop",
            "message": type("M", (), {"content": '  {"ok": true}  '})(),
        })()]
        usage = type("U", (), {"completion_tokens": 12})()

    assert content_of(Complete(), role="respondent") == '{"ok": true}'


def test_respondent_goes_without_a_schema():
    """
    У ответа персоны строгой схемы НЕТ, и это решение по замеру.

    Замер на двенадцати боевых персонах, один и тот же промпт, температура 0.3,
    бок о бок:

        со схемой   8 из 12 разобрано
        без схемы  12 из 12 разобрано

    Четыре ответа вырождались под грамматикой: модель залипала на пробельных
    токенах либо на счётчике внутри строки и шла до потолка, не дописав JSON.
    Цена блуждания здесь максимальна — теряется не поле, а весь оплаченный
    ответ.

    Тест стоит затем, чтобы схему не вернули «для единообразия»: соседние роли
    её используют, и отсутствие здесь выглядит недоделкой, а не выводом.
    Схема `RESPONDENT` при этом остаётся в модуле — она описывает форму ответа
    и годится для проверок, просто не уезжает в запрос.
    """
    source = (
        REPO / "services" / "agent-core" / "agent_core" / "respondent" / "run.py"
    ).read_text("utf-8")

    assert "response_format" not in source, (
        "строгая схема вернулась в ответ персоны: замер показал 8 из 12 против "
        "12 из 12 без неё — четыре ответа теряются на вырождении грамматики"
    )
    # Потолок при этом обязан остаться: он ограничивает и обычную генерацию.
    assert "max_tokens" in source


def test_schema_and_ceiling_are_passed_together():
    """
    Каждый вызов со схемой передаёт и потолок.

    Проверка по исходникам, а не по вызову: клиенты ходят в сеть, и поймать
    здесь можно только то, что видно в коде. Ищется связка — `response_format`
    без `max_tokens` рядом означает повторение ровно того дефекта, который стоил
    зависшего прогона.
    """
    core = REPO / "services" / "agent-core" / "agent_core"
    offenders: list[str] = []
    for path in core.rglob("*.py"):
        source = path.read_text("utf-8")
        if "response_format=" not in source:
            continue
        # Грубо, но по делу: оба ключа обязаны встречаться в одном файле, и
        # число вхождений response_format не должно превышать max_tokens.
        if source.count("response_format=") > source.count("max_tokens"):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"схема без потолка токенов: {offenders}"


# ─── Приведение ответов анкеты ───────────────────────────────────────────────
#
# Схема заставляет модель отвечать списком пар, а всё ниже по течению — правила
# покрытия в qa/checks.py, карточка персоны в отчёте — читает словарь. Стык
# закрыт одной функцией сразу после разбора; здесь проверяется, что он
# действительно закрыт, а не что кто-то ниже «тоже умеет список».


def test_list_of_pairs_becomes_a_map():
    """Список пар приводится к словарю «вопрос → ответ»."""
    from agent_core.respondent.run import parse_answer

    parsed = parse_answer(
        '{"survey_answers": [{"question": "base-6", "answer": "60"},'
        ' {"question": "Что запомнилось", "answer": "заставка"}]}'
    )

    assert parsed["survey_answers"] == {"base-6": "60", "Что запомнилось": "заставка"}


def test_old_map_format_still_works():
    """
    Словарь на входе принимается как есть.

    Так отвечали персоны до перехода на схему, и перезапуск прежнего прогона
    (#30) не должен падать на формате, который сам же и сохранил.
    """
    from agent_core.respondent.run import parse_answer

    parsed = parse_answer('{"survey_answers": {"base-6": "60"}}')

    assert parsed["survey_answers"] == {"base-6": "60"}


def test_missing_field_stays_missing():
    """
    Отсутствующее поле не подменяется пустым словарём.

    «Ответов нет» и «поля нет» — разные случаи, и правило покрытия их
    различает: первое означает, что персона пропустила анкету, второе — что
    ответ пришёл в неизвестном формате.
    """
    from agent_core.respondent.run import parse_answer

    assert "survey_answers" not in parse_answer('{"scores": {}}')


def test_pair_without_question_is_dropped():
    """Пара без вопроса выбрасывается: ключа у неё нет, а `None` их склеит."""
    from agent_core.respondent.run import parse_answer

    parsed = parse_answer(
        '{"survey_answers": [{"question": "", "answer": "а"},'
        ' {"question": "q-1", "answer": "б"}]}'
    )

    assert parsed["survey_answers"] == {"q-1": "б"}


@pytest.mark.parametrize("key", ["qa.consistency", "qa.grounding", "qa.diversity"])
def test_judge_schema_has_verdict_and_confidence(key: str):
    """
    У всех трёх судей общие поля — вердикт и уверенность.

    На них стоит `parse_verdict`, и профильные поля у каждого свои. Схема,
    забывшая confidence, обнулила бы эскалацию: порог сравнивать было бы не с
    чем, и все вердикты уходили бы наверх либо ни один.
    """
    props = JUDGE_SCHEMAS[key]["properties"]
    assert "verdict" in props
    assert "confidence" in props
    assert props["verdict"]["enum"] == ["ok", "regenerate"]
