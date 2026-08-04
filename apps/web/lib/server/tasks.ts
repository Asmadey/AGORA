import "server-only";

import { createHash } from "node:crypto";

import type { PoolClient } from "pg";

import { listActivePromptsByStage } from "@/lib/server/prompts";

/**
 * Запуск исследования (задача #11).
 *
 * ─── Снимок промптов ───────────────────────────────────────────────────────
 * Decision Log #10. Промпты правятся в Промпт-студии между прогонами, и без
 * пиннинга версий отчёт невоспроизводим: перезапуск того же исследования пошёл
 * бы по другим инструкциям, а объяснить расхождение было бы нечем.
 *
 * Снимок берётся из АКТИВНЫХ версий в базе, а не из файлов `prompts/`: файлы —
 * это seed, а активной может быть версия арендатора, отредактированная в
 * студии. Читать файлы значило бы пиннить то, что не исполняется.
 *
 * ─── Идемпотентность ───────────────────────────────────────────────────────
 * Не «похожий результат», а «не создаёт вторую задачу». Запуск платный: разбор
 * кадров и прогон респондентов стоят денег при каждом вызове, а двойной клик,
 * ретрай прокси или обновление страницы неотличимы от намеренного повтора.
 *
 * Ключ — отпечаток параметров, включая seed и снимок промптов. Снимок в ключе
 * обязателен: если промпт отредактировали между двумя нажатиями, это уже другой
 * прогон, и склеивать его с прежним нельзя — результат будет другим.
 */

export interface LaunchParams {
  mode: "short" | "long";
  videoRef: string | null;
  personaSetId: string | null;
  surveyId: string | null;
  projectId: string | null;
  replicationCount: number;
  seed: number;
}

export interface LaunchedTask {
  id: string;
  mode: string;
  videoRef: string | null;
  replicationCount: number;
  promptsSnapshot: Record<string, PinnedPrompt>;
  status: string;
  createdAt: string;
  /** false — задача уже существовала, повторный запуск ничего не создал. */
  created: boolean;
}

export interface PinnedPrompt {
  id: string;
  version: number;
  /** Отпечаток шаблона: по нему видно, что версия не подменена на месте. */
  templateSha256: string;
}

interface TaskRow {
  id: string;
  mode: string;
  video_ref: string | null;
  replication_count: number;
  prompts_snapshot: Record<string, PinnedPrompt>;
  status: string;
  created_at: Date;
}

/**
 * Снимок активных версий всех ключей реестра.
 *
 * Пустой снимок — это отказ, а не «промптов нет». Пустой снимок означает
 * «пиннинг есть в схеме, но не работает», и от рабочего он неотличим до первой
 * правки промпта — то есть до момента, когда воспроизводимость уже потеряна.
 */
export async function buildPromptsSnapshot(
  client: PoolClient,
): Promise<Record<string, PinnedPrompt>> {
  const byStage = await listActivePromptsByStage(client);
  const snapshot: Record<string, PinnedPrompt> = {};

  for (const versions of Object.values(byStage)) {
    for (const v of versions) {
      snapshot[v.key] = {
        id: v.id,
        version: v.version,
        templateSha256: createHash("sha256").update(v.template).digest("hex"),
      };
    }
  }

  if (Object.keys(snapshot).length === 0) {
    throw new Error(
      "реестр промптов пуст: снимок собрать не из чего. Примените миграцию " +
        "07_prompts_seed.sql — без снимка прогон невоспроизводим (Decision Log #10)",
    );
  }
  return snapshot;
}

/**
 * Отпечаток запуска. Одинаковые параметры → одинаковый ключ → та же задача.
 *
 * tenant_id в ключ НЕ входит: он отдельной колонкой в уникальном индексе.
 * Смешивать их в одну строку значило бы полагаться на то, что хеш не совпадёт
 * у разных арендаторов, вместо того чтобы разделить их структурно.
 */
