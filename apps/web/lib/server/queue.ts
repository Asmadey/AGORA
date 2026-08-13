import "server-only";

import { randomUUID } from "node:crypto";

import { valkey } from "@/lib/server/valkey";

/**
 * Постановка прогона в очередь воркера (задачи #11 → #13).
 *
 * ─── Зачем это здесь ───────────────────────────────────────────────────────
 * До этого запуск исследования создавал строку в `tasks` и на этом
 * заканчивался: воркер о ней не узнавал. Экран прогресса показывал бы QUEUED
 * вечно — а это выглядит как медленная система, не как ненаписанный вызов.
 * Тот же класс разрыва, что был в цепочке «Аудитория»: каждое звено исправно,
 * вместе не работает, и ни одна задача графа за это не отвечает.
 *
 * ─── Почему сообщение собирается руками, а не через клиент Celery ──────────
 * Клиента Celery для Node нет, а веб и воркер общаются только через Valkey
 * (Decision Log #3) — общей HTTP-границы между ними в развёртывании TimeWeb
 * нет вовсе: воркер живёт отдельно от App Platform.
 *
 * Формат — протокол задач Celery версии 2. Набор заголовков не выдуман: он
 * снят с `celery.app.amqp.as_task_v2` и проверяется CDD-тестом #12, который
 * сверяет список ниже с тем, что Celery выдаёт на самом деле. Обновление
 * Celery, изменившее имя заголовка, покраснит тест, а не сломает прод молча.
 */

/** Очередь по умолчанию. Совпадает с `task_default_queue` воркера. */
const QUEUE = "celery";

export interface PipelinePayload {
  task_id: string;
  tenant_id: string;
  mode: "short" | "long";
  video_ref: string | null;
  persona_ids: string[];
  survey: unknown;
  replication_count: number;
  prompts_snapshot: Record<string, unknown>;
}

/**
 * Заголовки протокола 2. Порядок неважен, состав — важен: воркер отвергает
 * сообщение без `task` и `id`, а без `argsrepr`/`kwargsrepr` теряет читаемость
 * в мониторинге.
 */
function headers(taskId: string, args: unknown[], taskName: string) {
  return {
    lang: "py",
    task: taskName,
    id: taskId,
    shadow: null,
    eta: null,
    expires: null,
    group: null,
    group_index: null,
    retries: 0,
    timelimit: [null, null],
    root_id: taskId,
    parent_id: null,
    argsrepr: JSON.stringify(args),
    kwargsrepr: "{}",
    origin: "agora-web",
    ignore_result: false,
    replaced_task_nesting: 0,
    stamped_headers: null,
    stamps: {},
  };
}

export function buildMessage(
  payload: unknown,
  taskId: string,
  taskName = "agora.run_pipeline",
): string {
  const args: unknown[] = [payload];
  // Тело протокола 2: [args, kwargs, embed]. Третий элемент обязателен даже
  // пустым — воркер разбирает кортеж по позиции и на двух элементах падает.
  const body = JSON.stringify([args, {}, {
    callbacks: null,
    errbacks: null,
    chain: null,
    chord: null,
  }]);

  return JSON.stringify({
    body: Buffer.from(body, "utf-8").toString("base64"),
    "content-encoding": "utf-8",
    "content-type": "application/json",
    headers: headers(taskId, args, taskName),
    properties: {
      correlation_id: taskId,
      reply_to: "",
      delivery_mode: 2,
      delivery_info: { exchange: "", routing_key: QUEUE },
      priority: 0,
      // Транспорт kombu поверх Redis/Valkey кодирует тело base64 — отсюда и
      // Buffer выше. Расхождение этих двух мест даёт сообщение, которое воркер
      // примет и не сможет разобрать.
      body_encoding: "base64",
      delivery_tag: randomUUID(),
    },
  });
}

/**
 * Кладёт прогон в очередь. Возвращает id celery-задачи.
 *
 * Ошибка НЕ гасится: запуск, не доехавший до воркера, обязан быть виден на
 * запуске, а не через десять минут пустого экрана прогресса.
 */
export async function enqueuePipeline(payload: PipelinePayload): Promise<string> {
  const client = await valkey();
  // task_id прогона и id celery-задачи совпадают намеренно: по нему воркер
  // находит свой чекпоинт (thread_id в LangGraph), поэтому ретрай Celery
  // продолжает прогон, а не начинает чистый.
  const taskId = payload.task_id;
  await client.lPush(QUEUE, buildMessage(payload, taskId));
  return taskId;
}

/** Параметры фоновой генерации аудитории. */
export interface AudiencePayload {
  persona_set_id: string;
  tenant_id: string;
  config: Record<string, unknown>;
}

/**
 * Ставит генерацию аудитории в ту же очередь, что и прогоны.
 *
 * ─── Почему в воркер, а не подпроцессом из веба ────────────────────────────
 * Маршрут запускал `python3 -m agent_core.persona.generate_cli` и ждал с
 * таймаутом 120 секунд, а обогащение — последовательный цикл с таймаутом 60
 * секунд на персону. Шестьдесят персон в такой бюджет не помещаются никак:
 * пользователь видел спиннер, превращавшийся в ошибку, и всё написанное к
 * этому моменту выбрасывалось.
 *
 * Вторая, менее заметная причина: в образе веба нет `openai`. Обогащение
 * оттуда всегда падало на ModuleNotFoundError и честно сообщало
 * `enriched: false` — то есть самая дорогая часть генерации не работала вовсе,
 * а выглядело это как привычная «деградация».
 *
 * Идентификатор задачи совпадает с идентификатором набора: по нему воркер
 * находит строку, которую наполняет, и повтор Celery не создаёт второй набор.
 */
export async function enqueueAudience(payload: AudiencePayload): Promise<string> {
  const client = await valkey();
  const taskId = payload.persona_set_id;
  await client.lPush(QUEUE, buildMessage(payload, taskId, "agora.generate_audience"));
  return taskId;
}
