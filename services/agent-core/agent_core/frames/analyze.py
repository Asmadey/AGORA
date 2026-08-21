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

from .dedup import DEFAULT_THRESHOLD as DEDUP_THRESHOLD
from .dedup import hamming

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

    #: Имя поля ключа в документе.
    #:
    #: `content_hash`, а не `cache_key`: именно так поле названо в схеме
    #: коллекции и именно по нему построен индекс
    #: (`infra/mongo/init/01_collections.js`). Писать под другим именем значило
    #: держать кэш, который никогда не попадает в индекс: на пустой коллекции
    #: это незаметно, а на выросшей — полный перебор при каждом промахе.
    KEY_FIELD = "content_hash"

    def get(self, key: str) -> dict[str, Any] | None:
        doc = self.collection.find_one({"tenant_id": self.tenant_id, self.KEY_FIELD: key})
        return doc.get("analysis") if doc else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        self.collection.update_one(
            {"tenant_id": self.tenant_id, self.KEY_FIELD: key},
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
    #: Сцены, описание которым досталось от предыдущей — визуально та же
    #: картинка. Отдельно от cache_hits: попадание в кэш означает «это уже
    #: разбирали когда-то», а дедупликация — «соседняя сцена выглядит так же».
    #: Слить их в один счётчик значит потерять способность понять, за что
    #: заплачено и почему у двух сцен одинаковое описание.
    deduped: int = 0
    #: Панели, которые провайдер отказался разбирать. Сцена остаётся в таймлайне
    #: со своими границами и признаком отказа — см. analyze_panels.
    failures: int = 0
    failure_reasons: list[str] = field(default_factory=list)


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

    previous_hash: int | None = None
    previous_analysis: dict[str, Any] | None = None

    for panel in panels:
        # ── Соседняя сцена, визуально неотличимая от предыдущей ─────────────
        #
        # Слайд, который лектор держит три минуты, режется на блоки по 30 секунд
        # (см. build_scenes) — и каждый блок стоил бы отдельного вызова за один и
        # тот же ответ. Кэш здесь не помогает: панели собраны из разных кадров, и
        # байты у них разные, а значит и ключ разный.
        #
        # Сравнение только с НЕПОСРЕДСТВЕННО предыдущей панелью, а не со всеми
        # виденными: возврат к той же локации через десять минут — это событие
        # материала, и описание ему полагается своё. Тем же порогом, что и кадры:
        # 4 бита из 64.
        current_hash = _panel_hash(panel)
        if (
            previous_analysis is not None
            and previous_hash is not None
            and current_hash is not None
            and hamming(current_hash, previous_hash) <= DEDUP_THRESHOLD
        ):
            result.scenes.append(_stamp({**previous_analysis, "deduped": True}, panel))
            result.deduped += 1
            continue

        key = cache_key(panel.image, prompt, model_name)

        cached = cache.get(key) if cache else None
        if cached is not None:
            result.scenes.append(_stamp(cached, panel))
            result.cache_hits += 1
            previous_hash, previous_analysis = current_hash, cached
            continue

        if budget.limit is not None and result.calls_made >= budget.limit:
            raise CostCapExceeded(
                limit=budget.limit,
                scenes=result.scenes,
                remaining=len(panels) - len(result.scenes),
            )

        # ── Отказ на одной панели не отменяет разбор ролика ─────────────────
        #
        # Провайдер отвергает вход по модерации («data_inspection_failed») на
        # отдельных кадрах — и один такой отказ уносил весь прогон, уже
        # оплативший скачивание, прокси, звук, транскрипцию и часть панелей.
        #
        # Выбор тот же, что для опроса персон: панель — независимое наблюдение,
        # и девятнадцать разобранных сцен полезнее, чем ноль. Но сцена остаётся
        # в таймлайне со своими границами: без неё в материале появилась бы
        # дыра, и следующая сцена молча растянулась бы на чужой кусок.
        #
        # Описание при этом НЕ выдумывается. Пустое честнее правдоподобного:
        # персона сошлётся на то, чего не видела, а судья справедливо забракует
        # её ответ.
        try:
            analysis = client.analyze(image=panel.image, prompt=_render(prompt, panel))
        except Exception as exc:  # noqa: BLE001 — причина обязана дойти до отчёта
            result.failures += 1
            reason = (
                f"{panel.timestamp_sec:.2f}–{(getattr(panel, 'end_sec', 0.0) or 0.0):.2f} с: "
                f"{type(exc).__name__}: {exc}"
            )
            result.failure_reasons.append(reason)
            result.scenes.append(_stamp({"analysis_failed": True, "reason": reason}, panel))
            # В кэш отказ не кладётся: иначе повторный прогон получил бы пустое
            # описание бесплатно и не сделал бы ни одной попытки — дефект стал бы
            # постоянным и потому незаметным.
            continue

        result.calls_made += 1
        if cache:
            cache.set(key, analysis)
        result.scenes.append(_stamp(analysis, panel))
        previous_hash, previous_analysis = current_hash, analysis

    # Ноль разобранных сцен — отказ, а не деградация: персонам показывать нечего,
    # и отчёт получился бы по ролику, которого никто не смотрел.
    if panels and result.failures == len(panels):
        raise RuntimeError(
            f"не разобрано ни одной панели из {len(panels)}: "
            f"{'; '.join(result.failure_reasons[:3])}"
        )

    return result


def _panel_hash(panel: Any) -> int | None:
    """
    Перцептивный хеш панели. `None` — посчитать не вышло.

    Отказ хеширования не должен ронять разбор: он всего лишь означает, что
    сцена будет оплачена, хотя могла бы не быть. Ронять из-за этого прогон,
    в котором уже оплачены транскрипция и часть панелей, несоразмерно.
    """
    from .dedup import dhash_bytes

    try:
        return dhash_bytes(panel.image)
    except Exception:  # noqa: BLE001 — см. докстринг
        return None


def _render(template: str, panel: Any) -> str:
    """Подстановка переменных промпта content.frame_analysis."""
    end = getattr(panel, "end_sec", 0.0) or panel.timestamp_sec
    times = getattr(panel, "frame_times", None) or []
    return (
        template
        .replace("{{timestamp}}", f"{panel.timestamp_sec:.2f}")
        .replace("{{scene_start}}", f"{panel.timestamp_sec:.2f}")
        .replace("{{scene_end}}", f"{end:.2f}")
        .replace("{{panel_size}}", str(len(panel.frames) or 1))
        .replace(
            "{{frame_times}}",
            ", ".join(f"{t:.2f}" for t in times) or f"{panel.timestamp_sec:.2f}",
        )
        .replace("{{frames}}", f"панель #{panel.index}")
    )


def _stamp(analysis: dict[str, Any], panel: Any) -> dict[str, Any]:
    """
    Приклеивает к разбору границы сцены из proxy, а не из ответа модели.

    Раньше приклеивался один момент — время первого кадра панели, — и описание
    четырёх разных моментов оказывалось привязано к одному. Персона, сославшаяся
    на середину, получала описание от начала; судья видел несовпадение и был
    прав. Теперь у описания есть начало и конец, и внутри этих границ оно верно
    по построению.

    `timestamp` из ответа модели затирается намеренно: промпт просит его вернуть
    ради связности рассуждения, но единственный источник времени — proxy
    (Decision Log #14). Модель видит только подставленное значение и вольна его
    переписать.
    """
    end = getattr(panel, "end_sec", 0.0) or panel.timestamp_sec
    return {
        **analysis,
        "panel_index": panel.index,
        "timestamp_sec": panel.timestamp_sec,
        "end_sec": end,
        "is_cut": bool(getattr(panel, "is_cut", True)),
        "frame_times": list(getattr(panel, "frame_times", None) or []),
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
        from ..tracing import llm_client

        # Клиент выдаётся agent_core.tracing: там он оборачивается для
        # LangFuse, если трассировка включена, и остаётся обычным, если нет.
        client = llm_client(
            api_key=self.config.api_key,
            base_url=self.config.vlm_base_url,
            default_headers=self.config.default_headers,
            timeout=REQUEST_TIMEOUT_SEC,
        )
        from ..schemas.responses import (
            FRAME_ANALYSIS,
            MAX_TOKENS,
            content_of,
            response_format,
        )

        data_url = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
        response = client.chat.completions.create(
            # Имя наблюдения в трассе. Без него интеграция назовёт
            # генерацию `OpenAI-generation` — одинаково для ответа
            # персоны, вердикта судьи и разбора кадра.
            name="analyze-frame",
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
            # Схема, а не уговоры в промпте: без неё модель вольна ответить
            # прозой, и вся эта проза уезжала в scene_description под флагом
            # parse_failed — то есть в таймлайн, который видит персона.
            response_format=response_format("SceneAnalysis", FRAME_ANALYSIS),
            # Потолок обязателен при схеме — см. MAX_TOKENS.
            max_tokens=MAX_TOKENS["frame_analysis"],
            # Размышление выключено — здесь особенно очевидно: разбор кадра это
            # описание увиденного, а не вывод. См. ModelConfig.thinking.
            extra_body=self.config.extra_body("frames"),
        )
        return _parse_json(content_of(response, role="frame_analysis"))


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
