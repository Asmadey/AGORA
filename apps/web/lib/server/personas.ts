import "server-only";

import type { PoolClient } from "pg";

import type { PersonaDNA } from "@agora/shared/types/persona-dna";

/**
 * Доступ к персонам и наборам персон (задача #6).
 *
 * ─── Про типы ──────────────────────────────────────────────────────────────
 * DNA описывается сгенерированным из canonical JSON Schema типом, а не
 * рукописным. В проекте до этой задачи сосуществовали две модели:
 * packages/shared/types/persona-dna.ts (из схемы, snake_case) и
 * apps/web/lib/agora-types.ts (руками, camelCase, другой состав полей —
 * например communication_style в схеме содержит directness и conflict_style,
 * которых в рукописном нет, а его tone и vocabulary нет в схеме).
 *
 * Карточка была построена на второй, поэтому 35 полей из 47 в ней просто
 * отсутствовали. Пункт cdd «ни одно поле не потеряно при рендере» на такой
 * модели невыполним в принципе: у неё другие имена.
 *
 * ─── Про изоляцию ──────────────────────────────────────────────────────────
 * Ни одна функция здесь не принимает tenant_id аргументом. Он приходит из
 * сессии через withTenant, который ставит его в контекст RLS. Аргумент означал
 * бы, что изоляция держится на дисциплине вызывающего, а не на политике базы, —
 * а RLS при отсутствии контекста возвращает пустоту, то есть отказ виден сразу.
 */

export interface PersonaSet {
  id: string;
  name: string;
  size: number;
  generationConfig: Record<string, unknown>;
  seed: number | null;
  createdAt: string;
  /** Сколько персон реально сохранено в наборе. Ноль — набор создан, но не заполнен. */
  personaCount: number;
  /** `generating` — воркер ещё пишет персон в этот набор. */
  status: "generating" | "ready" | "failed";
  /**
   * Сколько персон обработано на текущий момент. Обновляется воркером по ходу
   * генерации — из этого числа и заказанного размера складывается «40 из 60».
   */
  generatedCount: number;
  /** Причина отказа генерации. Без неё «failed» не подсказывает следующий шаг. */
  error: string | null;
}

export interface Persona {
  id: string;
  personaSetId: string | null;
  name: string;
  dna: PersonaDNA;
  narrative: string | null;
  seed: number | null;
  createdAt: string;
  /** Имя или адрес автора набора. null — автор неизвестен либо удалён. */
  author: string | null;
}

interface PersonaSetRow {
  id: string;
  name: string;
  size: number;
  generation_config: Record<string, unknown> | null;
  seed: string | number | null;
  created_at: Date;
  persona_count: string;
  status: string;
  generated_count: number;
  error: string | null;
}

interface PersonaRow {
  id: string;
  persona_set_id: string | null;
  name: string;
  dna: PersonaDNA;
  narrative: string | null;
  seed: string | number | null;
  created_at: Date;
  author?: string | null;
}

/** bigint приезжает из pg строкой: JS не может представить его безопасно как number. */
function toNumber(v: string | number | null): number | null {
  if (v === null) return null;
  return typeof v === "number" ? v : Number(v);
}

function toSet(row: PersonaSetRow): PersonaSet {
  return {
    id: row.id,
    name: row.name,
    size: row.size,
    generationConfig: row.generation_config ?? {},
    seed: toNumber(row.seed),
    createdAt: row.created_at.toISOString(),
    personaCount: Number(row.persona_count ?? 0),
    status: (row.status as PersonaSet["status"]) ?? "ready",
    generatedCount: Number(row.generated_count ?? 0),
    error: row.error ?? null,
  };
}

function toPersona(row: PersonaRow): Persona {
  return {
    id: row.id,
    personaSetId: row.persona_set_id,
    name: row.name,
    dna: row.dna,
    narrative: row.narrative,
    seed: toNumber(row.seed),
    createdAt: row.created_at.toISOString(),
    author: row.author ?? null,
  };
}

