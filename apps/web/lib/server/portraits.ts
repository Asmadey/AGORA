import "server-only";

import type { PoolClient } from "pg";

/**
 * Портреты аудитории (задача #24) — серверный слой.
 *
 * Список, детали с историей версий, обновление. Логика версионирования
 * повторяет промпт-студию (#26): каждое сохранение пишет новую версию
 * в audience_portrait_versions и обновляет body_md в audience_portraits.
 */

export interface Portrait {
  id: string;
  tenant_id: string;
  name: string;
  body_md: string;
  source: "manual" | "distilled" | "context_file";
  created_at: string;
  updated_at: string;
}

export interface PortraitVersion {
  id: string;
  version: number;
  body_md: string;
  editor: string;
  created_by: string | null;
  created_at: string;
}

interface PortraitRow {
  id: string;
  tenant_id: string;
  name: string;
  body_md: string;
  source: string;
  created_at: Date;
  updated_at: Date;
}

interface VersionRow {
  id: string;
  version: number;
  body_md: string;
  editor: string;
  created_by: string | null;
  created_at: Date;
}

function rowToPortrait(row: PortraitRow): Portrait {
  return {
    id: row.id,
    tenant_id: row.tenant_id,
    name: row.name,
    body_md: row.body_md,
    source: row.source as Portrait["source"],
    created_at: row.created_at.toISOString(),
    updated_at: row.updated_at.toISOString(),
  };
}

function rowToVersion(row: VersionRow): PortraitVersion {
  return {
    id: row.id,
    version: row.version,
    body_md: row.body_md,
    editor: row.editor,
    created_by: row.created_by,
    created_at: row.created_at.toISOString(),
  };
}

/** Список всех портретов арендатора. */
export async function listPortraits(client: PoolClient): Promise<Portrait[]> {
  const { rows } = await client.query<PortraitRow>(
    `SELECT id, tenant_id, name, body_md, source, created_at, updated_at
     FROM audience_portraits
     ORDER BY updated_at DESC`,
  );
  return rows.map(rowToPortrait);
}

/** Один портрет с историей версий. */
export async function getPortraitWithHistory(
  client: PoolClient,
  portraitId: string,
): Promise<{ portrait: Portrait | null; history: PortraitVersion[] }> {
  const { rows: pRows } = await client.query<PortraitRow>(
    `SELECT id, tenant_id, name, body_md, source, created_at, updated_at
     FROM audience_portraits
     WHERE id = $1`,
    [portraitId],
  );

  if (pRows.length === 0) {
    return { portrait: null, history: [] };
  }

  const { rows: vRows } = await client.query<VersionRow>(
    `SELECT id, version, body_md, editor, created_by, created_at
     FROM audience_portrait_versions
     WHERE portrait_id = $1
     ORDER BY version DESC`,
    [portraitId],
  );

  return {
    portrait: rowToPortrait(pRows[0]),
    history: vRows.map(rowToVersion),
  };
}

/** Обновить тело портрета и записать новую версию. */
export async function updatePortrait(
  client: PoolClient,
  portraitId: string,
  bodyMd: string,
  name: string | undefined,
  userId?: string,
): Promise<Portrait | null> {
  // Обновляем основную запись
  const { rows: pRows } = await client.query<PortraitRow>(
    `UPDATE audience_portraits
     SET body_md = $2,
         name = COALESCE($3, name),
         updated_at = now()
     WHERE id = $1
     RETURNING id, tenant_id, name, body_md, source, created_at, updated_at`,
    [portraitId, bodyMd, name ?? null],
  );

  if (pRows.length === 0) {
    return null;
  }

  // Считаем следующую версию
  const { rows: vRows } = await client.query<{ max_ver: number | null }>(
    `SELECT COALESCE(max(version), 0) AS max_ver
     FROM audience_portrait_versions
     WHERE portrait_id = $1`,
    [portraitId],
  );
  const nextVersion = (vRows[0]?.max_ver ?? 0) + 1;

  // Записываем версию
  await client.query(
    `INSERT INTO audience_portrait_versions (tenant_id, portrait_id, version, body_md, editor, created_by)
     VALUES ($1, $2, $3, $4, 'manual', $5)`,
    [pRows[0].tenant_id, portraitId, nextVersion, bodyMd, userId ?? null],
  );

  return rowToPortrait(pRows[0]);
}

