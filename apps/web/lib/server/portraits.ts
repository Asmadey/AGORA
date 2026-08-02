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
): Promise<Portrait> {
  // RLS policies fill tenant_id automatically, but we need it for the
  // versions table insert — get it from the current tenant context.
  const { rows: tidRows } = await client.query<{ tid: string }>(
    "SELECT app.current_tenant() AS tid",
  );
  const tenantId = tidRows[0]?.tid;

  const { rows } = await client.query<PortraitRow>(
    `INSERT INTO audience_portraits (tenant_id, name, body_md, source)
     VALUES ($1, $2, $3, $4)
     RETURNING id, tenant_id, name, body_md, source, created_at, updated_at`,
    [tenantId, name, bodyMd, source],
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