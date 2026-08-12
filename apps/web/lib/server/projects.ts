import "server-only";

import type { PoolClient } from "pg";

/**
 * Доступ к проектам арендатора.
 *
 * Модуль появился поздно, и это само по себе находка: таблица `projects` была
 * заведена миграцией 02 с первого дня, но интерфейс к ней не обращался ни разу.
 * Экраны проектов держали данные в localforage — то есть в IndexedDB одной
 * вкладки. Выглядело это работающим приложением: карточки рисовались, счётчики
 * считались, удаление удаляло. Обнаруживалось позже — когда второй человек
 * открывал тот же адрес и видел пустой список.
 *
 * ─── Что такое проект в этой схеме ─────────────────────────────────────────
 * `projects` — это `id`, `name`, `created_by`, `created_at`, и больше ничего.
 * Ни эпизодов, ни выбранной аудитории, ни анкеты, ни статуса: всё это —
 * свойства прогона, а не проекта, и живёт в `tasks`. Прототип держал их в
 * проекте, потому что прогонов у него не было вовсе.
 *
 * Отсюда форма карточки проекта: имя и список прогонов. Статус проекта не
 * хранится, а выводится из прогонов — хранимый статус разошёлся бы с ними при
 * первом же отказе воркера, и разошёлся бы молча.
 *
 * ─── Про изоляцию ──────────────────────────────────────────────────────────
 * Ни одна функция не принимает `tenant_id` аргументом: он приходит из сессии
 * через `withTenant`, который ставит его в контекст RLS. Аргумент означал бы,
 * что изоляция держится на дисциплине вызывающего.
 */

export interface Project {
  id: string;
  name: string;
  createdAt: string;
  /** Прогоны этого проекта, новые сверху. */
  runs: ProjectRun[];
}

export interface ProjectRun {
  id: string;
  status: "QUEUED" | "RUNNING" | "REPORT_READY" | "FAILED";
  mode: "short" | "long";
  replicationCount: number;
  createdAt: string;
  finishedAt: string | null;
  error: string | null;
}

interface ProjectRow {
  id: string;
  name: string;
  created_at: Date;
}

interface RunRow {
  id: string;
  project_id: string;
  status: ProjectRun["status"];
  mode: ProjectRun["mode"];
  replication_count: number;
  created_at: Date;
  finished_at: Date | null;
  error: string | null;
}

function toRun(row: RunRow): ProjectRun {
  return {
    id: row.id,
    status: row.status,
    mode: row.mode,
    replicationCount: row.replication_count,
    createdAt: row.created_at.toISOString(),
    finishedAt: row.finished_at?.toISOString() ?? null,
    error: row.error,
  };
}

/**
 * Проекты арендатора вместе с их прогонами.
 *
 * Прогоны берутся вторым запросом, а не `LEFT JOIN`: соединение вернуло бы имя
 * проекта столько раз, сколько у него прогонов, и склеивать это обратно пришлось
 * бы в коде. Два запроса на экран — не та цена, ради которой стоит городить
 * группировку.
 */
export async function listProjects(client: PoolClient): Promise<Project[]> {
  const { rows } = await client.query<ProjectRow>(
    `SELECT id, name, created_at FROM projects ORDER BY created_at DESC`,
  );
  if (rows.length === 0) return [];

  const { rows: runs } = await client.query<RunRow>(
    `SELECT id, project_id, status, mode, replication_count,
            created_at, finished_at, error
       FROM tasks
      WHERE project_id = ANY($1::uuid[])
      ORDER BY created_at DESC`,
    [rows.map((r) => r.id)],
  );

  const byProject = new Map<string, ProjectRun[]>();
  for (const row of runs) {
    const list = byProject.get(row.project_id) ?? [];
    list.push(toRun(row));
    byProject.set(row.project_id, list);
  }

  return rows.map((r) => ({
    id: r.id,
    name: r.name,
    createdAt: r.created_at.toISOString(),
    runs: byProject.get(r.id) ?? [],
  }));
}

/**
 * Один проект или `null`.
 *
 * `null`, а не исключение: чужой проект под RLS просто не находится, и экран
 * обязан ответить на это 404. Отдельная ошибка «доступ запрещён» подтвердила бы,
 * что проект с таким идентификатором существует.
 */
export async function getProject(
  client: PoolClient,
  id: string,
): Promise<Project | null> {
  const { rows } = await client.query<ProjectRow>(
    `SELECT id, name, created_at FROM projects WHERE id = $1`,
    [id],
  );
  const project = rows[0];
  if (!project) return null;

  const { rows: runs } = await client.query<RunRow>(
    `SELECT id, project_id, status, mode, replication_count,
            created_at, finished_at, error
       FROM tasks
      WHERE project_id = $1
      ORDER BY created_at DESC`,
    [id],
  );

  return {
    id: project.id,
    name: project.name,
    createdAt: project.created_at.toISOString(),
    runs: runs.map(toRun),
  };
}

/**
 * Создаёт проект.
 *
 * `tenant_id` подставляется из контекста RLS (`app.tenant_id`), а не передаётся
 * вызывающим: политика `WITH CHECK` всё равно отвергла бы чужой, но брать его
 * из одного места дешевле, чем ловить отказ вставки.
 */
export async function createProject(
  client: PoolClient,
  { name, createdBy }: { name: string; createdBy: string | null },
): Promise<Project> {
  const { rows } = await client.query<ProjectRow>(
    `INSERT INTO projects (tenant_id, name, created_by)
     VALUES (current_setting('app.tenant_id')::uuid, $1, $2)
     RETURNING id, name, created_at`,
    [name, createdBy],
  );
  const row = rows[0];
  return {
    id: row.id,
    name: row.name,
    createdAt: row.created_at.toISOString(),
    runs: [],
  };
}

/** Переименование. `false` — проекта нет либо он чужой; на экране это 404. */
export async function renameProject(
  client: PoolClient,
  id: string,
  name: string,
): Promise<boolean> {
  const { rowCount } = await client.query(
    `UPDATE projects SET name = $2 WHERE id = $1`,
    [id, name],
  );
  return (rowCount ?? 0) > 0;
}

/**
 * Удаление. Прогоны уходят каскадом (`tasks.project_id ... ON DELETE CASCADE`).
 *
 * Каскад здесь не побочный эффект, а смысл: прогон без проекта — строка, на
 * которую нельзя сослаться ни с одного экрана, и живёт она вечно.
 */
export async function deleteProject(
  client: PoolClient,
  id: string,
): Promise<boolean> {
  const { rowCount } = await client.query(`DELETE FROM projects WHERE id = $1`, [id]);
  return (rowCount ?? 0) > 0;
}
