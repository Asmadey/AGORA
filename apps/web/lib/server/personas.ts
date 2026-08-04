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
}

export interface Persona {
  id: string;
  personaSetId: string | null;
  name: string;
  dna: PersonaDNA;
  narrative: string | null;
  seed: number | null;
  createdAt: string;
}

interface PersonaSetRow {
  id: string;
  name: string;
  size: number;
  generation_config: Record<string, unknown> | null;
  seed: string | number | null;
  created_at: Date;
  persona_count: string;
}

interface PersonaRow {
  id: string;
  persona_set_id: string | null;
  name: string;
  dna: PersonaDNA;
  narrative: string | null;
  seed: string | number | null;
  created_at: Date;
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
    `SELECT ps.id, ps.name, ps.size, ps.generation_config, ps.seed, ps.created_at,
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
): Promise<PersonaSet> {
  const { rows } = await client.query<PersonaSetRow>(
    `INSERT INTO persona_sets (tenant_id, name, size, generation_config, seed)
     VALUES (app.current_tenant(), $1, $2, $3::jsonb, $4)
     RETURNING id, name, size, generation_config, seed, created_at, 0::bigint AS persona_count`,
    [name, size, JSON.stringify(generationConfig), seed],
  );
  return toSet(rows[0]);
}

// ─── Персоны ───────────────────────────────────────────────────────────────

export async function listPersonas(
  client: PoolClient,
  personaSetId?: string,
): Promise<Persona[]> {
  const { rows } = await client.query<PersonaRow>(
    `SELECT id, persona_set_id, name, dna, narrative, seed, created_at
       FROM personas
      WHERE ($1::uuid IS NULL OR persona_set_id = $1::uuid)
      ORDER BY created_at DESC`,
    [personaSetId ?? null],
  );
  return rows.map(toPersona);
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
