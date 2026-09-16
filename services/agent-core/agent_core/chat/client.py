"""
Вызов модели для чата — потоком.

─── Почему поток, а не готовый ответ ────────────────────────────────────────
Решение владельца. Ответ аналитика по отчёту — это абзацы, и ждать их молча
десять секунд хуже, чем читать по мере написания.

Цена названа и принята: `has_support` применяется к дописанному тексту, то есть
уже показанному. Ответ без опоры не убирается с экрана, а помечается — см.
`agent.py`.

─── Температура берётся из настроек прогона ─────────────────────────────────
Стадия `aggregation` для аналитика: он обязан быть воспроизводимым, вопрос по
одному отчёту не должен давать разные числа. Стадия `responseSimulation` для
персоны: она отвечает как человек, и нулевая температура сделала бы её
протоколом.

Разные стадии для двух режимов — не мелочь: одно значение на оба означало бы
либо плавающего аналитика, либо картонную персону.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

#: Потолок ответа. Чат — это реплика, а не отчёт: длинный ответ здесь чаще
#: означает, что модель пересказывает контекст, чем что вопрос был сложный.
MAX_TOKENS = 1200

#: Таймаут одного вызова. Больше, чем у судьи: контекст аналитика — весь отчёт
#: и все ответы персон, и первый токен приходит не сразу.
REQUEST_TIMEOUT_SEC = 180


def stream_reply(
    *,
    system: str,
    user: str,
    mode: str,
    config: Any | None = None,
    temperature: float | None = None,
) -> Iterator[str]:
    """
    Отдаёт куски ответа по мере генерации.

    Имя наблюдения зависит от режима: без него LangFuse назовёт обе генерации
    одинаково, и разобрать, сколько стоил аналитик, а сколько допрос персоны,
    будет нечем. Ровно эта ошибка уже случалась с обогащением и проверкой
    персон — 198 вызовов под одним именем.
    """
    from ..config import ModelConfig, TemperatureConfig
    from ..tracing import llm_client

    cfg = config or ModelConfig.from_env()

    # Роль берётся из существующего перечня, а не заводится седьмая.
    #
    # Аналитик — это `analytics`: он обязан быть воспроизводимым, и режим
    # размышления у него настраивается тем же переключателем, что у сборки
    # отчёта. Допрос персоны — `respondent`: она отвечает как зритель, теми же
    # правилами, что и в прогоне. Своя роль означала бы, что настройка
    # «размышление» в интерфейсе на чат не действует, и заметить это можно было
    # бы только по счёту.
    role = "analytics" if mode == "analyst" else "respondent"

    if temperature is None:
        defaults = TemperatureConfig.defaults()
        temperature = (
            defaults.aggregation if mode == "analyst" else defaults.responseSimulation
        )

    client = llm_client(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        default_headers=cfg.default_headers,
        timeout=REQUEST_TIMEOUT_SEC,
    )

    stream = client.chat.completions.create(
        name=f"chat-{mode}",
        model=cfg.text_model,
        temperature=temperature,
        max_tokens=MAX_TOKENS,
        stream=True,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        # Выключатель размышления. Ключ `enable_thinking`, а не `thinking`:
        # второй этот шлюз игнорирует — замер дал 480 токенов вывода против 4.
        extra_body=cfg.extra_body(role),
    )

    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        piece = getattr(delta, "content", None) if delta else None
        if piece:
            yield piece


def call_with_tools(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    mode: str,
    config: Any | None = None,
    temperature: float | None = None,
) -> tuple[list[Any], Iterator[str] | None]:
    """
    Один заход в шлюз: либо вызовы инструментов, либо поток ответа.

    ─── Почему не поток, когда есть инструменты ──────────────────────────────
    Вызов инструмента — это не текст, а структура, и собрать её из кусков
    потока можно только целиком. Пока модель решает, что запросить, показывать
    нечего: раунды идут ДО ответа. Поэтому заход с инструментами —
    непотоковый, а финальный (инструментов нет) — потоковый, как и прежде.

    Так поток остаётся ровно там, ради чего владелец его выбрал: на прозе,
    которую читает человек.

    ─── Почему возвращается пара ─────────────────────────────────────────────
    Шлюз сам решает, звать инструменты или отвечать. Вызывающий обязан уметь
    оба исхода, и пара «вызовы, поток» заставляет его это учесть: один из
    членов всегда пуст, и перепутать их нельзя.
    """
    from ..config import ModelConfig, TemperatureConfig
    from .loop import ToolCall

    cfg = config or ModelConfig.from_env()
    role = "analytics" if mode == "analyst" else "respondent"

    if temperature is None:
        defaults = TemperatureConfig.defaults()
        temperature = (
            defaults.aggregation if mode == "analyst" else defaults.responseSimulation
        )

    if not tools:
        return [], _stream(
            messages=messages, mode=mode, cfg=cfg, role=role, temperature=temperature
        )

    from ..tracing import llm_client

    client = llm_client(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        default_headers=cfg.default_headers,
        timeout=REQUEST_TIMEOUT_SEC,
    )
    response = client.chat.completions.create(
        name=f"chat-{mode}-tools",
        model=cfg.text_model,
        temperature=temperature,
        max_tokens=MAX_TOKENS,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        extra_body=cfg.extra_body(role),
    )
    choice = response.choices[0]
    raw_calls = getattr(choice.message, "tool_calls", None) or []

    calls = []
    for call in raw_calls:
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            # Модель прислала не-JSON в аргументах. Пустой словарь честнее
            # отказа: инструмент ответит тем, что умеет по умолчанию, и
            # разговор продолжится.
            args = {}
        calls.append(
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=args if isinstance(args, dict) else {},
            )
        )

    if calls:
        return calls, None

    # Инструменты были предложены, но модель ответила текстом. Он уже получен
    # целиком — отдаём его одним куском, а не ходим в шлюз второй раз.
    return [], iter([choice.message.content or ""])


def _stream(
    *, messages: list[dict[str, Any]], mode: str, cfg: Any, role: str, temperature: float
) -> Iterator[str]:
    """Потоковый заход без инструментов — тот же, что у `stream_reply`."""
    from ..tracing import llm_client

    client = llm_client(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        default_headers=cfg.default_headers,
        timeout=REQUEST_TIMEOUT_SEC,
    )
    stream = client.chat.completions.create(
        name=f"chat-{mode}",
        model=cfg.text_model,
        temperature=temperature,
        max_tokens=MAX_TOKENS,
        stream=True,
        messages=messages,
        extra_body=cfg.extra_body(role),
    )
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        piece = getattr(delta, "content", None) if delta else None
        if piece:
            yield piece