// ─── Наборы ────────────────────────────────────────────────────────────────

export async function listPersonaSets(
  client: PoolClient,
  id?: string,
): Promise<PersonaSet[]> {
  // persona_count считается подзапросом, а не JOIN с GROUP BY: набор без персон
  // обязан попасть в список. При JOIN он бы пропал, и преселект «Выбрать
  // существующую» не показывал бы только что созданный набор.
  const { rows } = await client.query<PersonaSetRow>(
    `SELECT ps.id, ps.name, ps.size, ps.generation_config, ps.seed, ps.created_at, status, generated_count, error,
            (SELECT count(*) FROM personas p WHERE p.persona_set_id = ps.id) AS persona_count
       FROM persona_sets ps
      WHERE ($1::uuid IS NULL OR ps.id = $1::uuid)
      ORDER BY ps.created_at DESC`,
    [id ?? null],
  );
  return rows.map(toSet);
}

export async function createPersonaSet(
  client: PoolClient,
  name: string,
  size: number,
  generationConfig: Record<string, unknown>,
  seed: number | null,
  /**
   * `generating` — набор заведён, персон в нём ещё нет: их пишет воркер.
   * По умолчанию `ready`, потому что так набор создаётся вручную и из тестов.
   */
  status: "generating" | "ready" = "ready",
  /**
   * Слепок корпуса, по которому собирается набор.
   *
   * `null` — набор создан не из корпуса базы (ручной вызов, тесты, прогоны до
   * этапа Е). Читается как «версия корпуса неизвестна», а не как «первая»:
   * подставлять сюда что-то по умолчанию значило бы утверждать
   * воспроизводимость, которой нет.
   */
  corpusSnapshotId: string | null = null,
  /**
   * Кто заказал генерацию. Наследуется персонами набора при записи.
   *
   * `null` законен: ручной вызов и тесты сессии не имеют. Читается как «автор
   * неизвестен» — в команде из нескольких человек это единственный способ
   * понять, чья аудитория, прежде чем её удалять.
   */
  createdBy: string | null = null,
): Promise<PersonaSet> {
  const { rows } = await client.query<PersonaSetRow>(
    `INSERT INTO persona_sets (tenant_id, name, size, generation_config, seed, status,
                               corpus_snapshot_id, created_by)
     VALUES (app.current_tenant(), $1, $2, $3::jsonb, $4, $5, $6, $7)
     RETURNING id, name, size, generation_config, seed, created_at, status,
               generated_count, error, 0::bigint AS persona_count`,
    [name, size, JSON.stringify(generationConfig), seed, status, corpusSnapshotId, createdBy],
  );
  return toSet(rows[0]);
}

/**
 * Удаляет персон по списку идентификаторов. Возвращает, сколько удалено.
 *
 * Чужие идентификаторы просто не находятся: RLS не покажет строку другого
 * арендатора, и `DELETE` по ней удалит ноль. Отдельной проверки на владение не
 * нужно — и это лучше проверки, потому что её нельзя забыть.
 *
 * Персона, на ответах которой стоит отчёт, удаляется вместе со своей карточкой
 * в реестре, но не из отчёта: карточки ответов живут в Mongo и ссылаются на
 * идентификатор, а не на строку. Прежний отчёт остаётся читаемым — иначе
 * уборка в реестре задним числом меняла бы уже принятые решения.
 */
export async function deletePersonas(
  client: PoolClient,
  ids: string[],
): Promise<number> {
  if (ids.length === 0) return 0;
  const { rowCount } = await client.query(
    "DELETE FROM personas WHERE id = ANY($1::uuid[])",
    [ids],
  );
  return rowCount ?? 0;
}


