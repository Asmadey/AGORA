"""Тесты контракта конфигурации worker'а (задача #1).

Проверяют главное правило проекта: секреты приходят только из окружения, и отсутствие
обязательной переменной — это внятная ошибка, а не тихий дефолт.
"""
from __future__ import annotations

import pytest

from agent_core import __version__
from agent_core.config import ConfigError, ModelConfig, StorageConfig, TranscriptionConfig


def test_package_importable():
    assert __version__


def test_model_config_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        ModelConfig.from_env()


def test_model_config_defaults_to_timeweb(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.delenv("VLM_MODEL", raising=False)

    cfg = ModelConfig.from_env()

    assert cfg.base_url == "https://api.timeweb.cloud/v1"
    assert cfg.text_model == "qwen3.6"
    assert cfg.vlm_model == "qwen3.6"


def test_storage_config_requires_all_three_stores(monkeypatch):
    for var in ("DATABASE_URL", "MONGODB_URL", "VALKEY_URL"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ConfigError):
        StorageConfig.from_env()


def test_transcription_rejects_unsupported_model(monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL", "tiny")
    with pytest.raises(ConfigError, match="large-v3"):
        TranscriptionConfig.from_env()


@pytest.mark.parametrize("model", ["large-v3", "large-v3-turbo"])
def test_transcription_accepts_both_supported_models(monkeypatch, model):
    monkeypatch.setenv("WHISPER_MODEL", model)
    assert TranscriptionConfig.from_env().whisper_model == model


@pytest.mark.parametrize("model", ["large-v3", "large-v3-turbo"])
def test_transcription_for_task_uses_snapshot_over_env(monkeypatch, model):
    """Снимок настроек в задаче важнее окружения: прогон исполняется тем, что выбрал
    пользователь на момент запуска, а не тем, что стоит в compose сегодня."""
    other = "large-v3-turbo" if model == "large-v3" else "large-v3"
    monkeypatch.setenv("WHISPER_MODEL", other)
    assert TranscriptionConfig.for_task(model).whisper_model == model


def test_transcription_for_task_falls_back_to_env_when_snapshot_empty(monkeypatch):
    """Задачи, поставленные до появления настроек, обязаны остаться исполнимыми."""
    monkeypatch.setenv("WHISPER_MODEL", "large-v3-turbo")
    assert TranscriptionConfig.for_task(None).whisper_model == "large-v3-turbo"


def test_transcription_for_task_rejects_unsupported_model(monkeypatch):
    """Невалидное значение в payload не должно молча превращаться в дефолт: иначе
    отчёт утверждал бы одну модель, а транскрипция шла на другой."""
    monkeypatch.setenv("WHISPER_MODEL", "large-v3")
    with pytest.raises(ConfigError, match="payload.settings.whisper_model"):
        TranscriptionConfig.for_task("whisper-1")
