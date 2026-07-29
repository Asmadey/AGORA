"""Конфигурация worker'а — строго из окружения, никаких значений по умолчанию для секретов.

Контракт env зафиксирован в apps/web/.env.example (Decision Log #1: Qwen 3.6 через
OpenAI-совместимый API timeweb; Whisper + pyannote self-host на CPU).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Обязательная переменная окружения отсутствует."""


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(
            f"переменная окружения {name} не задана — секреты берутся только из env, "
            f"см. apps/web/.env.example"
        )
    return value


def _optional(name: str, default: str) -> str:
    return os.environ.get(name) or default


@dataclass(frozen=True)
class ModelConfig:
    """Провайдер моделей. Один OpenAI-совместимый endpoint на текст и на VLM."""

    api_key: str
    base_url: str
    text_model: str
    vlm_model: str

    @classmethod
    def from_env(cls) -> ModelConfig:
        return cls(
            api_key=_required("OPENAI_API_KEY"),
            base_url=_optional("OPENAI_BASE_URL", "https://api.timeweb.cloud/v1"),
            text_model=_optional("AI_MODEL", "qwen3.6"),
            vlm_model=_optional("VLM_MODEL", "qwen3.6"),
        )


@dataclass(frozen=True)
class StorageConfig:
    """Хранилища: Postgres (RLS), MongoDB, Valkey (очередь/прогресс/кэш)."""

    database_url: str
    mongodb_url: str
    valkey_url: str

    @classmethod
    def from_env(cls) -> StorageConfig:
        return cls(
            database_url=_required("DATABASE_URL"),
            mongodb_url=_required("MONGODB_URL"),
            valkey_url=_required("VALKEY_URL"),
        )


#: Модели транскрипции. Список закрыт и продублирован в apps/web/lib/settings.ts —
#: интерфейс не должен уметь выбрать то, что воркер не умеет загрузить.
WHISPER_MODELS = ("large-v3", "large-v3-turbo")


@dataclass(frozen=True)
class TranscriptionConfig:
    """STT и диаризация. large-v3 по умолчанию, turbo — fallback из Настроек (#27)."""

    whisper_model: str
    compute_type: str

    @classmethod
    def from_env(cls) -> TranscriptionConfig:
        return cls(
            whisper_model=_validate_model(
                _optional("WHISPER_MODEL", "large-v3"), source="WHISPER_MODEL"
            ),
            compute_type=_optional("WHISPER_COMPUTE_TYPE", "int8"),
        )

    @classmethod
    def for_task(cls, whisper_model: str | None) -> TranscriptionConfig:
        """Конфигурация конкретного прогона.

        Модель приходит из снимка настроек арендатора, положенного в payload задачи
        в момент её создания, а не читается из настроек на лету. Причина та же, по
        которой пиннингуются версии промптов (Decision Log #10): пока задача стоит в
        очереди или досчитывается, настройки команды могут смениться, и тогда
        транскрипция началась бы на одной модели, а сегменты после перезапуска
        доехали бы на другой — расхождение в тексте нельзя было бы отличить от
        свойств материала.

        None означает «в снимке ничего не было» и даёт откат на env: так старые
        задачи, поставленные до появления настроек, остаются исполнимыми.
        """
        if whisper_model is None:
            return cls.from_env()
        return cls(
            whisper_model=_validate_model(whisper_model, source="payload.settings.whisper_model"),
            compute_type=_optional("WHISPER_COMPUTE_TYPE", "int8"),
        )


def _validate_model(model: str, *, source: str) -> str:
    if model not in WHISPER_MODELS:
        raise ConfigError(
            f"{source}={model!r} не поддерживается; допустимо "
            f"{' или '.join(repr(m) for m in WHISPER_MODELS)} (Decision Log #6)"
        )
    return model
