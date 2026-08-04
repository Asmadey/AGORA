import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { listPersonaSets, listPersonas } from "@/lib/server/personas";

/**
 * Один набор персон вместе с его составом (задача #6).
 *
 * Чужой или несуществующий набор даёт 404 одинаково. Это пункт cdd
 * «кросс-арендаторный доступ к persona_set → 404»: RLS не возвращает чужую
 * строку, и маршрут физически не может отличить один случай от другого.
 * Различие в ответах было бы утечкой само по себе — по коду ответа стало бы
 * видно, существует ли объект у соседа.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { tenantId } = await requireSession();
    const { id } = await params;

    const data = await withTenant(tenantId, async (client) => {
      const sets = await listPersonaSets(client, id);
      if (sets.length === 0) return null;
      return { personaSet: sets[0], personas: await listPersonas(client, id) };
    });

    if (!data) {
      return Response.json({ error: "набор не найден" }, { status: 404 });
    }
    return Response.json(data);
  } catch (error) {
    return toResponse(error);
  }
}
