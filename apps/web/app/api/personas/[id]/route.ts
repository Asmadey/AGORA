import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { getPersona } from "@/lib/server/personas";

/**
 * Одна персона (задача #6).
 *
 * Чужая персона даёт 404, а не 403: политика RLS просто не вернёт строку, и
 * маршрут не может отличить «нет такой» от «есть у другого арендатора». Это не
 * недостаток, а требуемое поведение — разница в ответах сама сообщала бы, что
 * объект существует.
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

    const persona = await withTenant(tenantId, async (client) => {
      return getPersona(client, id);
    });

    if (!persona) {
      return Response.json({ error: "персона не найдена" }, { status: 404 });
    }
    return Response.json({ persona });
  } catch (error) {
    return toResponse(error);
  }
}
