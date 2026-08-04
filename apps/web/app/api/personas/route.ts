import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { listPersonas } from "@/lib/server/personas";

/**
 * Список персон арендатора (задача #6).
 *
 * GET /api/personas            — все персоны арендатора
 * GET /api/personas?setId=<uuid> — персоны конкретного набора
 *
 * Фильтр по набору — параметром, а не отдельным маршрутом: это одна и та же
 * выборка с дополнительным условием, и разводить её по двум эндпоинтам значит
 * дублировать проекцию строк, которая обязана совпадать.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request) {
  try {
    const { tenantId } = await requireSession();
    const setId = new URL(request.url).searchParams.get("setId") ?? undefined;

    const personas = await withTenant(tenantId, async (client) => {
      return listPersonas(client, setId);
    });
    return Response.json({ personas });
  } catch (error) {
    return toResponse(error);
  }
}
