import { withTenant } from "@/lib/server/db";
import { requireOwner, requireSession, toResponse } from "@/lib/server/guard";
import { getPortraitWithHistory, updatePortrait, type Portrait } from "@/lib/server/portraits";

/**
 * API портретов аудитории (задача #24) — детали и правка.
 *
 * GET /api/portraits/[id] — портрет с историей версий. Любой участник.
 * PUT /api/portraits/[id] — обновить body_md (создаёт новую версию). Только owner.
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
      return getPortraitWithHistory(client, id);
    });

    if (!data.portrait) {
      return Response.json({ error: "портрет не найден" }, { status: 404 });
    }

    return Response.json(data);
  } catch (error) {
    return toResponse(error);
  }
}

interface PutBody {
  body_md: string;
  name?: string;
}

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { userId, tenantId } = await requireOwner();
    const { id } = await params;

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "тело запроса не является корректным JSON" }, { status: 400 });
    }

    const raw = body as PutBody;
    if (!raw || typeof raw.body_md !== "string" || raw.body_md.trim().length === 0) {
      return Response.json(
        { error: "требуется поле body_md (непустая строка)" },
        { status: 400 },
      );
    }

    const portrait = await withTenant(tenantId, async (client) => {
      return updatePortrait(client, id, raw.body_md, raw.name, userId);
    });

    if (!portrait) {
      return Response.json({ error: "портрет не найден" }, { status: 404 });
    }

    return Response.json({ portrait });
  } catch (error) {
    return toResponse(error);
  }
}