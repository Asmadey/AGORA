"""
Корпус, схемы строгого режима и портреты сегментов.

─── Почему эти три вместе ────────────────────────────────────────────────────
Все трое молчат, когда ошибаются.

Из корпуса считаются доли, по которым сэмплируются персоны. Битая запись,
проглоченная разбором, сдвигает доли — и аудитория получается не той, но
выглядит совершенно нормальной: двадцать связных портретов, просто из другого
среза.

Схемы строгого режима отвергаются провайдером кодом 400, и приходит этот отказ
посреди оплаченного прогона — после расшифровки и разбора кадров. Проверить их
можно на сборке, и это дешевле на порядок.

Портрет без ключа провайдера обязан вернуть None, а не упасть: детерминированный
портрет остаётся полезным, и терять из-за него весь прогон незачем.
"""

from __future__ import annotations

import pytest

from agent_core.schemas.responses import assert_strict, content_of, response_format

# ─────────────────────────────────────────────────────────────────────────
# Строгий режим: схема, которую провайдер примет
# ─────────────────────────────────────────────────────────────────────────

def test_strict_object_needs_additional_properties_false():
    with pytest.raises(ValueError, match="additionalProperties"):
        assert_strict({"type": "object", "properties": {"a": {"type": "string"}},
                       "required": ["a"]})


def test_every_property_must_be_required():
    """
    Правило строгого режима, о котором забывают чаще всего: перечислены обязаны
    быть ВСЕ свойства, а не только обязательные по смыслу. Провайдер отвергает
    нарушение четырёхсотым — посреди прогона.
    """
    with pytest.raises(ValueError, match="required"):
        assert_strict({
            "type": "object",
            "additionalProperties": False,
            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
            "required": ["a"],
        })


def test_error_names_the_path_not_just_the_fact():
    """
    «Схема неверна» не говорит, где именно. Путь в сообщении — разница между
    «поправил за минуту» и «ищу глазами в трёхэтажном JSON».
    """
    schema = {
        "type": "object", "additionalProperties": False, "required": ["outer"],
        "properties": {
            "outer": {
                "type": "object", "properties": {"inner": {"type": "string"}},
                "required": ["inner"],
            }
        },
    }
    with pytest.raises(ValueError, match=r"outer"):
        assert_strict(schema)


def test_arrays_are_checked_through_their_items():
    schema = {
        "type": "array",
        "items": {"type": "object", "properties": {"a": {"type": "string"}},
                  "required": ["a"]},
    }
    with pytest.raises(ValueError, match=r"\[\]"):
        assert_strict(schema)


def test_valid_schema_passes():
    # Ничего не возвращает и ничего не бросает — этого и достаточно: функция
    # существует ради исключения, а не ради значения.
    assert_strict({
        "type": "object", "additionalProperties": False,
        "properties": {"a": {"type": "string"}}, "required": ["a"],
    })


def test_response_format_carries_the_schema():
    schema = {"type": "object", "additionalProperties": False,
              "properties": {"a": {"type": "string"}}, "required": ["a"]}
    envelope = response_format("Answer", schema)
    assert envelope["type"] == "json_schema"
    assert envelope["json_schema"]["name"] == "Answer"
    assert envelope["json_schema"]["schema"] == schema


# ─────────────────────────────────────────────────────────────────────────
# Разбор ответа модели
# ─────────────────────────────────────────────────────────────────────────

class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Message(content)


class _Response:
    def __init__(self, content):
        self.choices = [_Choice(content)]


def test_content_is_extracted():
    assert content_of(_Response("готово"), role="respondent") == "готово"


def test_empty_content_is_an_empty_string_not_a_crash():
    """
    Пустой ответ — законное значение: в дорожке может не быть речи, персона
    может отказаться отвечать. Разбор выше по течению сам решит, что с этим
    делать; исключение здесь отобрало бы у него это решение.

    Первая редакция теста требовала здесь отказа — и была неправа: отказ у
    `content_of` другой, см. следующий случай.
    """
    assert content_of(_Response(None), role="respondent") == ""


def test_truncated_answer_is_a_named_failure_not_a_bad_answer():
    """
    Главное, ради чего эта функция вообще есть.

    Ответ, обрезанный потолком токенов, неотличим от плохого: и там, и там
    `json.loads` падает, и причина приходит как «ответ не разобран». Три прогона
    подряд упали с двенадцатью такими отказами, и по сообщению нельзя было
    понять, что дело в потолке — пришлось воспроизводить запрос вручную.

    Провайдер сообщает разницу сам, в `finish_reason`. Сообщение обязано
    называть роль и потолок: без них диагноз снова придётся добывать заново.
    """
    class _Truncated:
        class _C:
            finish_reason = "length"
            message = _Message('{"verdict": "o')

        choices = [_C()]

        class usage:  # noqa: N801
            completion_tokens = 512

    with pytest.raises(ValueError, match="потолк"):
        content_of(_Truncated(), role="respondent")

    try:
        content_of(_Truncated(), role="respondent")
    except ValueError as e:
        assert "respondent" in str(e), f"в сообщении нет роли: {e}"
        assert "512" in str(e), f"в сообщении нет израсходованного: {e}"


# ─────────────────────────────────────────────────────────────────────────
# Портрет сегмента
# ─────────────────────────────────────────────────────────────────────────

def test_portrait_without_api_key_returns_none(monkeypatch):
    """
    Без ключа провайдера — None, а не исключение. Вызывающий откатывается на
    детерминированный портрет, и он остаётся полезным; уронить из-за него весь
    прогон значило бы потерять уже оплаченные расшифровку и разбор кадров.
    """
    from agent_core.portraits import distill

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)

    assert distill.distill_portrait_llm(
        records=[],
        segment_key="age:25-34",
        prompt_template="шаблон",
        api_key=None,
        base_url=None,
        model=None,
    ) is None


def test_portrait_without_base_url_returns_none(monkeypatch):
    """
    Ключ есть, адреса нет. Умолчаний здесь нет намеренно: зашитый адрес пережил
    смену провайдера и указывал в пустоту — прогон шёл, вызовы уходили в никуда.
    """
    from agent_core.portraits import distill

    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)

    assert distill.distill_portrait_llm(
        records=[],
        segment_key="age:25-34",
        prompt_template="шаблон",
        api_key="ключ",
        base_url=None,
        model=None,
    ) is None
