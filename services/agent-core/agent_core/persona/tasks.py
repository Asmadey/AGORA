"""
Генерация аудитории как фоновая задача Celery.

─── Почему это переехало из веба ────────────────────────────────────────────
Маршрут `/api/audience` запускал `python3 -m agent_core.persona.generate_cli`
подпроцессом и ждал результата с таймаутом 120 секунд. Обогащение при этом —
последовательный цикл: один вызов модели на персону, до 60 секунд на каждый.
Шестьдесят персон в такой бюджет не помещаются никак: пользователь видел
спиннер, который однажды превращался в ошибку, а всё написанное к этому моменту
выбрасывалось.

Здесь же решается вторая, менее заметная беда: в образе веба нет `openai`.
Обогащение оттуда всегда падало на `ModuleNotFoundError`, честно сообщало
`enriched: false` — и narrative у всех персон оставался скелетным. То есть
самая дорогая часть генерации не работала вообще, а выглядело это как
«деградация», которую все привыкли видеть.

─── Транзакции: короткие, а не одна на весь прогон ──────────────────────────
Первая редакция держала одну транзакцию открытой всю генерацию и писала в неё
прогресс. Это не работало по двум причинам сразу, и обе тихие:

1. Незакоммиченная строка не видна читателю. Список наборов опрашивается извне
   и показал бы ноль до самого конца, каким бы ни был счётчик внутри.
2. `tenant_scope` ставит арендатора транзакционно (`set_config(…, true)`), и
   `SET LOCAL ROLE` — тоже. Коммит изнутри `conn.transaction()` psycopg
   отвергает, а обёртка прогресса исключение глотает: прогресс молча не
   писался, и заметить это можно было только по нулю на экране.

Поэтому здесь: генерация и обогащение идут ВНЕ транзакции, каждое обновление
прогресса — своя короткая транзакция со своим тенант-контекстом, запись персон —
одна транзакция в конце. Держать транзакцию открытой минутами вредно и само по
себе: она держит снимок и мешает автовакууму.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..celery_app import app

#: Как часто писать прогресс в базу.
#:
#: Не после каждой персоны: при пятистах персонах это пятьсот транзакций по
#: строке, которую в это же время опрашивает список. Каждая пятая — заметно для
#: глаза (обновление раз в несколько секунд) и незаметно для базы.
PROGRESS_EVERY = 5


def _update(tenant_id: str, sql: str, params: tuple[Any, ...]) -> None:
    """
    Короткая транзакция со своим тенант-контекстом.

    Отдельное соединение на операцию — намеренно. Долгоживущее соединение
    пришлось бы держать открытым всю генерацию, а тенант-контекст в нём живёт
    ровно транзакцию: продлить его без продления транзакции нельзя.
    """
    import psycopg

    from ..db import tenant_scope

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, tenant_scope(conn, tenant_id) as cur:
        cur.execute(sql, params)


@app.task(name="agora.generate_audience", bind=True)
def generate_audience(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Наполняет уже созданный набор персонами.

    `payload`: persona_set_id, tenant_id, config (критерии генерации).

    Отказ помечает набор `failed` с причиной. Пустой набор — заведомо
    провальный прогон (маршрут запуска его теперь и не примет), поэтому
    состояние обязано быть видно на экране, а не только в логах воркера.
    """
    from .generator import GenerationConfig, PersonaGenerator

    set_id = str(payload["persona_set_id"])
    tenant_id = str(payload["tenant_id"])
    raw_config = payload.get("config") or {}
    snapshot_id = payload.get("corpus_snapshot_id")

    def fail(reason: str) -> dict[str, Any]:
        _update(
            tenant_id,
            "UPDATE persona_sets SET status='failed', error=%s, finished_at=now() "
            "WHERE id = %s::uuid",
            (reason, set_id),
        )
        return {"persona_set_id": set_id, "status": "failed", "error": reason}

    # ── Скелеты ──────────────────────────────────────────────────────────────
    try:
        config = GenerationConfig(**raw_config)
        # Слепок корпуса, снятый при создании аудитории, — главнее файла в
        # образе. Файл остаётся запасным путём для наборов, созданных до того,
        # как корпус переехал в базу; молча предпочитать его слепку значило бы
        # собирать персон не по тому корпусу, который выбрал пользователь.
        gen = (
            PersonaGenerator.from_snapshot(str(snapshot_id), tenant_id)
            if snapshot_id
            else PersonaGenerator.from_corpus()
        )
        named = gen.generate_named(config)
    except Exception as exc:  # noqa: BLE001 — причина обязана дойти до экрана
        return fail(f"{type(exc).__name__}: {exc}")

    names = [n for n, _ in named]
    personas = [dna for _, dna in named]

    # ── Обогащение с прогрессом ──────────────────────────────────────────────
    meta: dict[str, Any] = {"enriched": False, "llm_calls": 0, "cache_hits": 0}
    if config.use_llm:
        from .enrich import enrich_personas

        def report(done: int, total: int) -> None:  # noqa: ARG001
            if done % PROGRESS_EVERY:
                return
            _update(
                tenant_id,
                "UPDATE persona_sets SET generated_count = %s WHERE id = %s::uuid",
                (done, set_id),
            )

        try:
            outcome = enrich_personas(personas, on_progress=report)
        except Exception as exc:  # noqa: BLE001
            return fail(f"обогащение не удалось: {type(exc).__name__}: {exc}")

        personas = outcome.personas
        meta = {
            "enriched": outcome.enriched,
            "llm_calls": outcome.calls_made,
            "cache_hits": outcome.cache_hits,
            "degraded_reason": outcome.degraded_reason,
        }

    # ── Запись персон одной транзакцией ──────────────────────────────────────
    # Все или ни одной: наполовину записанный набор выглядит готовым и даёт
    # отчёт по случайной части аудитории.
    import psycopg

    from ..db import tenant_scope

    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn, tenant_scope(
            conn, tenant_id
        ) as cur:
            for name, dna in zip(names, personas, strict=False):
                cur.execute(
                    "INSERT INTO personas (tenant_id, persona_set_id, name, dna, narrative, seed) "
                    "VALUES (app.current_tenant(), %s::uuid, %s, %s, %s, %s)",
                    (
                        set_id,
                        name,
                        json.dumps(dna, ensure_ascii=False),
                        dna.get("narrative"),
                        dna.get("seed"),
                    ),
                )
            cur.execute(
                "UPDATE persona_sets SET status='ready', generated_count=%s, finished_at=now() "
                "WHERE id = %s::uuid",
                (len(personas), set_id),
            )
    except Exception as exc:  # noqa: BLE001
        return fail(f"персоны не сохранены: {type(exc).__name__}: {exc}")

    return {
        "persona_set_id": set_id,
        "status": "ready",
        "size": len(personas),
        "enrichment": meta,
    }
