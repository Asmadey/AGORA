"""
Обогащение персон моделью поверх заземлённого скелета.

─── Зачем отдельный слой, а не генерация персоны моделью целиком ─────────────
Продукт продаётся фразой «прогноз, а не догадка». Разница между прогнозом и
догадкой здесь ровно одна: откуда взялись факты. Если возраст, гео, ценности и
баллы придумала модель, то персона правдоподобна и ни на чём не основана, а
метрика persona_grounding — которая сверяет доли выдачи с долями корпуса — меряет
качество фантазии, а не заземление.

Поэтому порядок жёсткий: корпус даёт факты, модель даёт язык.

  · PersonaGenerator.generate() сэмплирует 8 категорий DNA по реальным долям
    корпуса. Это скелет. Он детерминирован по seed и не зависит от модели.
  · enrich_personas() отдаёт скелет модели и забирает обратно ОДНО поле —
    narrative. Всё остальное возвращается байт в байт.

Если модель недоступна, персона остаётся со сшитым из шаблона narrative. Она
хуже читается и полностью пригодна к работе: ни один расчёт вниз по конвейеру на
narrative не опирается.

─── Почему narrative, а не «немного всего» ───────────────────────────────────
Соблазн дать модели править ещё и хобби, и цитаты — понятный: живее выйдет. Но
как только модель меняет хоть одно поле, по которому считается заземление,
метрика начинает мерить смесь корпуса и модели, а разделить вклад уже нечем.
Граница проходит по признаку «участвует ли поле в persona_grounding», и narrative
— единственное поле, которое не участвует.

─── Детерминизм ──────────────────────────────────────────────────────────────
CDD задачи #5 требует ``generate(cfg) == generate(cfg)``. Вызов модели этому
угрожает, и три меры закрывают угрозу:

  · temperature=0 и seed в запросе — насколько провайдер это поддерживает;
  · кэш по СОДЕРЖИМОМУ скелета: второй прогон с тем же seed даёт тот же скелет,
    тот же ключ и тот же narrative из кэша, то есть побайтовое совпадение уже не
    зависит от воспроизводимости модели;
  · без ключа обогащение выключается целиком и одинаково.

Последнее важнее, чем кажется. Без него CDD #5 проверялся бы только на машине с
ключом и с деньгами на счету, то есть нигде в CI.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

DEFAULT_MODEL = "qwen3.6"

def _find_prompt(name: str) -> Path:
    """
    Ищет промпт по нескольким раскладкам, а не по одной.

    Причина не в аккуратности. В репозитории модуль лежит по пути
    services/agent-core/agent_core/persona/, и prompts/ находится на четыре
    уровня выше. В образе воркера код скопирован в /app/agent_core/, а промпты в
    /app/prompts — то есть на два. Жёсткий отсчёт вверх верен ровно в одной из
    двух сред, и ошибётся он молча: файла нет → обогащение деградирует до
    шаблона → аудитория выглядит сгенерированной, просто скучной.

    Возвращается первый существующий кандидат, а при полном промахе — путь для
    репозитория: сообщение об ошибке должно называть то место, куда файл
    действительно кладут.
    """
    here = Path(__file__).resolve()
    candidates = [p / "prompts" / name for p in here.parents[:6]]
    for path in candidates:
        if path.exists():
            return path
    return here.parents[4] / "prompts" / name


#: Промпт живёт в prompts/ и правится в Промпт-студии (#26) — как и все прочие.
PROMPT_PATH = _find_prompt("persona.enrich.md")

#: Обогащение одной персоны — короткий текстовый запрос, не разбор картинки.
REQUEST_TIMEOUT_SEC = 60

#: Нижняя граница длины из canonical JSON Schema (#4). Ответ короче — брак:
#: схема его отвергнет, и персона не сохранится.
MIN_NARRATIVE_LEN = 100

#: Поля, которые модель не видит и не может изменить. Список не для красоты:
#: по ним считается persona_grounding, и любое расширение этого модуля обязано
#: сначала объяснить, почему новое поле не ломает метрику.
GROUNDED_FIELDS = (
    "demographics",
    "big_five",
    "values_and_beliefs",
    "viewer_behavior",
    "communication_style",
    "decision_making",
    "technology_usage",
    "lifestyle_and_interests",
    "seed",
)


# ─── Кэш ─────────────────────────────────────────────────────────────────────


def cache_key(skeleton: dict[str, Any], prompt_template: str, model: str) -> str:
    """
    Ключ обогащения одной персоны.

    Считается от скелета, а не от id персоны или прогона. Причина та же, что в
    #16: при перезапуске исследования (#30) персоны те же, а id у них новые, и
    ключ по id не нашёл бы ни одного попадания ровно там, где кэш нужнее всего.

    Скелет сериализуется с sort_keys — иначе порядок ключей словаря, вообще
    говоря стабильный в CPython, стал бы частью контракта кэша молча.
    """
    h = hashlib.sha256()
    h.update(json.dumps(skeleton, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(prompt_template.encode("utf-8"))
    h.update(model.encode("utf-8"))
    return h.hexdigest()


class Cache(Protocol):
    """Хранилище обогащений. Промах возвращает None, а не бросает."""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...


@dataclass
class MemoryCache:
    """Кэш в памяти процесса — для тестов и одиночного прогона."""

    store: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str) -> None:
        self.store[key] = value


# ─── Клиент ──────────────────────────────────────────────────────────────────


class TextClient(Protocol):
    """Шов между обогащением и провайдером — тот же приём, что у VlmClient."""

    def complete(self, *, prompt: str) -> str: ...


class QwenTextClient:
    """
    Боевой клиент: OpenAI-совместимый endpoint TimeWeb (Decision Log #1).

    Создаётся лениво и падает с ConfigError, если ключа нет. Ошибку ловит
    enrich_personas и переводит генерацию в режим без модели — падать здесь
    нельзя, потому что отсутствие ключа это штатное состояние CI.
    """

    def __init__(self, config: Any | None = None, model: str | None = None):
        from ..config import ModelConfig

        self.config = config or ModelConfig.from_env()
        self.model = model or self.config.text_model

    def complete(self, *, prompt: str) -> str:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            default_headers=self.config.default_headers,
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            # temperature=0 — не «поменьше фантазии», а условие воспроизводимости
            # CDD #5. Провайдер вправе его не соблюсти полностью, поэтому вторым
            # эшелоном стоит кэш.
            temperature=0,
        )
        return (response.choices[0].message.content or "").strip()


# ─── Результат ───────────────────────────────────────────────────────────────


@dataclass
class EnrichResult:
    """
    Итог обогащения.

    ``degraded_reason`` не None означает: персоны вернулись с шаблонным
    narrative. Это состояние обязано быть видно вызывающему, иначе отличить
    «модель поработала» от «модели не было» можно только на глаз по тексту.

    ``sources`` идёт отдельным списком, а не полем внутри персоны, и это не
    вкусовщина: canonical JSON Schema (#4) объявлена ``additionalProperties:
    false``, поэтому лишний ключ в словаре персоны — это отказ валидации при
    сохранении. Ровно так же снаружи DNA живёт имя персоны: в колонке
    ``personas.name``, а не в jsonb.
    """

    personas: list[dict[str, Any]] = field(default_factory=list)
    #: Для каждой персоны: "model" или "template". Индексы совпадают с personas.
    sources: list[str] = field(default_factory=list)
    calls_made: int = 0
    cache_hits: int = 0
    degraded_reason: str | None = None

    @property
    def enriched(self) -> bool:
        return self.degraded_reason is None


# ─── Обогащение ──────────────────────────────────────────────────────────────


def _skeleton(persona: dict[str, Any]) -> dict[str, Any]:
    """Заземлённая часть персоны — то, что уходит в промпт и в ключ кэша."""
    return {k: persona[k] for k in GROUNDED_FIELDS if k in persona}


def render_prompt(template: str, persona: dict[str, Any]) -> str:
    """
    Подставляет скелет в шаблон persona.enrich.md.

    Переменные те же, что у прочих промптов — ``{{name}}``. Скелет отдаётся и
    целиком (``{{skeleton_json}}``), и разложенным по удобным полям: модель
    заметно лучше держится фактов, когда видит их и списком, и в структуре.
    """
    demo = persona.get("demographics", {})
    values = persona.get("values_and_beliefs", {}).get("important_values", [])
    lifestyle = persona.get("lifestyle_and_interests", {})
    return (
        template
        .replace("{{skeleton_json}}", json.dumps(_skeleton(persona), ensure_ascii=False, indent=2))
        .replace("{{age}}", str(demo.get("age", "")))
        .replace("{{gender}}", str(demo.get("gender", "")))
        .replace("{{city}}", str(demo.get("city", "")))
        .replace("{{geo}}", str(demo.get("geo", "")))
        .replace("{{values}}", ", ".join(values))
        .replace("{{hobbies}}", ", ".join(lifestyle.get("hobbies", [])))
        .replace("{{work_status}}", str(lifestyle.get("work_status", "")))
        .replace("{{min_len}}", str(MIN_NARRATIVE_LEN))
    )


def enrich_personas(
    personas: list[dict[str, Any]],
    *,
    client: TextClient | None = None,
    prompt: str | None = None,
    cache: Cache | None = None,
    model: str | None = None,
) -> EnrichResult:
    """
    Переписывает narrative каждой персоны моделью, оставляя скелет нетронутым.

    Ни одно исключение наружу не выходит. Обогащение — улучшение читаемости, а
    не условие работоспособности: сорвать из-за него генерацию аудитории значит
    поменять надёжный результат на красивый.

    Порядок на каждой персоне: кэш → вызов → проверка длины. Ответ короче
    MIN_NARRATIVE_LEN отбрасывается и заменяется шаблонным: canonical JSON Schema
    (#4) такую персону всё равно не примет, и лучше это увидеть здесь, чем при
    сохранении в базу.
    """
    model_name = model or os.environ.get("AI_MODEL") or DEFAULT_MODEL

    if prompt is None:
        prompt = PROMPT_PATH.read_text("utf-8") if PROMPT_PATH.exists() else ""
    if not prompt:
        return EnrichResult(
            personas=copy.deepcopy(personas),
            degraded_reason=f"промпт не найден: {PROMPT_PATH}",
        )

    if client is None:
        try:
            client = QwenTextClient(model=model_name)
        except Exception as exc:  # ConfigError и всё, что зависит от среды
            return EnrichResult(
                personas=copy.deepcopy(personas),
                degraded_reason=f"модель недоступна: {type(exc).__name__}: {exc}",
            )

    result = EnrichResult()
    for persona in personas:
        enriched = copy.deepcopy(persona)
        key = cache_key(_skeleton(persona), prompt, model_name)

        cached = cache.get(key) if cache else None
        if cached is not None:
            enriched["narrative"] = cached
            result.personas.append(enriched)
            result.sources.append("model")
            result.cache_hits += 1
            continue

        try:
            text = client.complete(prompt=render_prompt(prompt, persona))
        except Exception as exc:
            # Отказ на середине списка: уже обогащённые персоны сохраняются,
            # остальные остаются с шаблонным narrative. Наполовину обогащённый
            # набор честнее, чем откат к шаблону целиком, — оплаченные вызовы не
            # выбрасываются.
            result.degraded_reason = f"вызов модели не удался: {type(exc).__name__}: {exc}"
            result.personas.append(enriched)
            result.sources.append("template")
            continue

        result.calls_made += 1
        if len(text) < MIN_NARRATIVE_LEN:
            result.personas.append(enriched)
            result.sources.append("template")
            continue

        if cache:
            cache.set(key, text)
        enriched["narrative"] = text
        result.personas.append(enriched)
        result.sources.append("model")

    return result
