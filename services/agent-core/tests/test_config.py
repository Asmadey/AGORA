"""Тесты контракта конфигурации worker'а (задача #1).

Проверяют главное правило проекта: секреты приходят только из окружения, и отсутствие
обязательной переменной — это внятная ошибка, а не тихий дефолт.
"""
from __future__ import annotations

import pytest

from agent_core import __version__
from agent_core.config import (
    DIARIZATION_PIPELINES,
    ConfigError,
    DiarizationConfig,
    ModelConfig,
    StorageConfig,
    TranscriptionConfig,
)


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


# ─── Провайдер моделей: агент TimeWeb ─────────────────────────────────────

def test_model_config_sends_required_proxy_header(monkeypatch):
    """x-proxy-source помечен required в OpenAPI провайдера; SDK его не шлёт.
    Без заголовка запрос отклоняется до модели, поэтому он часть конфигурации."""
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert ModelConfig.from_env().default_headers == {"x-proxy-source": "agora"}


def test_vlm_falls_back_to_same_agent(monkeypatch):
    """Один агент = одна модель. Пустой VLM_BASE_URL означает общий агент —
    и это должно быть видно в конфигурации, а не выясняться по счёту."""
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://agent.timeweb.cloud/api/v1/cloud-ai/agents/abc/v1")
    monkeypatch.delenv("VLM_BASE_URL", raising=False)
    cfg = ModelConfig.from_env()
    assert cfg.vlm_base_url == cfg.base_url
    assert cfg.vlm_shares_agent is True


def test_separate_vlm_agent_is_detected(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://agent.timeweb.cloud/api/v1/cloud-ai/agents/text/v1")
    monkeypatch.setenv("VLM_BASE_URL", "https://agent.timeweb.cloud/api/v1/cloud-ai/agents/vision/v1")
    assert ModelConfig.from_env().vlm_shares_agent is False


# ─── Диаризация: pyannote на своём железе ─────────────────────────────────

def test_diarization_requires_hf_token(monkeypatch):
    """Веса закрыты принятием условий на HF — без токена загрузка вернёт 401."""
    monkeypatch.delenv("PYANNOTE_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="PYANNOTE_TOKEN"):
        DiarizationConfig.from_env()


def test_diarization_rejects_hosted_premium_pipeline(monkeypatch):
    """precision-2 исполняется на серверах pyannoteAI. Для self-host-продукта это
    молчаливая передача пользовательского аудио третьей стороне."""
    monkeypatch.setenv("PYANNOTE_TOKEN", "hf_x")
    monkeypatch.setenv("DIARIZATION_PIPELINE", "pyannote/speaker-diarization-precision-2")
    with pytest.raises(ConfigError, match="self-host"):
        DiarizationConfig.from_env()


def test_diarization_telemetry_off_by_default(monkeypatch):
    """pyannote.audio 4.x включает телеметрию по умолчанию."""
    monkeypatch.setenv("PYANNOTE_TOKEN", "hf_x")
    monkeypatch.delenv("PYANNOTE_METRICS_ENABLED", raising=False)
    assert DiarizationConfig.from_env().telemetry is False


@pytest.mark.parametrize("pipeline", list(DIARIZATION_PIPELINES))
def test_diarization_accepts_both_local_pipelines(monkeypatch, pipeline):
    monkeypatch.setenv("PYANNOTE_TOKEN", "hf_x")
    monkeypatch.setenv("DIARIZATION_PIPELINE", pipeline)
    assert DiarizationConfig.from_env().pipeline == pipeline
