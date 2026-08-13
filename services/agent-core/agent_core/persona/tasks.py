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

Воркер — то место, где зависимости моделей уже стоят и где задача может идти
столько, сколько нужно.

─── Что видит пользователь ──────────────────────────────────────────────────
Строка набора создаётся веб-маршрутом СРАЗУ, до постановки задачи, и сразу
появляется в списке со статусом `generating`. Дальше эта задача наполняет её,
обновляя `generated_count` после каждой персоны.

Прогресс пишется в Postgres, а не в Valkey. Valkey держит прогресс прогонов с
суточным TTL, и для набора это было бы вторым механизмом ради одного числа;
к тому же список наборов всё равно читается из Postgres — лишний источник
означал бы, что счётчик и список могут разойтись.
"""

from __future__ import annotations

import os
from typing import Any

from ..celery_app import app

#: Как часто писать прогресс в базу.
#:
#: Не после каждой персоны: при пятистах персонах это пятьсот UPDATE по строке,
#: которую в это же время читает список. Каждая пятая — заметно для глаза
#: (обновление раз в несколько секунд) и незаметно для базы.
PROGRESS_EVERY = 5


def _connect(tenant_id: str):
    """Соединение с контекстом арендатора. RLS обязателен и здесь."""
    import psycopg

    from ..db import tenant_scope

    dsn = os.environ["DATABASE_URL"]
    conn = psycopg.connect(dsn)
    return conn, tenant_scope(conn, tenant_id)


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

    conn, scope = _connect(tenant_id)
    try:
        with conn, scope as cur:
            try:
                config = GenerationConfig(**raw_config)
                gen = PersonaGenerator.from_corpus()
                named = gen.generate_named(config)
            except Exception as exc:  # noqa: BLE001 — причина обязана дойти до экрана
                cur.execute(
                    "UPDATE persona_sets SET status='failed', error=%s, finished_at=now() "
                    "WHERE id = %s::uuid",
                    (f"{type(exc).__name__}: {exc}", set_id),
                )
                return {"persona_set_id": set_id, "status": "failed"}

            names = [n for n, _ in named]
            personas = [dna for _, dna in named]

            # ── Обогащение с прогрессом ──────────────────────────────────────
            sources = ["template"] * len(personas)
            meta: dict[str, Any] = {"enriched": False, "llm_calls": 0, "cache_hits": 0}

            if config.use_llm:
                from .enrich import enrich_personas

                def report(done: int, total: int) -> None:  # noqa: ARG001
                    # Пишем не каждую персону — см. PROGRESS_EVERY. Последняя
                    # всё равно доедет: после цикла ставится итоговое число.
                    if done % PROGRESS_EVERY:
                        return
                    cur.execute(
                        "UPDATE persona_sets SET generated_count = %s WHERE id = %s::uuid",
                        (done, set_id),
                    )
                    conn.commit()

                outcome = enrich_personas(personas, on_progress=report)
                personas = outcome.personas
                sources = outcome.sources
                meta = {
                    "enriched": outcome.enriched,
                    "llm_calls": outcome.calls_made,
                    "cache_hits": outcome.cache_hits,
                    "degraded_reason": outcome.degraded_reason,
                }

            # ── Запись персон ────────────────────────────────────────────────
            import json

            for name, dna, source in zip(names, personas, sources, strict=False):
                cur.execute(
                    "INSERT INTO personas (tenant_id, persona_set_id, name, dna, narrative, seed) "
                    "VALUES (current_setting('app.tenant_id')::uuid, %s::uuid, %s, %s, %s, %s)",
                    (
                        set_id,
                        name,
                        json.dumps(dna, ensure_ascii=False),
                        dna.get("narrative"),
                        dna.get("seed"),
                    ),
                )
                _ = source

            cur.execute(
                "UPDATE persona_sets SET status='ready', generated_count=%s, finished_at=now() "
                "WHERE id = %s::uuid",
                (len(personas), set_id),
            )

        return {
            "persona_set_id": set_id,
            "status": "ready",
            "size": len(personas),
            "enrichment": meta,
        }
    finally:
        conn.close()
