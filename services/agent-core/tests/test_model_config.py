"""
Выбор модели из настроек доезжает до запроса.

─── Что здесь стык ──────────────────────────────────────────────────────────
Настройка, которая выставляется в интерфейсе и не применяется воркером,
выглядит рабочей с обеих сторон: интерфейс её сохраняет, воркер считает по
своему умолчанию. Увидеть расхождение можно только по счёту от провайдера — или
по карточке отчёта, где написана одна модель, а считала другая.

Проверяются три вещи: имена ключей совпадают с контрактом интерфейса, пустое
значение означает «как в окружении» (а не «без модели»), и ключ провайдера в
снимок не попадает ни при каких условиях.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agent_core.config import ModelConfig

REPO = Path(__file__).resolve().parents[3]
SETTINGS_TS = REPO / "apps" / "web" / "lib" / "settings.ts"


def base_config() -> ModelConfig:
    return ModelConfig(
        api_key="sk-секрет",
        base_url="https://env.example/v1",
        vlm_base_url="https://env.example/v1",
        text_model="env-text",
        vlm_model="env-vision",
        proxy_source="agora",
    )


# ─── Стык с интерфейсом ──────────────────────────────────────────────────────


def test_model_roles_match_the_web_contract():
    """
    Роли моделей названы одинаково по обе стороны.

    Интерфейс кладёт в снимок `models: {text, vision, judge}`. Разойдясь на одну
    букву, стороны дадут выбор, который сохраняется и не применяется.
    """
    source = SETTINGS_TS.read_text("utf-8")
    block = source.split("export interface ModelSelection", 1)[1].split("}", 1)[0]
    roles = set(re.findall(r"^\s*(\w+):", block, re.M))

    assert roles == {"text", "vision", "judge"}


def test_reasoning_efforts_match_the_web_contract():
    """Список усилий совпадает: интерфейс не должен уметь выбрать неизвестное."""
    source = SETTINGS_TS.read_text("utf-8")
    block = source.split("REASONING_EFFORTS = [", 1)[1].split("]", 1)[0]
    efforts = set(re.findall(r'"(\w+)"', block))

    config = ModelConfig.for_task({"reasoning": {"effort": "nonsense"}}, base_config())
    assert efforts == {"low", "medium", "high", "max"}
    # Неизвестное значение отбрасывается молча: воркер читает снимок посреди
    # прогона, и падать здесь значит терять оплаченную расшифровку.
    assert "effort" not in config.reasoning


# ─── Выбор применяется ───────────────────────────────────────────────────────


def test_snapshot_models_win_over_environment():
    config = ModelConfig.for_task(
        {"models": {"text": "выбранная-текст", "vision": "выбранная-зрение"}},
        base_config(),
    )

    assert config.text_model == "выбранная-текст"
    assert config.vlm_model == "выбранная-зрение"


def test_empty_choice_means_environment_not_absence():
    """
    Пустая строка — «как в окружении», а не «без модели».

    Так выглядят все прогоны до первого захода в настройки. Трактовать пустоту
    как отсутствие значило бы уронить их все.
    """
    config = ModelConfig.for_task({"models": {"text": "", "vision": "  "}}, base_config())

    assert config.text_model == "env-text"
    assert config.vlm_model == "env-vision"


def test_judge_falls_back_to_the_text_model():
    """Судья без своего выбора судит тем же, чем отвечали."""
    assert ModelConfig.for_task({}, base_config()).judge_model_or_text == "env-text"
    chosen = ModelConfig.for_task({"models": {"judge": "судья"}}, base_config())
    assert chosen.judge_model_or_text == "судья"


def test_endpoint_from_snapshot():
    config = ModelConfig.for_task({"endpoint": "https://другой/v1"}, base_config())
    assert config.base_url == "https://другой/v1"


# ─── Рассуждение ─────────────────────────────────────────────────────────────


def test_settings_reasoning_beats_role_default():
    """
    Настройка арендатора главнее умолчания по ролям.

    `thinking_roles` описывает, где размышление полезно вообще; настройка — чего
    хочет команда. Иначе переключатель в интерфейсе ничего не менял бы для
    ролей, попавших в умолчание.
    """
    config = ModelConfig.for_task(
        {"reasoning": {"thinking": True, "effort": "low"}}, base_config()
    )
    body = config.extra_body("frames")

    assert body["chat_template_kwargs"]["enable_thinking"] is True
    assert body["chat_template_kwargs"]["reasoning_effort"] == "low"


def test_judge_reasoning_is_separate():
    """У судьи свой режим: цена ошибки проверки другая."""
    config = ModelConfig.for_task(
        {
            "reasoning": {"thinking": True},
            "judgeReasoning": {"thinking": False},
        },
        base_config(),
    )

    assert config.extra_body("respondent")["chat_template_kwargs"]["enable_thinking"] is True
    assert config.extra_body("qa")["chat_template_kwargs"]["enable_thinking"] is False


def test_thinking_uses_the_key_that_works():
    """
    Ключ именно `enable_thinking`.

    Замер на боевом endpoint 17.08.2026: `thinking: false` шлюз ИГНОРИРУЕТ — 480
    токенов вывода против 4 при `enable_thinking: false`. Переключатель,
    повешенный на ключ из документации провайдера, был бы ручкой, которая ничего
    не крутит.
    """
    body = ModelConfig.for_task({"reasoning": {"thinking": False}}, base_config()).extra_body(
        "respondent"
    )

    assert "enable_thinking" in body["chat_template_kwargs"]
    assert "thinking" not in body["chat_template_kwargs"]


# ─── Секрет не размножается ──────────────────────────────────────────────────


def test_snapshot_never_carries_the_api_key():
    """
    Ключ провайдера в снимок задачи не попадает.

    Снимок живёт столько же, сколько отчёт, и копия ключа в каждой строке
    `tasks` — это секрет, размноженный по резервным копиям базы без единого
    способа его отозвать. Проверяется по исходнику веба: именно он собирает
    снимок.
    """
    source = (REPO / "apps" / "web" / "lib" / "server" / "tasks.ts").read_text("utf-8")
    snapshot_block = source.split("function pickProvider", 1)[1].split("\n}", 1)[0]

    # Проверяется СПИСОК копируемых полей, а не отсутствие слова «key»: первая
    # редакция теста искала подстроку и срабатывала на имени переменной цикла.
    # Белый список строже: чтобы протащить секрет, его придётся сюда вписать,
    # и тест это заметит.
    copied = set(re.findall(r'"(\w+)"', snapshot_block))

    assert copied == {"models", "reasoning", "judgeReasoning", "endpoint"}, (
        f"состав снимка изменился: {sorted(copied)}. Ключ провайдера сюда попасть "
        f"не должен — снимок живёт столько же, сколько отчёт"
    )


def test_config_repr_does_not_leak_the_key():
    """
    Ключ не должен попадать в текст исключения или лога через repr конфигурации.

    Дефект такого рода не виден в коде: он проявляется в тот день, когда кто-то
    добавит `logger.error(f"…{config}")`, — и ключ уедет в журнал навсегда.
    """
    with pytest.raises(ValueError) as exc:
        base_config().extra_body("несуществующая-роль")

    assert "sk-секрет" not in str(exc.value)
