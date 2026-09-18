"""
Допрос персоны в чате обязан оставлять место рассуждению.

─── Что было видно 18.09.2026 ───────────────────────────────────────────────
«Обсуждения пока не работают. И обсудить с персонами, а не аналитиком».

Воспроизведено на прогоне 0093: аналитик отвечает и стримит прозу, персона
возвращает `{"answer": ""}` без единого куска текста. Прямой вызов с тем же
отрендеренным промптом (25 601 символ) даёт `finish_reason: length` при
`completion_tokens: 1200` — то есть ровно потолок.

Причина та же, что у ответа персоны в прогоне, и ровно поэтому её не заметили:
`respondent` — единственная роль с ВКЛЮЧЁННЫМ размышлением, а рассуждение
считается теми же токенами вывода (замер 4738–4844 против 581–622 без него). У
чата свой потолок, 1200 на все роли, и он не знал про размышление вовсе.

Аналитик работал именно потому, что у его роли размышление выключено: все 1200
токенов уходили в прозу.

Потолок здесь связан с размышлением ЯВНО, а не подобран числом: выключат
размышление в настройках — потолок опустится сам, и никто не будет платить за
запас, которым не пользуются.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.chat import client as chat_client  # noqa: E402
from agent_core.config import ModelConfig  # noqa: E402


class _Config:
    api_key = "test"
    base_url = "http://model.invalid/v1"
    default_headers: dict[str, str] = {}
    text_model = "Qwen/Qwen3.6-35B-A3B"

    def __init__(self, thinking_for: set[str]):
        self._thinking = thinking_for

    def extra_body(self, role: str) -> dict[str, object]:
        if role in self._thinking:
            return {}
        return {"chat_template_kwargs": {"enable_thinking": False}}

    def thinking_enabled(self, role: str) -> bool:
        kwargs = self.extra_body(role).get("chat_template_kwargs") or {}
        return bool(kwargs.get("enable_thinking", True))


def _capturing(monkeypatch):
    captured: dict[str, object] = {}

    def llm_client(**_kwargs):
        def create(**kwargs):
            captured.update(kwargs)
            return iter(())

        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    from agent_core import tracing

    monkeypatch.setattr(tracing, "llm_client", llm_client)
    return captured


def test_persona_gets_room_for_reasoning(monkeypatch) -> None:
    captured = _capturing(monkeypatch)
    cfg = _Config(thinking_for={"respondent"})

    list(chat_client.stream_reply(system="", user="вопрос", mode="persona", config=cfg))

    ceiling = captured["max_tokens"]
    assert ceiling >= 5000, (
        f"потолок {ceiling} не вмещает рассуждение: замер дал 4738–4844 токена, "
        f"и при 1200 персона возвращала пустой ответ"
    )


def test_analyst_ceiling_stays_small(monkeypatch) -> None:
    """Аналитику запас не нужен: у его роли размышление выключено."""
    captured = _capturing(monkeypatch)
    cfg = _Config(thinking_for={"respondent"})

    list(chat_client.stream_reply(system="", user="вопрос", mode="analyst", config=cfg))

    assert captured["max_tokens"] == chat_client.REPLY_TOKENS


def test_ceiling_follows_the_setting_not_a_guess(monkeypatch) -> None:
    """Выключили размышление персоне — потолок опустился сам."""
    captured = _capturing(monkeypatch)
    cfg = _Config(thinking_for=set())

    list(chat_client.stream_reply(system="", user="вопрос", mode="persona", config=cfg))

    assert captured["max_tokens"] == chat_client.REPLY_TOKENS


def test_model_config_answers_about_thinking() -> None:
    """
    Предикат живёт на конфигурации, а не пересобирается по месту: правило
    «настройки арендатора главнее умолчания по ролям» записано один раз.
    """
    cfg = ModelConfig(
        api_key="x", base_url="y", text_model="m",
        vlm_base_url="y", vlm_model="m", proxy_source="test",
        thinking_roles=frozenset({"respondent"}),
    )
    assert cfg.thinking_enabled("respondent") is True
    assert cfg.thinking_enabled("analytics") is False
