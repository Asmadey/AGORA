"""
VLM-разбор панелей: кэш, кап вызовов, клиент (задача #16).

Самая дорогая стадия пайплайна. Всё в этом модуле подчинено одному: вызвать
модель ровно столько раз, сколько действительно нужно, и ни разу больше.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_MODEL = "qwen3.6"

#: Сколько секунд ждать ответа модели на одну панель. Разбор изображения идёт
#: заметно дольше текстового запроса, а обрыв по таймауту стоит как полный
#: вызов: провайдер уже посчитал его.
REQUEST_TIMEOUT_SEC = 180


# ─── Ошибки ──────────────────────────────────────────────────────────────────


class CostCapExceeded(RuntimeError):
    """
    Жёсткий кап вызовов исчерпан — разбор оборван.

    Исключение, а не короткий список сцен. Настройки (#27) требуют, чтобы
    жёсткий кап «реально обрывал пайплайн»: молчаливое усечение дало бы отчёт,
    построенный на половине ролика, и отличить его от полного было бы нечем —
    ни в интерфейсе, ни в артефактах.

    Уже полученные сцены прикладываются к исключению: они оплачены, и вызывающий
    вправе сохранить их в кэш, чтобы повтор после поднятия капа не платил дважды.
    """

    def __init__(self, limit: int, scenes: list[dict[str, Any]], remaining: int):
        super().__init__(
            f"жёсткий кап в {limit} вызовов VLM исчерпан: разобрано {len(scenes)} панелей, "
            f"осталось {remaining}. Поднимите кап в Настройках либо переключите его в «авто»"
        )
        self.limit = limit
        self.scenes = scenes
        self.remaining = remaining


# ─── Кап вызовов ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CallBudget:
    """
    Потолок числа вызовов VLM. `None` — без ограничения.

    Попадания в кэш бюджет НЕ расходуют, и это не послабление: кап введён,
    чтобы ограничить деньги, а кэшированная панель денег не стоит. Считать её
    значило бы обрывать повторный прогон (#30) тем раньше, чем лучше сработал
    кэш — то есть наказывать за экономию.
    """

    limit: int | None

    @classmethod
    def unlimited(cls) -> CallBudget:
        return cls(limit=None)

    @classmethod
    def for_task(cls, settings_snapshot: dict[str, Any] | None) -> CallBudget:
        """
        Кап из снимка настроек, положенного в задачу при её создании.

        Снимок, а не чтение настроек на лету — по той же причине, по которой
        пиннингуется модель Whisper (#15) и версии промптов (Decision Log #10):
        пока задача стоит в очереди, команда может сменить кап, и тогда часть
        панелей разобрана под одним потолком, часть под другим. Расхождение в
        полноте разбора выглядело бы свойством материала, а не настройки.

        Контракт полей совпадает с apps/web/lib/settings.ts: costCap — «auto» или
        «hard», costCapValue осмыслен только при «hard».
        """
        if not settings_snapshot:
            return cls.unlimited()
        if settings_snapshot.get("costCap") != "hard":
            return cls.unlimited()
        value = settings_snapshot.get("costCapValue")
        if not isinstance(value, int) or value <= 0:
            return cls.unlimited()
        return cls(limit=value)


# ─── Кэш ─────────────────────────────────────────────────────────────────────


def cache_key(image: bytes, prompt_template: str, model: str) -> str:
    """
    Ключ разбора одной панели.

    В ключ входят три вещи, и каждая — по своей причине:

    · содержимое панели, а не путь к файлу и не id задачи. Иначе повторный
      прогон (#30) не нашёл бы разбор родительской задачи, ради которого кэш
      и заводится: у нового прогона другой task_id, а картинка та же;

    · ШАБЛОН промпта. Правка content.frame_analysis в Промпт-студии (#26)
      обязана обесценить кэш. Без этого пользователь видит изменённый промпт и
      прежний результат, и объяснить расхождение нечем;

    · имя модели. Смена агента провайдера меняет ответ на тот же вход.

    Подстановки в шаблон (таймкод панели) в ключ НЕ входят: они выводятся из
    самой панели, а таймкод результата всё равно проставляется нами, а не
    моделью — см. analyze_panels.
    """
    h = hashlib.sha256()
    h.update(hashlib.sha256(image).digest())
    h.update(prompt_template.encode("utf-8"))
    h.update(model.encode("utf-8"))
    return h.hexdigest()


class Cache(Protocol):
    """Хранилище разборов. Промах возвращает None, а не бросает."""

    def get(self, key: str) -> dict[str, Any] | None: ...

    def set(self, key: str, value: dict[str, Any]) -> None: ...


@dataclass
class MemoryCache:
    """Кэш в памяти процесса — для тестов и одиночного прогона."""

    store: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get(self, key: str) -> dict[str, Any] | None:
        return self.store.get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
        self.store[key] = value


class MongoCache:
    """
    Кэш в коллекции chunk_analyses (схема заведена в #2).

    Между процессами, а не в памяти: «повторный прогон» из cdd — это новая
    задача Celery в другом процессе, и кэш в памяти для неё пуст. Кэш, который
    не переживает процесс, требование бы не выполнил, а выглядел бы работающим.

    tenant_id обязателен: коллекция разделяется по арендаторам наравне с
    остальными (см. agent_core.db.assert_tenant_filter). Разбор кадров чужого
    ролика — такая же утечка, как и всё прочее.
    """

    def __init__(self, collection: Any, tenant_id: str):
        self.collection = collection
        self.tenant_id = tenant_id

    def get(self, key: str) -> dict[str, Any] | None:
        doc = self.collection.find_one({"tenant_id": self.tenant_id, "cache_key": key})
        return doc.get("analysis") if doc else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        self.collection.update_one(
            {"tenant_id": self.tenant_id, "cache_key": key},
            {"$set": {"analysis": value}},
            upsert=True,
        )


# ─── Разбор ──────────────────────────────────────────────────────────────────


@dataclass
class AnalysisResult:
    """Итог разбора. Счётчики нужны отчёту о стоимости прогона."""

    scenes: list[dict[str, Any]] = field(default_factory=list)
    calls_made: int = 0
    cache_hits: int = 0


class VlmClient(Protocol):
    """Шов между разбором и провайдером.

    Клиент передаётся параметром, а не создаётся внутри, по двум причинам.
    Продуктовая: разбор кадров и рассуждение персон могут обслуживаться разными
    агентами провайдера, то есть разными base_url (см. ModelConfig). Проверочная:
    все пункты cdd задачи — про число вызовов, а не про ответы модели, и
    проверяются клиентом-счётчиком без единого обращения к сети.
    """

    def analyze(self, *, image: bytes, prompt: str) -> dict[str, Any]: ...


def analyze_panels(
    panels: list[Any],
    *,
    client: VlmClient,
    prompt: str,
    cache: Cache | None = None,
    model: str | None = None,
    budget: CallBudget | None = None,
) -> AnalysisResult:
    """
    Прогоняет панели через VLM с кэшем и капом.

    Порядок действий на каждой панели ровно такой: сначала кэш, потом бюджет,
    потом вызов. Проверять бюджет раньше кэша нельзя — тогда исчерпанный кап
    обрывал бы прогон, который не собирался тратить ни рубля.

    Таймкод результата проставляется из панели, а не берётся из ответа модели,
    хотя промпт и просит его вернуть. Единственный источник времени — proxy
    (Decision Log #14); модель здесь ненадёжна вдвойне, потому что видит только
    подставленное в текст значение и вольна его переписать.
    """
    model_name = model or os.environ.get("VLM_MODEL") or DEFAULT_MODEL
    budget = budget or CallBudget.unlimited()
    result = AnalysisResult()

    for panel in panels:
        key = cache_key(panel.image, prompt, model_name)

        cached = cache.get(key) if cache else None
        if cached is not None:
            result.scenes.append(_stamp(cached, panel))
            result.cache_hits += 1
            continue

        if budget.limit is not None and result.calls_made >= budget.limit:
            raise CostCapExceeded(
                limit=budget.limit,
                scenes=result.scenes,
                remaining=len(panels) - len(result.scenes),
            )

        analysis = client.analyze(image=panel.image, prompt=_render(prompt, panel))
        result.calls_made += 1
        if cache:
            cache.set(key, analysis)
        result.scenes.append(_stamp(analysis, panel))

    return result


def _render(template: str, panel: Any) -> str:
    """Подстановка переменных промпта content.frame_analysis."""
    return (
        template
        .replace("{{timestamp}}", f"{panel.timestamp_sec:.2f}")
        .replace("{{panel_size}}", str(len(panel.frames) or 1))
        .replace("{{frames}}", f"панель #{panel.index}")
    )


def _stamp(analysis: dict[str, Any], panel: Any) -> dict[str, Any]:
    """Приклеивает к разбору таймкод и номер панели из proxy, а не из ответа."""
    return {
        **analysis,
        "panel_index": panel.index,
        "timestamp_sec": panel.timestamp_sec,
    }


# ─── Клиент провайдера ───────────────────────────────────────────────────────


class QwenVlmClient:
    """
    Боевой клиент: OpenAI-совместимый endpoint TimeWeb (Decision Log #1).

    Панель уходит как data-URL в base64. Ссылкой отдать нельзя: PRD §7.1
    запрещает выпускать кадры пользовательского видео за контур любым способом,
    в котором они становятся доступны по URL, — а публичная ссылка на S3 именно
    это и делает.
    """

    def __init__(self, config: Any | None = None, model: str | None = None):
        from ..config import ModelConfig

        self.config = config or ModelConfig.from_env()
        self.model = model or self.config.vlm_model

    def analyze(self, *, image: bytes, prompt: str) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.vlm_base_url,
            default_headers=self.config.default_headers,
            timeout=REQUEST_TIMEOUT_SEC,
        )
        data_url = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
        response = client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
        )
        return _parse_json(response.choices[0].message.content or "")


def _parse_json(text: str) -> dict[str, Any]:
    """
    Разбор ответа модели.

    Модель просят вернуть чистый JSON, и она регулярно оборачивает его в
    ```json — это не сбой, а обычное поведение чат-модели. Падать на такой
    обёртке значило бы терять оплаченный вызов из-за трёх обратных кавычек.
    """
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {"scene_description": text.strip()[:2000], "parse_failed": True}
    return parsed if isinstance(parsed, dict) else {"scene_description": str(parsed)}