/** Создать новый портрет (manual или distilled). */
export async function createPortrait(
  client: PoolClient,
  name: string,
  bodyMd: string,
  source: "manual" | "distilled" | "context_file" = "manual",
  userId?: string,
  /**
   * Ключ сегмента в формате дистилляции: `age_group|geo|gender`.
   *
   * По нему воркер сопоставляет персону с портретом при обогащении narrative.
   * У портрета, заведённого вручную, сегмента нет — сопоставлять его не по
   * чему, и в сборке он не участвует. Имя для этого не годится: человек правит
   * его руками, и матчинг сломался бы на первом переименовании молча.
   */
  segmentKey?: string | null,
): Promise<Portrait> {
  // RLS policies fill tenant_id automatically, but we need it for the
  // versions table insert — get it from the current tenant context.
  const { rows: tidRows } = await client.query<{ tid: string }>(
    "SELECT app.current_tenant() AS tid",
  );
  const tenantId = tidRows[0]?.tid;

  const { rows } = await client.query<PortraitRow>(
    `INSERT INTO audience_portraits (tenant_id, name, body_md, source, segment_key)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING id, tenant_id, name, body_md, source, created_at, updated_at`,
    [tenantId, name, bodyMd, source, segmentKey ?? null],
  );

  const portrait = rowToPortrait(rows[0]);

  // First version
  await client.query(
    `INSERT INTO audience_portrait_versions (tenant_id, portrait_id, version, body_md, editor, created_by)
     VALUES ($1, $2, 1, $3, $4, $5)`,
    [tenantId, portrait.id, bodyMd, source === "distilled" ? "distilled" : "manual", userId ?? null],
  );

  return portrait;
}

/**
 * Портрет сегмента: обновить существующий, завести только если его нет.
 *
 * ─── Что чинится ──────────────────────────────────────────────────────────
 * Дистилляция звала `createPortrait` для каждого сегмента, и каждый запуск
 * добавлял полный комплект. К 11.09.2026 на боевой базе лежало 38 портретов
 * на 19 сегментов — по паре близнецов на каждый, плюс 163 записи вообще без
 * ключа сегмента, удалённые отдельно.
 *
 * Цена не в месте. Воркер ищет портрет ПО СЕГМЕНТУ, и при двух записях с
 * одним ключом выбор доставался тому, кто раньше попался. То есть две персоны
 * одного сегмента могли быть описаны по разным портретам, а разницу не видно
 * ни в интерфейсе, ни в отчёте.
 *
 * ─── Почему по сегменту, а не по имени ────────────────────────────────────
 * Имя человек правит руками. Матчинг по имени разошёлся бы на первом
 * переименовании — молча, потому что портрет просто перестал бы находиться.
 * Сегмент — это ключ, а не подпись: он один на сегмент по определению.
 *
 * ─── Что происходит с историей ────────────────────────────────────────────
 * Обновление пишет новую версию в `audience_portrait_versions` с редактором
 * `distilled`. Прежний текст остаётся в истории — повторная дистилляция не
 * стирает то, что было, а продолжает ряд.
 */
export async function upsertDistilledPortrait(
  client: PoolClient,
  name: string,
  bodyMd: string,
  segmentKey: string,
  userId?: string,
): Promise<Portrait> {
  const key = segmentKey?.trim();
  if (!key) {
    // Без ключа обновлять нечего и сопоставлять нечем: такой портрет воркер
    // не найдёт никогда. Отказ громче, чем запись, которую никто не прочтёт.
    throw new Error("дистиллированный портрет без segment_key не сохраняется");
  }

  // Существующий ищется по сегменту в пределах арендатора — RLS сужает
  // выборку сама, отдельного условия по tenant_id не нужно.
  const { rows: found } = await client.query<{ id: string }>(
    `SELECT id FROM audience_portraits
      WHERE segment_key = $1
      ORDER BY updated_at DESC, id DESC
      LIMIT 1`,
    [key],
  );

  if (found.length === 0) {
    return createPortrait(client, name, bodyMd, "distilled", userId, key);
  }

  const portraitId = found[0].id;
  const { rows: updated } = await client.query<PortraitRow>(
    `UPDATE audience_portraits
        SET body_md = $2, name = $3, source = 'distilled', updated_at = now()
      WHERE id = $1
      RETURNING id, tenant_id, name, body_md, source, created_at, updated_at`,
    [portraitId, bodyMd, name],
  );

  const { rows: vRows } = await client.query<{ max_ver: number | null }>(
    `SELECT COALESCE(max(version), 0) AS max_ver
       FROM audience_portrait_versions
      WHERE portrait_id = $1`,
    [portraitId],
  );

  await client.query(
    `INSERT INTO audience_portrait_versions (tenant_id, portrait_id, version, body_md, editor, created_by)
     VALUES ($1, $2, $3, $4, 'distilled', $5)`,
    [updated[0].tenant_id, portraitId, (vRows[0]?.max_ver ?? 0) + 1, bodyMd, userId ?? null],
  );

  return rowToPortrait(updated[0]);
}

/**
 * Удаление портрета.
 *
 * Версии уходят каскадом (`audience_portrait_versions.portrait_id`). Персоны,
 * сгенерированные с этим портретом, не трогаются: они уже созданы, их DNA
 * самодостаточна, и удалять аудиторию из-за уборки в портретах значило бы
 * терять данные прогонов, которые на ней посчитаны.
 */
export async function deletePortrait(
  client: PoolClient,
  portraitId: string,
): Promise<boolean> {
  const { rowCount } = await client.query(
    `DELETE FROM audience_portraits WHERE id = $1`,
    [portraitId],
  );
  return (rowCount ?? 0) > 0;
}
