import { NextRequest, NextResponse } from "next/server";
import { requireSession, toResponse } from "@/lib/server/guard";
import { withTenant } from "@/lib/server/db";
import { validateSurvey } from "@/lib/server/survey-validator";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/surveys
 *
 * Возвращает список анкет текущего арендатора.
 * tenant_id — из сессии, не из параметров.
 */
export async function GET() {
  try {
    const session = await requireSession();

    const surveys = await withTenant(session.tenantId, async (client) => {
      const { rows } = await client.query<{
        id: string;
        name: string;
        questions: unknown;
        created_at: string;
      }>(
        `SELECT id, name, questions, created_at
         FROM surveys
         ORDER BY created_at DESC`,
      );
      return rows;
    });

    return NextResponse.json({ surveys });
  } catch (error) {
    return toResponse(error);
  }
}

/**
 * PUT /api/surveys
 *
 * Создаёт или обновляет анкету. Валидирует questions по JSON Schema
 * перед записью в базу.
 *
 * Запрос: { id?, name, questions }
 * Если id передан — обновляет существующую, иначе создаёт новую.
 */
export async function PUT(req: NextRequest) {
  try {
    const session = await requireSession();

    const body = await req.json();
    const { id, name, questions } = body as {
      id?: string;
      name?: string;
      questions?: unknown;
    };

    // Валидация по схеме
    const result = validateSurvey({ name, questions });
    if (!result.valid) {
      return NextResponse.json(
        { error: "Анкета не прошла валидацию", details: result.errors },
        { status: 400 },
      );
    }

    const surveyId = await withTenant(session.tenantId, async (client) => {
      if (id) {
        // Обновление существующей анкеты (проверка владения через RLS)
        const { rows } = await client.query<{ id: string }>(
          `UPDATE surveys
           SET name = $1, questions = $2
           WHERE id = $3
           RETURNING id`,
          [name, JSON.stringify(questions), id],
        );
        if (rows.length === 0) {
          throw new Error("Анкета не найдена или принадлежит другому арендатору");
        }
        return rows[0].id;
      }

      // Создание новой
      const { rows } = await client.query<{ id: string }>(
        `INSERT INTO surveys (tenant_id, name, questions)
         VALUES ($1, $2, $3)
         RETURNING id`,
        [session.tenantId, name, JSON.stringify(questions)],
      );
      return rows[0].id;
    });

    return NextResponse.json({ id: surveyId, ok: true });
  } catch (error) {
    return toResponse(error);
  }
}