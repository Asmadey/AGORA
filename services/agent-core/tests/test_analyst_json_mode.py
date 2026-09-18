"""
Аналитик обязан отвечать валидным JSON и честно сообщать про обрыв.

─── Что случилось в прогоне 0093 ────────────────────────────────────────────
Отчёт остался без нарратива:

    нарратив не собран: JSONDecodeError: Expecting ',' delimiter:
    line 31 column 104 (char 3427)

Трасса LangFuse (наблюдение `build-report`, 1823 токена вывода, finish_reason
`stop`) показывает, что оборвано ничего не было. Модель написала внутри строки
JSON неэкранированную двойную кавычку:

    "Понятность идеи: … им «понятна» (idea_comprehension: "понятно"…

Строка на этой кавычке закончилась, и разбор упёрся в слово там, где ждал
запятую. По сообщению это неотличимо от обрыва по потолку — а лечится совсем
иначе.

─── Почему именно этот вызов ────────────────────────────────────────────────
Аналитик — ЕДИНСТВЕННАЯ роль, которая шла к модели без грамматики, без потолка
и мимо `content_of`. У респондента, судьи, разбора кадров и проверки персон всё
три есть. Отсюда и симптом, которого больше нигде нет.

Режим `json_object` проверен на боевом endpoint 18.09.2026: та же кавычка
внутри строки приезжает экранированной. Схема (`json_schema`) здесь не годится:
`rationales` — словарь с произвольными ключами метрик, и строгая схема с
закрытым составом полей описать его не может, не переписав контракт отчёта.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.analytics import report as report_mod  # noqa: E402
from agent_core.schemas.responses import MAX_TOKENS  # noqa: E402


class _Config:
    """Ровно то, что `complete` спрашивает у конфигурации, и ничего больше."""

    api_key = "test"
    base_url = "http://model.invalid/v1"
    default_headers: dict[str, str] = {}
    text_model = "Qwen/Qwen3.6-35B-A3B"

    def extra_body(self, _role: str) -> dict[str, object]:
        return {}


def _client_returning(content: str, finish_reason: str = "stop", completion_tokens: int = 100):
    captured: dict[str, object] = {}

    def llm_client(**_kwargs):
        def create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason=finish_reason,
                        message=SimpleNamespace(content=content),
                    )
                ],
                usage=SimpleNamespace(completion_tokens=completion_tokens),
            )

        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    return llm_client, captured


def test_analyst_asks_for_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_core import tracing

    llm_client, captured = _client_returning('{"narrative": []}')
    monkeypatch.setattr(tracing, "llm_client", llm_client)

    out = report_mod.QwenAnalystClient(config=_Config(), temperature=0.1).complete(
        system="роль", user="данные"
    )

    assert out == '{"narrative": []}'
    assert captured.get("response_format") == {"type": "json_object"}, (
        "без грамматики модель пишет сырую кавычку внутри строки — прогон 0093"
    )


def test_analyst_has_a_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Потолок ставится ВМЕСТЕ с грамматикой: см. MAX_TOKENS."""
    from agent_core import tracing

    llm_client, captured = _client_returning('{"narrative": []}')
    monkeypatch.setattr(tracing, "llm_client", llm_client)

    report_mod.QwenAnalystClient(config=_Config(), temperature=0.1).complete(
        system="роль", user="данные"
    )

    assert captured.get("max_tokens") == MAX_TOKENS["analyst"]


def test_truncated_report_is_named_as_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Обрыв по потолку обязан приходить как обрыв, а не как «битый JSON».

    Ровно ради этой разницы и написан `content_of`: в прогоне 0093 пришлось
    лезть в трассу LangFuse, чтобы понять, что потолок ни при чём.
    """
    from agent_core import tracing

    llm_client, _ = _client_returning("{\"narrative\": [", finish_reason="length",
                                      completion_tokens=MAX_TOKENS["analyst"])
    monkeypatch.setattr(tracing, "llm_client", llm_client)

    with pytest.raises(ValueError) as caught:
        report_mod.QwenAnalystClient(config=_Config(), temperature=0.1).complete(
            system="роль", user="данные"
        )

    message = str(caught.value)
    assert "потолком токенов" in message
    assert "analyst" in message, "в причине обязана стоять роль — потолков несколько"