export function idempotencyKey(
  params: LaunchParams,
  snapshot: Record<string, PinnedPrompt>,
): string {
  const canonical = JSON.stringify({
    mode: params.mode,
    videoRef: params.videoRef,
    personaSetId: params.personaSetId,
    surveyId: params.surveyId,
    projectId: params.projectId,
    replicationCount: params.replicationCount,
    seed: params.seed,
    // Сортировка обязательна: порядок ключей объекта в JS зависит от порядка
    // вставки, а он приходит из порядка строк базы и не гарантирован.
    prompts: Object.keys(snapshot)
      .sort()
      .map((k) => [k, snapshot[k].id, snapshot[k].version, snapshot[k].templateSha256]),
  });
  return createHash("sha256").update(canonical).digest("hex");
}

function toTask(row: TaskRow, created: boolean): LaunchedTask {
  return {
    id: row.id,
    mode: row.mode,
    videoRef: row.video_ref,
    replicationCount: row.replication_count,
    promptsSnapshot: row.prompts_snapshot,
    status: row.status,
    createdAt: row.created_at.toISOString(),
    created,
  };
}

/**
 * Создаёт задачу либо возвращает уже существующую с тем же ключом.
 *
 * ON CONFLICT DO NOTHING + повторный SELECT, а не «сначала посмотреть, потом
 * вставить»: проверка перед вставкой гонку не закрывает — два одновременных
 * запроса оба ничего не находят и оба вставляют. Здесь конфликт разрешает
 * уникальный индекс, то есть база, а не порядок исполнения.
 */
export async function launchTask(
  client: PoolClient,
  params: LaunchParams,
  createdBy: string | null,
): Promise<LaunchedTask> {
  const snapshot = await buildPromptsSnapshot(client);
  const key = idempotencyKey(params, snapshot);

  const inserted = await client.query<TaskRow>(
    `INSERT INTO tasks (project_id, persona_set_id, survey_id, mode, video_ref,
                        replication_count, prompts_snapshot, idempotency_key,
                        created_by, tenant_id)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
             current_setting('app.tenant_id')::uuid)
     ON CONFLICT (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL
     DO NOTHING
     RETURNING id, mode, video_ref, replication_count, prompts_snapshot, status, created_at`,
    [
      params.projectId,
      params.personaSetId,
      params.surveyId,
      params.mode,
      params.videoRef,
      params.replicationCount,
      JSON.stringify(snapshot),
      key,
      createdBy,
    ],
  );

  if (inserted.rows.length > 0) return toTask(inserted.rows[0], true);

  // Конфликт: задача с таким ключом уже есть. Возвращаем её, а не ошибку —
  // для вызывающего повторный запуск обязан выглядеть как успешный.
  const existing = await client.query<TaskRow>(
    `SELECT id, mode, video_ref, replication_count, prompts_snapshot, status, created_at
     FROM tasks WHERE idempotency_key = $1`,
    [key],
  );
  if (existing.rows.length === 0) {
    // Сюда попадём, только если строку удалили между INSERT и SELECT, либо если
    // RLS её не показывает. Молчать нельзя: пустой ответ выглядел бы как
    // «запуск прошёл», а задачи нет.
    throw new Error(
      "задача с этим ключом идемпотентности не создана и не найдена — " +
        "проверьте тенант-контекст и политику RLS на tasks",
    );
  }
  return toTask(existing.rows[0], false);
}

export async function getTask(
  client: PoolClient,
  id: string,
): Promise<LaunchedTask | null> {
  const { rows } = await client.query<TaskRow>(
    `SELECT id, mode, video_ref, replication_count, prompts_snapshot, status, created_at
     FROM tasks WHERE id = $1`,
    [id],
  );
  return rows[0] ? toTask(rows[0], false) : null;
}

export async function listTasks(client: PoolClient): Promise<LaunchedTask[]> {
  const { rows } = await client.query<TaskRow>(
    `SELECT id, mode, video_ref, replication_count, prompts_snapshot, status, created_at
     FROM tasks ORDER BY created_at DESC LIMIT 100`,
  );
  return rows.map((r) => toTask(r, false));
}
