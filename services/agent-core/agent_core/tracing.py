"""
Трассировка вызовов модели — LangFuse.

─── Зачем ────────────────────────────────────────────────────────────────────
Прогон исследования — это от сорока до нескольких сотен вызовов модели: разбор
каждой панели кадров, обогащение каждой персоны, её ответ на каждый вопрос,
вердикт судьи по каждому ответу, сборка отчёта. Наружу из всего этого выходило
одно число — «диаризация 1111 секунд» — и список отбраковок без причин.

Каждый разбор этой сессии упирался в одно и то же: чтобы понять, почему судья
забраковал ответ, приходилось лезть в `qa_report.json` внутри контейнера,
который умирает вместе с прогоном. Трассировка — тот же разбор, но без
раскопок и после того, как контейнера уже нет.

─── Почему всё через один модуль ─────────────────────────────────────────────
Шесть мест в коде поднимают `OpenAI(...)` самостоятельно. Обернуть пять из них
и забыть шестое — дефект, который ничем себя не проявляет: прогон идёт, трассы
приходят, и только одного вида вызовов в них нет. Поэтому клиент выдаётся
отсюда, а тест на стыке проверяет, что мест с прямым `OpenAI(` не осталось.

─── Почему без ключей ничего не меняется ─────────────────────────────────────
Трассировка — наблюдение за продуктом, а не его часть. Разработчик без LangFuse,
CI без LangFuse и прогон при упавшем LangFuse обязаны идти как раньше. Иначе
установка наблюдения добавила продукту новую точку отказа — ровно то, от чего
наблюдение и должно защищать.
"""

from __future__ import annotations

import contextlib
import os
import re
from typing import Any

#: Переменные окружения. Имена — те, что понимает SDK сам; свои завести значило
#: бы иметь два источника правды и разъехаться с документацией LangFuse.
PUBLIC_KEY = "LANGFUSE_PUBLIC_KEY"
SECRET_KEY = "LANGFUSE_SECRET_KEY"
BASE_URL = "LANGFUSE_BASE_URL"

#: Разобранный клиент. Кэшируется: создание поднимает фоновый поток отправки, и
#: делать это на каждый вызов модели значило бы завести по потоку на вызов.
_client: Any = None
_configured = False


# ─────────────────────────────────────────────────────────────────────────
# Маска
# ─────────────────────────────────────────────────────────────────────────
#
# Маскируются УЧЁТНЫЕ данные, а не предметные. Ответы персон, содержимое
# корпуса и промпты в трассу уезжают целиком — ради них трассировка и ставится,
# и трасса, из которой вырезано содержание, не отвечает ни на один вопрос,
# ради которого её открывают.
#
# Ключ провайдера — другое дело. Трасса живёт дольше прогона, смотрится шире и
# выгружается целиком; ключ, попавший туда, скомпрометирован так же, как
# попавший в git (CLAUDE.md §7).
_SECRETS = (
    # Ключи вида sk-…, pk-…, включая sk-lf-… самого LangFuse.
    re.compile(r"\b[a-z]{2}-(?:[a-z]{2}-)?[A-Za-z0-9_\-]{16,}"),
    # Заголовок авторизации вместе со значением.
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}", re.IGNORECASE),
    # Пароль внутри строки подключения: схема://логин:ПАРОЛЬ@хост.
    re.compile(r"(?<=://)[^:/\s]+:[^@/\s]+(?=@)"),
)

MASKED = "[скрыто]"


