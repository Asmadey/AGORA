import "server-only";

import type { PoolClient } from "pg";

import type { SurveyQuestion } from "@/lib/agora-types";

/**
 * Чтение анкет арендатора.
 *
 * Запись осталась в `PUT /api/surveys`: там же валидация по JSON Schema, и
 * разносить проверку и вставку по разным модулям значило бы завести путь, на
 * котором можно записать невалидную анкету. Читать при этом нужно и странице
 * списка, и редактору, и самому маршруту — поэтому SELECT живёт здесь один.
 *
 * До этой правки экраны анкет читали localforage и знали собственный набор
 * типов вопросов: `rating`, `values`, `nps`, `matrix`, `slogan`. Валидатор не
 * принимает ни одного из них. Две модели одного и того же разошлись ровно так,
 * как расходятся всегда, — молча и полностью.
 */

export interface Survey {
  id: string;
  name: string;
  questions: SurveyQuestion[];
  createdAt: string;
}

interface SurveyRow {
  id: string;
  name: string;
  questions: SurveyQuestion[] | null;
  created_at: Date;
}

function toSurvey(row: SurveyRow): Survey {
  return {
    id: row.id,
    name: row.name,
    // jsonb приезжает разобранным; пустой массив вместо null — потому что
    // «анкета без вопросов» и «поле не заполнено» на экране одно и то же.
    questions: Array.isArray(row.questions) ? row.questions : [],
    createdAt: row.created_at.toISOString(),
  };
}

export async function listSurveys(client: PoolClient): Promise<Survey[]> {
  const { rows } = await client.query<SurveyRow>(
    `SELECT id, name, questions, created_at FROM surveys ORDER BY created_at DESC`,
  );
  return rows.map(toSurvey);
}

/** `null` — анкеты нет либо она чужая: под RLS это неразличимо, и на экране 404. */
export async function getSurvey(client: PoolClient, id: string): Promise<Survey | null> {
  const { rows } = await client.query<SurveyRow>(
    `SELECT id, name, questions, created_at FROM surveys WHERE id = $1`,
    [id],
  );
  return rows[0] ? toSurvey(rows[0]) : null;
}

export async function deleteSurvey(client: PoolClient, id: string): Promise<boolean> {
  const { rowCount } = await client.query(`DELETE FROM surveys WHERE id = $1`, [id]);
  return (rowCount ?? 0) > 0;
}
