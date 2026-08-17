"""Конфигурация worker'а — строго из окружения, никаких значений по умолчанию для секретов.

Контракт env зафиксирован в apps/web/.env.example (Decision Log #1: Qwen 3.6 через
OpenAI-совместимый API timeweb; Whisper + pyannote self-host на CPU).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from typing import Any


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

    #: Роли, которым размышление ОСТАВЛЕНО. Остальные идут без него.
    #:
    #: Замер тремя прогонами golden-сета решил вопрос, который одиночный прогон
    #: решить не мог. С размышлением, выключенным везде, QA браковал 7, 5 и 4
    #: ответа из двенадцати: персоны выдумывали таймкоды и приписывали сцены не
    #: тем моментам. С включённым везде — ноль отбраковок из двенадцати, но
    #: прогон занимал 23 минуты против десяти по критерию #22.
    #:
    #: Отсюда разделение по РОЛЯМ, а не один рубильник:
    #:
    #:   respondent  — размышление НУЖНО. Персона строит ответ по материалу и
    #:                 обязана не промахнуться мимо таймкода; без размышления
    #:                 треть ответов не заземлена, и это воспроизводится.
    #:   frames      — не нужно: разбор кадра описывает увиденное.
    #:   qa          — не нужно: судья сверяет по правилам и без размышления
    #:                 ловил галлюцинации ничуть не хуже, отказов ноль.
    #:   analytics,
    #:   persona,
    #:   portrait    — не нужно: сжатие и пересказ уже готового.
    #:
    #: Экономия при этом сохраняется: судей и разборов кадров в прогоне больше,
    #: чем персон, и основное время уходило именно на них.
    #:
    #: Переопределяется переменной MODEL_THINKING_ROLES: список через запятую,
    #: `none` — выключить везде, `all` — включить везде.
    thinking_roles: frozenset[str] = frozenset({"respondent"})

    #: Модель судьи. Пусто — судить той же, что отвечает (`judge_model_or_text`).
    #:
    #: Отдельное поле, а не второй адрес: провайдер, под которого писался
    #: `escalation_base_url`, выбирал модель адресом агента, а нынешний —
    #: полем `model`. Подстановка идентификатора в сегмент `/agents/<id>` на
    #: адресе Cloud.ru падает: такого сегмента там нет.
    judge_model: str = ""

    #: Режим рассуждения из настроек: {"thinking": bool, "effort": str}.
    #: Пустой словарь — брать поведение из `thinking_roles`, как было до
    #: появления настроек.
    reasoning: dict[str, Any] = field(default_factory=dict)
    judge_reasoning: dict[str, Any] = field(default_factory=dict)

    @property
    def default_headers(self) -> dict[str, str]:
        """Передаётся в OpenAI(..., default_headers=...) — иначе запрос отклонят."""
        return {"x-proxy-source": self.proxy_source}

    #: Роли, которые вообще бывают. Список закрытый намеренно — см. extra_body.
    ROLES = ("respondent", "frames", "qa", "analytics", "persona", "portrait")

    @classmethod
    def for_task(
        cls, settings_snapshot: dict[str, Any] | None, base: ModelConfig | None = None
    ) -> ModelConfig:
        """
        Конфигурация прогона: выбор моделей и адрес из снимка настроек.

        Пустая строка в снимке означает «как в окружении», а не «без модели»:
        так выглядят все прогоны до первого захода в настройки, и подставлять
        туда конкретное имя нельзя — оно разъедется с `.env` при первой смене, и
        отчёт станет называть модель, по которой прогон не шёл.

        Ключа в снимке нет и не должно быть. Снимок живёт столько же, сколько
        отчёт, и копия ключа в каждой строке `tasks` — это секрет, размноженный
        по резервным копиям базы без единого способа его отозвать.
        """
        config = base or cls.from_env()
        stored = settings_snapshot or {}
        models = stored.get("models") or {}

        def pick(role: str, fallback: str) -> str:
            value = models.get(role)
            return value.strip() if isinstance(value, str) and value.strip() else fallback

        endpoint = stored.get("endpoint")
        base_url = (
            endpoint.strip()
            if isinstance(endpoint, str) and endpoint.strip()
            else config.base_url
        )

        return replace(
            config,
            base_url=base_url,
            # vlm_base_url следует за основным, если не задан отдельно: он
            # заведён под провайдера, у которого «другая модель» означала
            # «другой агент», то есть другой адрес. Там, где модель выбирается
            # полем `model`, второй адрес не нужен.
            vlm_base_url=(
                config.vlm_base_url
                if config.vlm_base_url != config.base_url
                else base_url
            ),
            text_model=pick("text", config.text_model),
            vlm_model=pick("vision", config.vlm_model),
            judge_model=pick("judge", ""),
            reasoning=_reasoning_of(stored.get("reasoning")),
            judge_reasoning=_reasoning_of(stored.get("judgeReasoning")),
        )

    @property
    def judge_model_or_text(self) -> str:
        """Модель судьи либо текстовая. Пусто = судить тем же, чем отвечали."""
        return self.judge_model or self.text_model

    def extra_body(self, role: str) -> dict[str, object]:
        """
        Дополнительные поля запроса для роли. Пустой словарь — ничего не добавляем.

        Ключ именно `enable_thinking`, соглашение vLLM/Qwen. `thinking: false`
        из документации провайдера этот шлюз ИГНОРИРУЕТ: замер дал те же 600
        токенов рассуждения и пустой content. Опечатка в имени ничего не
        сломает — просто вернёт медленные прогоны, поэтому имя под тестом.

        Незнакомая роль — ValueError, а не тихое умолчание. Опечатка в имени
        роли иначе молча выбрала бы быстрый режим там, где нужен заземлённый, и
        увидеть это можно было бы только по доле отбракованных ответов через
        десять минут прогона.
        """
        if role not in self.ROLES:
            raise ValueError(
                f"неизвестная роль модели {role!r}; ожидается одна из {', '.join(self.ROLES)}"
            )

        # Настройки арендатора главнее умолчания по ролям: `thinking_roles`
        # описывает, где размышление полезно ВООБЩЕ, а настройка — чего хочет
        # команда на своих прогонах. Пустой словарь означает «настройки не
        # трогали», и тогда работает прежнее правило.
        settings = self.judge_reasoning if role == "qa" else self.reasoning
        if settings:
            kwargs: dict[str, object] = {"enable_thinking": bool(settings.get("thinking"))}
            effort = settings.get("effort")
            if effort:
                # Текущий шлюз параметр игнорирует (замер 17.08.2026), но
                # отправляется он всё равно: заработает при смене провайдера, а
                # молча выбрасывать выбор пользователя нельзя.
                kwargs["reasoning_effort"] = effort
            return {"chat_template_kwargs": kwargs}

        if role in self.thinking_roles:
            return {}
        return {"chat_template_kwargs": {"enable_thinking": False}}

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
            thinking_roles=_thinking_roles(),
        )


#: Порог уверенности, ниже которого вердикт судьи идёт на перепроверку моделью
#: большего размера. Значение ПРЕДВАРИТЕЛЬНОЕ — ровно в том смысле, в каком это
#: сказано в PRD §14.1: «назначать его до того, как известно распределение
#: confidence, значит выдумывать число».
#:
#: Калибровать так: прогнать QA на полном наборе ответов с эскалацией
#: ВЫКЛЮЧЕННОЙ, собрать распределение confidence из qa_report.json и поставить
#: порог по доле ответов, которую готовы оплачивать дважды.
#:
#: Число обязано совпадать с apps/web/.env.example — там же оно объявлено как
#: контракт окружения. Разойдясь, они дали бы разный порог в зависимости от
#: того, скопировал ли оператор файл: у одного эскалация на трети ответов, у
#: другого на десятой части, и оба уверены, что настройка одна. Совпадение
#: держится проверкой test_default_threshold_matches_env_example.
DEFAULT_ESCALATION_CONFIDENCE = 0.6

#: Где в базовом URL провайдера стоит идентификатор агента. Endpoint TimeWeb —
#: /api/v1/cloud-ai/agents/{agent_access_id}/v1 (см. docs/providers.md §2), и
#: «другая модель» означает «другой агент», а не другое значение поля model:
#: поле model этим endpoint игнорируется.
_AGENT_SEGMENT = re.compile(r"(/agents/)[^/]+(/|$)")


def _reasoning_of(source: Any) -> dict[str, Any]:
    """
    Режим рассуждения из снимка. Мусор отбрасывается молча.

    Молча — потому что снимок читает воркер посреди прогона, и падать здесь
    значило бы терять оплаченную расшифровку из-за поля, у которого есть
    осмысленное умолчание.
    """
    if not isinstance(source, dict):
        return {}
    out: dict[str, Any] = {}
    if isinstance(source.get("thinking"), bool):
        out["thinking"] = source["thinking"]
    effort = source.get("effort")
    if isinstance(effort, str) and effort in ("low", "medium", "high", "max"):
        out["effort"] = effort
    return out


@dataclass(frozen=True)
class QaConfig:
    """Политика QA-агента (#19): порог уверенности и агент для перепроверки.

    ``escalation_agent_id`` НЕОБЯЗАТЕЛЕН, и его отсутствие — штатный режим, а не
    деградация (Decision Log #16, PRD §14.1). Без него все проверки закрываются
    основной моделью, и это ровно то, что происходит у большинства арендаторов.

    Отсюда правило, которое легко нарушить из лучших побуждений: отсутствие
    эскалации не пишется в ``degraded``. Канал деградаций читает отчёт, и запись
    «эскалации не было» приучила бы читать её как изъян прогона — а через
    несколько прогонов перестали бы читать весь канал целиком.
    """

    escalation_agent_id: str | None
    escalation_confidence: float

    @property
    def escalation_enabled(self) -> bool:
        return bool(self.escalation_agent_id)

    @classmethod
    def from_env(cls) -> QaConfig:
        raw = _optional("QA_ESCALATION_CONFIDENCE", str(DEFAULT_ESCALATION_CONFIDENCE))
        try:
            threshold = float(raw)
        except ValueError as exc:
            raise ConfigError(
                f"QA_ESCALATION_CONFIDENCE={raw!r} не число. Порог сравнивается с "
                f"confidence судьи (0.0..1.0)"
            ) from exc
        if not 0.0 <= threshold <= 1.0:
            raise ConfigError(
                f"QA_ESCALATION_CONFIDENCE={threshold} вне диапазона 0.0..1.0: "
                f"confidence судьи нормирован, и порог вне шкалы означает либо "
                f"«эскалировать всегда», либо «никогда» — оба случая стоит написать явно"
            )
        return cls(
            escalation_agent_id=os.environ.get("QA_ESCALATION_AGENT_ID") or None,
            escalation_confidence=threshold,
        )

    def escalation_base_url(self, base_url: str) -> str:
        """
        Базовый URL агента-перепроверщика.

        Если в переменной лежит готовый URL — берётся он. Иначе идентификатор
        подставляется в базовый URL основного агента вместо его собственного.

        Когда подставить некуда, поднимается ошибка, а не тихий возврат
        ``base_url``. Молчаливый откат означал бы, что «эскалация» уходит в ту
        же модель: вердикт получал бы штамп «перепроверено моделью большего
        размера», не будучи перепроверенным ничем, — и в отчёте разницы не видно.
        """
        agent = self.escalation_agent_id
        if not agent:
            raise ConfigError("QA_ESCALATION_AGENT_ID не задан — эскалировать не к кому")
        if agent.startswith(("http://", "https://")):
            return agent.rstrip("/")
        patched, count = _AGENT_SEGMENT.subn(rf"\g<1>{agent}\g<2>", base_url, count=1)
        if not count:
            raise ConfigError(
                f"в OPENAI_BASE_URL={base_url!r} нет сегмента /agents/<id>, и подставить "
                f"QA_ESCALATION_AGENT_ID={agent!r} некуда. Задайте переменной полный URL "
                f"второго агента целиком"
            )
        return patched.rstrip("/")


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


@dataclass(frozen=True)
class TemperatureConfig:
    """
    Температура по стадиям конвейера.

    ─── Почему не одно значение ───────────────────────────────────────────
    Стадии требуют противоположного. Персона обязана получиться непохожей на
    соседнюю — это условие метрики `response_diversity`, и низкая температура
    здесь даёт mode collapse: двадцать почти совпадающих портретов вместо
    аудитории. Проверяющий и аналитик обязаны быть повторяемыми: вердикт,
    меняющийся от прогона к прогону, перестаёт быть свойством проверяемого.

    До появления этого класса значения стояли числами прямо в клиентах, и
    поменять их можно было только правкой кода с пересборкой образа.

    ─── Имена полей ──────────────────────────────────────────────────────
    Совпадают с ключами `TEMPERATURE_STAGES` в apps/web/lib/settings.ts, и это
    не косметика: снимок задачи приезжает оттуда как есть. Разойдясь на одну
    букву, стороны дадут настройку, которая выставляется и не применяется, —
    обе выглядят исправными, а расхождение видно только по счёту от провайдера
    и по доле отбраковок. Совпадение держит test_temperature_config.py.
    """

    #: Обогащение портрета персоны (`persona/enrich.py`).
    personaCreation: float = 0.9
    #: Проверка созданной персоны на связность с её же DNA.
    personaValidation: float = 0.1
    #: Ответы персон на анкету (`respondent/run.py`).
    responseSimulation: float = 0.3
    #: Сборка нарратива отчёта (`analytics/report.py`).
    aggregation: float = 0.1
    #: Вердикты QA по ответам (`qa/judge.py`).
    answerJudge: float = 0.0
    #: Сводные портреты сегментов (`portraits/distill.py`).
    segmentPortraits: float = 0.3

    #: Порядок стадий. Отдельной константой, чтобы обход не зависел от
    #: `dataclasses.fields` — от него зависит проверка стыка с интерфейсом.
    STAGES = (
        "personaCreation",
        "personaValidation",
        "responseSimulation",
        "aggregation",
        "answerJudge",
        "segmentPortraits",
    )

    #: Диапазон, который принимает OpenAI-совместимый endpoint.
    MIN = 0.0
    MAX = 2.0

    @classmethod
    def defaults(cls) -> TemperatureConfig:
        return cls()

    @classmethod
    def for_task(cls, settings_snapshot: dict[str, Any] | None) -> TemperatureConfig:
        """
        Температуры конкретного прогона из снимка настроек.

        Снимок кладётся в задачу при создании и не перечитывается на лету — по
        той же причине, что модель Whisper и версии промптов: пока задача стоит
        в очереди, команда может сменить настройку, и тогда персоны созданы под
        одной температурой, а опрошены под другой. Разница в разбросе ответов
        выглядела бы свойством материала, а не настройки.

        Пропущенная стадия берёт умолчание, а не ноль. Ноль здесь не «значения
        нет», а «полная детерминированность»: на создании персон он означал бы
        mode collapse.
        """
        raw = ((settings_snapshot or {}).get("temperatures") or {})
        values: dict[str, float] = {}
        for stage in cls.STAGES:
            if stage not in raw:
                continue
            try:
                value = float(raw[stage])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"температура стадии {stage} не число: {raw[stage]!r}"
                ) from exc
            if not cls.MIN <= value <= cls.MAX:
                # Отвергаем здесь, а не у провайдера: его отказ придёт посреди
                # оплаченного прогона — после расшифровки и разбора кадров — и
                # будет выглядеть сбоем сети, а не опечаткой в настройках.
                raise ValueError(
                    f"температура стадии {stage} = {value} вне диапазона "
                    f"{cls.MIN}..{cls.MAX}"
                )
            values[stage] = value
        return cls(**values)


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


def _thinking_roles() -> frozenset[str]:
    """
    Роли с размышлением из окружения. Умолчание — только респондент.

    `none` и `all` названы явно: пустая строка означала бы «не задано», и
    отличить её от «выключить везде» было бы нечем.
    """
    raw = _optional("MODEL_THINKING_ROLES", "respondent").strip().lower()
    if raw in ("", "respondent"):
        return frozenset({"respondent"})
    if raw == "none":
        return frozenset()
    if raw == "all":
        return frozenset(ModelConfig.ROLES)
    return frozenset(part.strip() for part in raw.split(",") if part.strip())
