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

Поэтому здесь: генерация и обогащение идут ВНЕ транзакции, а персоны пишутся
партиями по пять. Каждая партия — своя короткая транзакция со своим
тенант-контекстом; `generated_count` означает только число уже записанных строк.
Держать транзакцию открытой минутами вредно и само по себе: она держит снимок
и мешает автовакууму.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from ..celery_app import app
from ..portraits.distill import distill_context_file, load_prompt_template

#: Как часто писать прогресс в базу.
#:
#: Не после каждой персоны: при пятистах персонах это пятьсот транзакций по
#: строке, которую в это же время опрашивает список. Каждая пятая — заметно для
#: глаза (обновление раз в несколько секунд) и незаметно для базы.
PROGRESS_EVERY = 5

# Celery повторяет только два раза: вместе с первым заходом это три попытки.
# Небольшая пауза не даёт мгновенно долбить временно недоступную базу или модель.
MAX_RETRIES = 2
RETRY_DELAY_SEC = int(os.environ.get("AUDIENCE_RETRY_DELAY_SEC", 30))

logger = logging.getLogger(__name__)


def _mark_context_file_failed(file_id: str, tenant_id: str, reason: str) -> None:
    """Record a loud extraction failure without hiding the original reason."""
    try:
        _update(
            tenant_id,
            "UPDATE audience_context_files SET status='failed' WHERE id = %s::uuid",
            (file_id,),
        )
    except Exception:
        # The persona set still receives the extraction error. A secondary DB
        # failure must not replace it with a misleading generic message.
        pass


def _load_context_file_portrait(file_id: str, tenant_id: str) -> str:
    """Download, extract, distill, and persist one tenant-owned context file."""
    import psycopg

    from ..db import tenant_scope

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL не задан: файл контекста нельзя прочитать")

    with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
        cur.execute(
            "SELECT f.s3_key, f.filename, f.status, p.body_md "
            "FROM audience_context_files f "
            "LEFT JOIN audience_portraits p ON p.id = f.portrait_id "
            "WHERE f.id = %s::uuid",
            (file_id,),
        )
        row = cur.fetchone()

    if not row:
        raise ValueError("файл контекста не найден или недоступен этому арендатору")
    key, filename, status, existing_portrait = row
    if status == "failed":
        raise ValueError("файл контекста ранее не прошёл разбор")
    if status == "distilled" and isinstance(existing_portrait, str) and existing_portrait.strip():
        return existing_portrait.strip()

    from ..portraits.extract import extract_context_text
    from ..storage import Boto3S3

    with tempfile.TemporaryDirectory(prefix="agora-context-") as directory:
        # Имя пришло из БД, но не должно становиться путём за пределами
        # временного каталога даже при ручной порче строки.
        source = Path(directory) / Path(str(filename)).name
        Boto3S3().download(str(key), source)
        extracted = extract_context_text(source)

    try:
        template = load_prompt_template()
        portrait = distill_context_file(extracted, prompt_template=template)
    except Exception as exc:  # noqa: BLE001 - the file must become failed, not empty
        raise ValueError(f"дистилляция файла не удалась: {type(exc).__name__}: {exc}") from exc
    if not portrait.strip():
        raise ValueError("portrait.distill вернул пустой портрет для файла контекста")

    # A separate short transaction keeps the S3/model work out of a database
    # transaction and makes status visible to the UI as soon as it is durable.
    with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
        cur.execute(
            "INSERT INTO audience_portraits (tenant_id, name, body_md, source) "
            "VALUES (app.current_tenant(), %s, %s, 'context_file') RETURNING id",
            (f"Контекст: {filename}", portrait),
        )
        portrait_id = cur.fetchone()[0]
        cur.execute(
            "UPDATE audience_context_files SET portrait_id=%s::uuid, status='distilled' "
            "WHERE id=%s::uuid",
            (portrait_id, file_id),
        )
    return portrait