def mask(*, data: Any) -> Any:
    """
    Замена учётных данных на заглушку. Сигнатура с именованным `data` — та, что
    вызывает SDK; менять её нельзя, даже если она выглядит странно.
    """
    if isinstance(data, str):
        out = data
        for pattern in _SECRETS:
            out = pattern.sub(MASKED, out)
        return out
    if isinstance(data, dict):
        return {k: mask(data=v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return type(data)(mask(data=v) for v in data)
    return data


# ─────────────────────────────────────────────────────────────────────────
# Клиент
# ─────────────────────────────────────────────────────────────────────────

def enabled() -> bool:
    """Есть ли чем трассировать. Оба ключа обязательны, адрес — тоже."""
    return all(os.environ.get(name) for name in (PUBLIC_KEY, SECRET_KEY, BASE_URL))


def reset() -> None:
    """
    Забыть разобранное состояние. Нужно тестам: ключи в них меняются, а клиент
    кэширован, и без сброса второй тест работал бы клиентом первого.
    """
    global _client, _configured
    _client = None
    _configured = False


def client() -> Any:
    """Клиент LangFuse или None. Создаётся один раз на процесс."""
    global _client, _configured
    if _configured:
        return _client
    _configured = True
    if not enabled():
        _client = None
        return None

    from langfuse import Langfuse

    _client = Langfuse(
        public_key=os.environ[PUBLIC_KEY],
        secret_key=os.environ[SECRET_KEY],
        host=os.environ[BASE_URL],
        # Маска ставится на клиенте, а не на каждом вызове: пропущенный вызов
        # означал бы ключ в трассе, а это не та ошибка, которую ловят ревью.
        mask=mask,
        environment=os.environ.get("LANGFUSE_ENVIRONMENT", "production"),
    )
    return _client


def llm_client(
    *,
    api_key: str,
    base_url: str,
    default_headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> Any:
    """
    Клиент провайдера моделей — обёрнутый, если есть чем трассировать.

    Обёртка LangFuse — это подмена того же класса `OpenAI`, поэтому вызывающий
    код не отличает один от другого и не должен: `if` по включённости
    трассировки в шести местах разъехался бы при первой же правке.
    """
    kwargs: dict[str, Any] = {"api_key": api_key, "base_url": base_url}
    if default_headers is not None:
        kwargs["default_headers"] = default_headers
    if timeout is not None:
        kwargs["timeout"] = timeout

    if client() is None:
        from openai import OpenAI

        return OpenAI(**kwargs)

    # Импорт ПОСЛЕ того, как клиент LangFuse создан: обёртка читает настройки
    # при импорте, и обратный порядок дал бы клиент без ключей — молча, потому
    # что он всё равно работает, просто никуда не пишет.
    from langfuse.openai import OpenAI as TracedOpenAI

    return TracedOpenAI(**kwargs)


# ─────────────────────────────────────────────────────────────────────────
# Спаны
# ─────────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def run(task_id: str, tenant_id: str, **attrs: Any):
    """
    Корневой спан прогона. Всё, что случится внутри, ляжет под него.

    `session_id` — идентификатор задачи: в LangFuse это то, что группирует
    разрозненные вызовы в одно наблюдаемое событие, а прогон исследования и
    есть такое событие. `user_id` — арендатор: он же в фильтрах и в разбивке
    стоимости, а настоящего пользователя внутри воркера нет.
    """
    lf = client()
    if lf is None:
        yield None
        return

    with lf.start_as_current_span(name="pipeline") as span:
        span.update_trace(
            name=f"прогон {task_id}",
            session_id=task_id,
            user_id=tenant_id,
            tags=[f"tenant:{tenant_id}", *(attrs.pop("tags", []) or [])],
            metadata={"task_id": task_id, "tenant_id": tenant_id, **attrs},
        )
        try:
            yield span
        finally:
            # Отправка здесь, а не в конце процесса: воркер живёт долго, и
            # трасса, ждущая выхода процесса, не появится вовсе — а нужна она
            # ровно тогда, когда прогон только что кончился.
            lf.flush()


@contextlib.contextmanager
def stage(name: str, task_id: str = "", tenant_id: str = "", **attrs: Any):
    """
    Спан узла конвейера. Даёт то, чего нет в замерах длительности: из чего
    состоят секунды узла и какой вызов внутри него отказал.
    """
    lf = client()
    if lf is None:
        yield None
        return

    metadata = {k: v for k, v in attrs.items() if v is not None}
    if task_id:
        metadata["task_id"] = task_id
    if tenant_id:
        metadata["tenant_id"] = tenant_id

    with lf.start_as_current_span(name=name, metadata=metadata or None) as span:
        yield span


def flush() -> None:
    """Дослать накопленное. Безопасно при выключенной трассировке."""
    lf = client()
    if lf is not None:
        lf.flush()
