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
    """Провайдер моделей — агент TimeWeb Cloud AI (OpenAI-совместимый).

    Три особенности этого endpoint, из-за которых обычный OpenAI-клиент к нему
    не подключается «как есть» (сверено с api-1.json, OpenAPI провайдера):

    1. Обязательный заголовок ``x-proxy-source``. Он помечен required в
       спецификации, а SDK его не отправляет. Без него — отказ на транспортном
       уровне, до всякой модели.

    2. Поле ``model`` игнорируется: «This field is ignored as the agent has its
       own model configuration». Модель выбирается в кабинете при настройке
       агента, а не в запросе. Поэтому AI_MODEL/VLM_MODEL здесь — только подпись
       для отчёта и снимка задачи, влиять на выбор они не могут.

    3. Как следствие пункта 2: один агент = одна модель. Развести рассуждение
       персон и разбор кадров по разным моделям можно только двумя агентами с
       разными access_id, то есть разными base_url. VLM_BASE_URL для этого и
       заведён; если он пуст, оба потока идут в один агент.
    """

    api_key: str
    base_url: str
    vlm_base_url: str
    text_model: str
    vlm_model: str
    proxy_source: str

    @property
    def default_headers(self) -> dict[str, str]:
        """Передаётся в OpenAI(..., default_headers=...) — иначе запрос отклонят."""
        return {"x-proxy-source": self.proxy_source}

    @property
    def vlm_shares_agent(self) -> bool:
        """True — кадры и текст обслуживает один агент, то есть одна модель."""
        return self.vlm_base_url == self.base_url

    @classmethod
    def from_env(cls) -> ModelConfig:
        base_url = _optional("OPENAI_BASE_URL", "https://api.timeweb.cloud/v1")
        return cls(
            api_key=_required("OPENAI_API_KEY"),
            base_url=base_url,
            vlm_base_url=_optional("VLM_BASE_URL", base_url),
            text_model=_optional("AI_MODEL", "qwen3.6"),
            vlm_model=_optional("VLM_MODEL", "qwen3.6"),
            proxy_source=_optional("MODEL_PROXY_SOURCE", "agora"),
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


#: Пайплайны диаризации, которые допустимо загружать локально.
#: Оба бесплатны и работают на своём железе: сама библиотека под MIT, веса на
#: Hugging Face закрыты принятием условий, но не оплатой. Платный вариант
#: pyannote — это ``speaker-diarization-precision-2``, он ходит на серверы
#: pyannoteAI, и здесь его быть не должно: PRD требует self-host, а аудио
#: пользователей не должно уезжать третьей стороне.
DIARIZATION_PIPELINES = (
    "pyannote/speaker-diarization-3.1",
    "pyannote/speaker-diarization-community-1",
)


@dataclass(frozen=True)
class DiarizationConfig:
    """Диаризация pyannote.audio на своём железе (Decision Log #6).

    ``hf_token`` обязателен даже для локального запуска: веса лежат в закрытых
    репозиториях Hugging Face, доступ открывается принятием условий. Денег это не
    стоит, но без токена ``Pipeline.from_pretrained`` вернёт 401.

    ``cache_dir`` указывает на смонтированный том: веса тяжёлые, а качать их на
    каждый старт контейнера — и медленно, и хрупко, если до HF нет доступа из
    сети развёртывания.

    ``telemetry`` выключена по умолчанию. pyannote.audio 4.x по умолчанию шлёт
    анонимную статистику вызовов; для сервиса, который продаётся как self-host,
    неявная исходящая передача — сюрприз для клиента, даже обезличенная.
    """

    pipeline: str
    hf_token: str
    cache_dir: str
    telemetry: bool

    @classmethod
    def from_env(cls) -> DiarizationConfig:
        pipeline = _optional("DIARIZATION_PIPELINE", "pyannote/speaker-diarization-community-1")
        if pipeline not in DIARIZATION_PIPELINES:
            raise ConfigError(
                f"DIARIZATION_PIPELINE={pipeline!r} не поддерживается; допустимо "
                f"{' или '.join(repr(p) for p in DIARIZATION_PIPELINES)}. "
                f"Платный precision-2 исключён намеренно: он исполняется на серверах "
                f"pyannoteAI, а PRD требует self-host"
            )
        return cls(
            pipeline=pipeline,
            hf_token=_required("PYANNOTE_TOKEN"),
            cache_dir=_optional("HF_HOME", "/root/.cache/huggingface"),
            telemetry=_optional("PYANNOTE_METRICS_ENABLED", "0") == "1",
        )


def _validate_model(model: str, *, source: str) -> str:
    if model not in WHISPER_MODELS:
        raise ConfigError(
            f"{source}={model!r} не поддерживается; допустимо "
            f"{' или '.join(repr(m) for m in WHISPER_MODELS)} (Decision Log #6)"
        )
    return model
