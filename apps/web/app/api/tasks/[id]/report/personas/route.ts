import { requireSession, toResponse } from "@/lib/server/guard";
import { PERSONA_PAGE_MAX, loadReportPersonas } from "@/lib/server/reports";

/**
 * Карточки персон для аккордеона отчёта (задача #21).
 *
 * GET /api/tasks/{id}/report/personas?limit=&skip=
 *
 * Отдельный маршрут, потому что данные другого порядка величины: отчёт на 500
 * персонах с перекрытием 3 — 178 КБ, карточки к нему — 2.1 МБ. Класть их в
 * первый экран значило бы платить двумя мегабайтами за пять чисел в шапке.
 *
 * `total` возвращается всегда, а не только на первой странице: приёмка задачи
 * требует len(per_persona) == audience_size, и проверять это по длине одной
 * страницы нельзя.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function positiveInt(raw: string | null, fallback: number): number {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { tenantId, userId } = await requireSession();
    const { id } = await params;

    const url = new URL(request.url);
    const limit = Math.min(positiveInt(url.searchParams.get("limit"), 50), PERSONA_PAGE_MAX);
    // skip допускает 0, поэтому positiveInt здесь не годится.
    const rawSkip = Number(url.searchParams.get("skip"));
    const skip = Number.isFinite(rawSkip) && rawSkip > 0 ? Math.floor(rawSkip) : 0;

    const { items, total } = await loadReportPersonas({ tenantId, userId }, id, {
      limit,
      skip,
    });

    return Response.json({ items, total, limit, skip });
  } catch (error) {
    return toResponse(error);
  }
}