/**
 * Удаление наборов. Набор, на котором стоит исследование, НЕ удаляется.
 *
 * ─── Почему отказ, а не удаление ───────────────────────────────────────────
 * Внешний ключ `tasks.persona_set_id` объявлен `ON DELETE SET NULL`: удаление
 * набора не ломает прогон, оно тихо обнуляет ссылку. Отчёт остаётся на месте, а
 * ответ на вопрос «на ком это проверяли» исчезает — и исчезает молча, без следа
 * в интерфейсе. Уборка в списке наборов задним числом лишала бы смысла уже
 * принятые по отчётам решения.
 *
 * Поэтому такие наборы возвращаются отдельным списком с числом прогонов: пусть
 * человек решает, а не узнаёт постфактум.
 */
export async function deletePersonaSets(
  client: PoolClient,
  ids: string[],
): Promise<{ deleted: number; blocked: { id: string; name: string; runs: number }[] }> {
  if (ids.length === 0) return { deleted: 0, blocked: [] };

  const { rows: used } = await client.query<{ id: string; name: string; runs: string }>(
    `SELECT ps.id, ps.name, COUNT(t.id)::text AS runs
       FROM persona_sets ps
       JOIN tasks t ON t.persona_set_id = ps.id
      WHERE ps.id = ANY($1::uuid[])
      GROUP BY ps.id, ps.name`,
    [ids],
  );
  const blocked = used.map((r) => ({ id: r.id, name: r.name, runs: Number(r.runs) }));
  const blockedIds = new Set(blocked.map((b) => b.id));
  const free = ids.filter((id) => !blockedIds.has(id));

  if (free.length === 0) return { deleted: 0, blocked };

  // Персоны уезжают каскадом (`personas_persona_set_id_fkey ON DELETE CASCADE`)
  // — отдельного запроса не нужно, и его отсутствие здесь намеренное.
  const { rowCount } = await client.query(
    "DELETE FROM persona_sets WHERE id = ANY($1::uuid[])",
    [free],
  );
  return { deleted: rowCount ?? 0, blocked };
}

// ─── Персоны ───────────────────────────────────────────────────────────────

export async function listPersonas(
  client: PoolClient,
  personaSetId?: string,
): Promise<Persona[]> {
  const { rows } = await client.query<PersonaRow>(
    `SELECT p.id, p.persona_set_id, p.name, p.dna, p.narrative, p.seed, p.created_at,
            (SELECT COALESCE(u.name, u.email) FROM users u WHERE u.id = p.created_by) AS author
       FROM personas p
      WHERE ($1::uuid IS NULL OR p.persona_set_id = $1::uuid)
      ORDER BY p.created_at DESC`,
    [personaSetId ?? null],
  );
  return rows.map(toPersona);
}

export async function insertPersonas(
  client: PoolClient,
  personaSetId: string,
  personas: { name: string; dna: Record<string, unknown>; narrative: string | null; seed: number | null }[],
): Promise<number> {
  if (personas.length === 0) return 0;

  // Один INSERT с unnest, а не N запросов в цикле. Набор по умолчанию — 20
  // персон, при перекрытии бывает больше; двадцать round-trip'ов к managed
  // Postgres из другого дата-центра стоят заметно дороже одного, и главное —
  // при обрыве на середине цикла набор остался бы наполовину заполненным, а
  // отличить такой от полного можно только пересчётом.
  const { rowCount } = await client.query(
    `INSERT INTO personas (tenant_id, persona_set_id, name, dna, narrative, seed)
     SELECT app.current_tenant(), $1::uuid, t.name, t.dna::jsonb, t.narrative, t.seed
       FROM unnest($2::text[], $3::text[], $4::text[], $5::bigint[])
              AS t(name, dna, narrative, seed)`,
    [
      personaSetId,
      personas.map((p) => p.name),
      personas.map((p) => JSON.stringify(p.dna)),
      personas.map((p) => p.narrative),
      personas.map((p) => p.seed),
    ],
  );
  return rowCount ?? 0;
}

export async function getPersona(
  client: PoolClient,
  id: string,
): Promise<Persona | null> {
  const { rows } = await client.query<PersonaRow>(
    `SELECT id, persona_set_id, name, dna, narrative, seed, created_at
       FROM personas
      WHERE id = $1`,
    [id],
  );
  return rows[0] ? toPersona(rows[0]) : null;
}