def _prepare_generation_config(
    raw_config: dict[str, Any],
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Distill text or a worker-side file before constructing ``GenerationConfig``."""
    file_id = raw_config.get("audience_context_file_id")
    clean = {key: value for key, value in raw_config.items() if key != "audience_context_file_id"}
    if isinstance(file_id, str) and file_id.strip():
        if not tenant_id:
            raise ValueError("tenant_id обязателен для чтения файла контекста")
        try:
            clean["audience_context"] = _load_context_file_portrait(file_id, tenant_id)
        except Exception as exc:  # noqa: BLE001 - status and set must both fail visibly
            _mark_context_file_failed(file_id, tenant_id, str(exc))
            raise ValueError(f"разбор файла контекста не удался: {exc}") from exc
        return clean

    context_file = clean.get("audience_context")
    if not isinstance(context_file, str) or not context_file.strip():
        return clean

    try:
        context_prompt = load_prompt_template()
    except FileNotFoundError:
        context_prompt = None
    return {
        **clean,
        "audience_context": distill_context_file(
            context_file,
            prompt_template=context_prompt,
        ),
    }


class PersonaSetGone(RuntimeError):
    """
    Набор, который наполняет эта задача, исчез из базы.

    Не отказ генерации, а её беспредметность: писать больше некуда, и каждый
    следующий вызов модели оплачивается впустую. См. `_progress_reporter`.
    """

    stop_generation = True


def _update(tenant_id: str, sql: str, params: tuple[Any, ...]) -> int:
    """
    Короткая транзакция со своим тенант-контекстом. Возвращает число строк.

    Отдельное соединение на операцию — намеренно. Долгоживущее соединение
    пришлось бы держать открытым всю генерацию, а тенант-контекст в нём живёт
    ровно транзакцию: продлить его без продления транзакции нельзя.

    `rowcount` возвращается, а не выбрасывается: 18.09.2026 задача двадцать семь
    минут писала прогресс в удалённый набор и считалась работающей, потому что
    `UPDATE` в ноль строк не ошибка ни для psycopg, ни для celery. Смотреть на
    число обязан вызывающий — здесь неизвестно, какой из вызовов имеет право
    попасть в пустоту (`fail` по исчезнувшему набору имеет, прогресс — нет).
    """
    import psycopg

    from ..db import tenant_scope

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, tenant_scope(conn, tenant_id) as cur:
        cur.execute(sql, params)
        return cur.rowcount


#: Запись прогресса генерации. Отдельной константой, потому что её же читает
#: тест исчезнувшего набора: SQL, набранный там заново, разошёлся бы с боевым.
_PROGRESS_SQL = (
    "UPDATE persona_sets SET generated_count = %s, progress_at = now(), "
    "status = CASE WHEN %s >= size THEN 'ready' ELSE 'generating' END, "
    "finished_at = CASE WHEN %s >= size THEN now() ELSE NULL END "
    "WHERE id = %s::uuid AND status = 'generating'"
)
_HEARTBEAT_SQL = (
    "UPDATE persona_sets SET progress_at = now() "
    "WHERE id = %s::uuid AND status = 'generating'"
)


def _progress_reporter(
    tenant_id: str,
    set_id: str,
    *,
    every: int = PROGRESS_EVERY,
    update: Any = _update,
) -> Any:
    """
    Обратный вызов прогресса для `enrich_personas` — и заодно перепроверка того,
    что набор ещё существует.

    ─── Почему проверка живёт здесь, а не отдельным SELECT ────────────────────
    Ответ «набор на месте» уже приходит вместе с отметкой движения: `UPDATE …
    WHERE id = …` возвращает единицу, если строка есть, и ноль, если её нет.
    Отдельный SELECT был бы вторым походом в базу за тем же самым.

    Проверка на старте задачи существует и работает — 18.09.2026 следующая
    задача в очереди упала за 0,066 секунды с внятным «слепок корпуса не
    найден». Но та, что уже стартовала, до конца своих двадцати семи минут ни
    разу не спросила, есть ли ещё куда писать: набор удалили из интерфейса уже
    после её старта, и ни одной персоны она не записала.
    """

    def report(done: int, total: int) -> None:  # noqa: ARG001
        if done % every:
            return
        if update(tenant_id, _HEARTBEAT_SQL, (set_id,)) == 0:
            raise PersonaSetGone(
                f"набор {set_id} исчез во время генерации: писать персон некуда, "
                f"остановлено на {done}"
            )

    return report


def _begin_generation(tenant_id: str, set_id: str) -> dict[str, Any]:
    """Снять неизменяемые параметры набора и вернуть его в generating."""
    import psycopg

    from ..db import tenant_scope

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, tenant_scope(
        conn, tenant_id
    ) as cur:
        cur.execute(
            "SELECT size, generation_config, seed, corpus_snapshot_id::text, "
            "       status, "
            "       (SELECT count(*) FROM personas p "
            "          WHERE p.persona_set_id = persona_sets.id) "
            "FROM persona_sets WHERE id = %s::uuid",
            (set_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise PersonaSetGone(f"набор {set_id} исчез до начала генерации")

        size, generation_config, seed, snapshot_id, status, count = row
        count = int(count or 0)
        cur.execute(
            "UPDATE persona_sets "
            "SET status = CASE WHEN %s >= size THEN 'ready' ELSE 'generating' END, "
            "    generated_count = %s, error = NULL, "
            "    finished_at = CASE WHEN %s >= size THEN now() ELSE NULL END, "
            "    progress_at = now() "
            "WHERE id = %s::uuid",
            (count, count, count, set_id),
        )
        if cur.rowcount == 0:
            raise PersonaSetGone(f"набор {set_id} исчез при запуске генерации")

    stored_config = dict(generation_config or {})
    return {
        "size": int(size),
        "generation_config": stored_config,
        # На resume источник истины именно снимок конфигурации набора. Колонка
        # seed остаётся запасным путём для старых строк до появления этого
        # поля в JSON-снимке.
        "seed": stored_config.get("seed", seed),
        "corpus_snapshot_id": snapshot_id,
        "status": "ready" if count >= int(size) else "generating",
        "generated_count": count,
        "previous_status": status,
    }


def _write_persona_batch(
    tenant_id: str,
    set_id: str,
    *,
    names: list[str],
    personas: list[dict[str, Any]],
    verdicts: list[Any],
    expected_start: int,
    total: int,
) -> int:
    """Атомарно записать одну партию и вернуть фактическое число строк."""
    import psycopg

    from ..db import tenant_scope

    if len(names) != len(personas) or len(verdicts) != len(personas):
        raise ValueError("партия персон имеет рассогласованные списки")

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, tenant_scope(
        conn, tenant_id
    ) as cur:
        # Блокировка только на короткую запись партии делает повтор Celery
        # идемпотентным: две доставки не вставят один и тот же хвост дважды.
        cur.execute(
            "SELECT size FROM persona_sets WHERE id = %s::uuid FOR UPDATE",
            (set_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise PersonaSetGone(f"набор {set_id} исчез перед записью персон")
        set_size = int(row[0])
        cur.execute(
            "SELECT count(*) FROM personas WHERE persona_set_id = %s::uuid",
            (set_id,),
        )
        current = int(cur.fetchone()[0] or 0)
        batch_end = expected_start + len(personas)
        if current >= batch_end:
            return current
        if current != expected_start:
            raise RuntimeError(
                f"набор {set_id}: ожидалось {expected_start} персон, найдено {current}"
            )

        for name, dna, verdict in zip(names, personas, verdicts, strict=True):
            validation = verdict.to_json() if hasattr(verdict, "to_json") else verdict
            cur.execute(
                "INSERT INTO personas (tenant_id, persona_set_id, name, dna, "
                "                      narrative, seed, validation, created_by) "
                "VALUES (app.current_tenant(), %s::uuid, %s, %s, %s, %s, %s, "
                "        (SELECT created_by FROM persona_sets WHERE id = %s::uuid))",
                (
                    set_id,
                    name,
                    json.dumps(dna, ensure_ascii=False),
                    dna.get("narrative"),
                    dna.get("seed"),
                    json.dumps(validation or {}, ensure_ascii=False),
                    set_id,
                ),
            )

        new_count = current + len(personas)
        if new_count > set_size or new_count > total:
            raise RuntimeError(f"набор {set_id}: записано больше заказанного размера")
        cur.execute(
            _PROGRESS_SQL,
            (new_count, new_count, new_count, set_id),
        )
        if cur.rowcount == 0:
            raise PersonaSetGone(f"набор {set_id} исчез при записи прогресса")
        return new_count


def _fail_set(tenant_id: str, set_id: str, reason: str) -> None:
    rowcount = _update(
        tenant_id,
        "UPDATE persona_sets SET status='failed', error=%s, finished_at=now() "
        "WHERE id = %s::uuid",
        (reason, set_id),
    )
    if rowcount == 0:
        raise PersonaSetGone(f"набор {set_id} исчез при записи отказа")


@app.task(name="agora.generate_audience", bind=True)
def generate_audience(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Запустить генерацию или докачать только хвост существующего набора."""
    set_id = str(payload["persona_set_id"])
    tenant_id = str(payload["tenant_id"])

    try:
        state = _begin_generation(tenant_id, set_id)
        if state["status"] == "ready":
            return {"persona_set_id": set_id, "status": "ready", "size": state["size"]}
        return _generate_audience_once(payload, state)
    except PersonaSetGone as gone:
        # Набор удалён: повторять нечего, и писать в него уже нельзя.
        logger.warning("генерация аудитории прервана: %s", gone)
        return {"persona_set_id": set_id, "status": "abandoned", "error": str(gone)}
    except Exception as exc:  # noqa: BLE001 - Celery должен получить retry
        retries = int(getattr(getattr(self, "request", None), "retries", 0) or 0)
        if retries < MAX_RETRIES:
            retry_payload = {**payload, "resume": True}
            raise self.retry(
                args=(retry_payload,), exc=exc, countdown=RETRY_DELAY_SEC
            ) from exc

        reason = (
            f"генерация аудитории не удалась после {MAX_RETRIES + 1} попыток: "
            f"{type(exc).__name__}: {exc}"
        )
        try:
            _fail_set(tenant_id, set_id, reason)
        except PersonaSetGone:
            return {"persona_set_id": set_id, "status": "abandoned", "error": str(exc)}
        return {"persona_set_id": set_id, "status": "failed", "error": reason}


def _generate_audience_once(
    payload: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    """Сгенерировать полный детерминированный скелет и обработать только хвост."""
    from dataclasses import fields

    from .. import tracing
    from ..config import PersonaAttemptsConfig, TemperatureConfig
    from .enrich import QwenTextClient, enrich_personas
    from .generator import GenerationConfig, PersonaGenerator
    from .validate import validate_set

    set_id = str(payload["persona_set_id"])
    tenant_id = str(payload["tenant_id"])
    allowed = {field.name for field in fields(GenerationConfig)}
    raw_config = {
        key: value for key, value in state["generation_config"].items() if key in allowed
    }
    raw_config["size"] = state["size"]
    if state["seed"] is not None:
        raw_config["seed"] = int(state["seed"])
    raw_config = _prepare_generation_config(raw_config, tenant_id)
    config = GenerationConfig(**raw_config)

    snapshot_id = state.get("corpus_snapshot_id")
    gen = (
        PersonaGenerator.from_snapshot(snapshot_id, tenant_id)
        if snapshot_id
        else PersonaGenerator.from_corpus()
    )
    named = gen.generate_named(config)
    if len(named) != state["size"]:
        raise RuntimeError(
            f"генератор вернул {len(named)} персон вместо {state['size']}"
        )

    resume = bool(payload.get("resume"))
    start = int(state["generated_count"])
    if resume:
        logger.info("Докачка набора %s начинается с персон %s", set_id, start)
    names = [name for name, _ in named][start:]
    personas = [dna for _, dna in named][start:]
    settings_snapshot = payload.get("settings_snapshot")
    temperatures = TemperatureConfig.for_task(settings_snapshot)
    attempts = PersonaAttemptsConfig.for_task(settings_snapshot).attempts
    portraits = _load_portraits(tenant_id)
    enrichment_meta: dict[str, Any] = {
        "enriched": False,
        "llm_calls": 0,
        "cache_hits": 0,
    }
    validation_meta: dict[str, Any] = {
        "checked": 0,
        "regenerated": 0,
        # Сколько портретов переписано на ТОМ ЖЕ скелете вместо розыгрыша
        # нового. Отдельно от `regenerated`, потому что это разные события:
        # переписывание сохраняет выборку из корпуса, пересоздание её меняет.
        "reenriched": 0,
        # Сколько раз судья нашёл несовместимость МЕЖДУ атрибутами, а не между
        # текстом и атрибутами. Это счётчик про генератор, а не про персону, и
        # он отвечает на отдельный вопрос: стоит ли переходить к связанному
        # сэмплированию. Раньше такого числа не было ни у кого.
        "attribute_conflicts": 0,
        "failed": 0,
        "calls": 0,
    }

    trace = tracing.run(
        task_id=set_id,
        tenant_id=tenant_id,
        trace_name="аудитория",
        kind="generate_audience",
        size=len(personas),
        tags=["audience"],
    )
    with trace:
        for batch_start in range(0, len(personas), PROGRESS_EVERY):
            batch_names = names[batch_start:batch_start + PROGRESS_EVERY]
            batch_personas = personas[batch_start:batch_start + PROGRESS_EVERY]

            if config.use_llm and batch_personas:
                outcome = enrich_personas(
                    batch_personas,
                    names=batch_names,
                    on_progress=_progress_reporter(tenant_id, set_id),
                    temperature=temperatures.personaCreation,
                    portraits=portraits,
                )
                batch_personas = outcome.personas
                enrichment_meta["enriched"] = enrichment_meta["enriched"] or outcome.enriched
                enrichment_meta["llm_calls"] += outcome.calls_made
                enrichment_meta["cache_hits"] += outcome.cache_hits
                if outcome.degraded_reason:
                    enrichment_meta["degraded_reason"] = outcome.degraded_reason

            batch_verdicts: list[Any] = [{} for _ in batch_personas]
            if config.use_llm and batch_personas:
                validated_names = list(batch_names)
                absolute_start = start + batch_start
                # Источник для переписывания — текущее состояние персоны в
                # партии. Скелет, имя и портрет сегмента остаются прежними:
                # виноват текст, и менять из-за него розыгрыш из корпуса
                # значит смещать состав набора в сторону персон, которых легко
                # описать прозой.
                reenrich_sources = list(batch_personas)

                def reenrich(
                    index: int,
                    issues: list[Any],
                    *,
                    reenrich_sources: list[dict[str, Any]] = reenrich_sources,
                    validated_names: list[str] = validated_names,
                ) -> dict[str, Any] | None:
                    """Переписывает narrative, сохраняя скелет, имя и портрет."""
                    try:
                        outcome = enrich_personas(
                            [reenrich_sources[index]],
                            names=[validated_names[index]],
                            temperature=temperatures.personaCreation,
                            portraits=portraits,
                            revision_issues=issues,
                        )
                        if not outcome.personas:
                            return None
                        replacement = outcome.personas[0]
                        reenrich_sources[index] = replacement
                        return replacement
                    except Exception:  # noqa: BLE001 — следующая ступень возьмёт новый seed
                        return None

                def regenerate(
                    index: int,
                    attempt: int,
                    *,
                    absolute_start: int = absolute_start,
                    validated_names: list[str] = validated_names,
                ) -> dict[str, Any] | None:
                    absolute = absolute_start + index
                    try:
                        shifted = GenerationConfig(
                            **{
                                **raw_config,
                                "size": 1,
                                "seed": (config.seed or 0) + 10_000 * attempt + absolute,
                            }
                        )
                        fresh = gen.generate_named(shifted)
                        if not fresh:
                            return None
                        replacement_name, replacement_dna = fresh[0]
                        replacement = enrich_personas(
                            [replacement_dna],
                            names=[replacement_name],
                            temperature=temperatures.personaCreation,
                            portraits=portraits,
                        ).personas[0]
                        validated_names[index] = replacement_name
                        return replacement
                    except Exception:  # noqa: BLE001 - keep the original persona
                        return None

                from ..schemas.responses import MAX_TOKENS, PERSONA_VALIDATION

                # Отказ проверки не роняет партию. Проверка связности —
                # улучшение качества, а не условие работоспособности: сорвать
                # из-за неё оплаченную генерацию значит поменять надёжный
                # результат на аккуратный. Партионная запись этого правила не
                # отменяет — наоборот, теперь на кону ещё и уже записанные
                # партии, которые пришлось бы бросить в статусе generating.
                try:
                    validation = validate_set(
                        batch_personas,
                        client=QwenTextClient(
                            temperature=temperatures.personaValidation,
                            response_schema=("PersonaValidation", PERSONA_VALIDATION),
                            max_tokens=MAX_TOKENS["persona_validation"],
                        ),
                        reenrich=reenrich,
                        regenerate=regenerate,
                        verbatim_pool=_judge_pool(gen.dist.verbatims),
                        max_attempts=attempts,
                    )
                except Exception as exc:  # noqa: BLE001 — см. комментарий выше
                    validation_meta["degraded_reason"] = (
                        f"{type(exc).__name__}: {exc}"
                    )
                else:
                    batch_personas = validation.personas
                    batch_names = validated_names
                    batch_verdicts = validation.verdicts
                    for key in (
                        "checked",
                        "regenerated",
                        "reenriched",
                        "attribute_conflicts",
                        "failed",
                        "calls",
                    ):
                        validation_meta[key] += getattr(validation, key)

            _write_persona_batch(
                tenant_id,
                set_id,
                names=batch_names,
                personas=batch_personas,
                verdicts=batch_verdicts,
                expected_start=start + batch_start,
                total=state["size"],
            )

    return {
        "persona_set_id": set_id,
        "status": "ready",
        "size": state["size"],
        "enrichment": enrichment_meta,
        "validation": validation_meta,
    }


def _judge_pool(verbatims: list[str], n: int = 20) -> list[str]:
    """
    Образец речи корпуса для судьи связности.

    `persona.validate.md` бракует за «досочинённый факт» — подробность, которой
    нет «ни в атрибутах, НИ В РЕПЛИКАХ КОРПУСА». До этой правки раздел с репликами
    рендерился пустым при каждой проверке: `validate_set` принимает пул
    необязательным параметром, и продовый вызов его не передавал. Судью просили
    сверить текст с образцом, а образец не показывали.

    Берём с равномерным шагом, а не первые двадцать: `validate._render` обрезает
    пул до двадцати реплик, а в порядке корпуса это почти один материал —
    17 из 20 приходились на «Константинополь». Шаг сохраняет детерминизм и даёт
    речь со всего корпуса.
    """
    from .generator import even_sample

    return even_sample(verbatims, n)


def _load_portraits(tenant_id: str) -> dict[str, str]:
    """
    Портреты сегментов команды: `{ключ сегмента: текст}`.

    Отказ чтения — не отказ сборки аудитории. Портрет улучшает описание
    персоны, а не делает её возможной; уронить из-за него набор значило бы
    поменять надёжный результат на красивый.

    Берутся только портреты С сегментом: заведённые вручную его не имеют, и
    сопоставить их с персоной не по чему. Имя для этого не годится — человек
    правит его руками, и матчинг по имени сломался бы на первом переименовании
    молча, оставив персону без портрета.
    """
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return {}
    try:
        import psycopg

        from ..db import tenant_scope

        with psycopg.connect(dsn) as conn, tenant_scope(conn, tenant_id) as cur:
            cur.execute(
                # DISTINCT ON, а не просто SELECT: 11.09.2026 в базе лежало по
                # ДВА портрета на сегмент — дистилляция добавляла запись вместо
                # замены. Без сортировки словарь оставлял последнюю строку из
                # выдачи, а Postgres её порядок не гарантирует: какой из двух
                # портретов достанется персоне, решал случай.
                #
                # Проявилось бы это так: два одинаковых прогона дают разные
                # описания персон — при тех же настройках, критериях и seed.
                # Искать причину пришлось бы где угодно, только не здесь.
                #
                # Побеждает свежий по updated_at: он и есть тот, который человек
                # видит в разделе «Портреты».
                "SELECT DISTINCT ON (segment_key) segment_key, body_md "
                "  FROM audience_portraits "
                " WHERE segment_key IS NOT NULL AND body_md <> '' "
                " ORDER BY segment_key, updated_at DESC, id DESC"
            )
            return {str(k): str(v) for k, v in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}
