import { withTenant } from "@/lib/server/db";
import { requireOwner, requireSession, toResponse } from "@/lib/server/guard";
import { createPortrait, listPortraits, type Portrait } from "@/lib/server/portraits";

/**
 * API портретов аудитории (задача #24) — список и создание.
 *
 * GET  /api/portraits — список портретов. Любой участник.
 * POST /api/portraits — создать новый портрет (manual). Только owner.
 *       Для дистилляции — POST /api/portraits/distill.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  try {
    const { tenantId } = await requireSession();
    const portraits = await withTenant(tenantId, async (client) => {
      return listPortraits(client);
    });
    return Response.json({ portraits });
  } catch (error) {
    return toResponse(error);
  }
}

interface CreateBody {
  name: string;
  body_md: string;
  source?: "manual" | "distilled" | "context_file";
}

export async function POST(request: Request) {
  try {
    const { userId, tenantId } = await requireOwner();

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "тело запроса не является корректным JSON" }, { status: 400 });
    }

    const raw = body as CreateBody;
    if (!raw || typeof raw.name !== "string" || typeof raw.body_md !== "string") {
      return Response.json(
        { error: "требуются поля name (string) и body_md (string)" },
        { status: 400 },
      );
    }

    const portrait = await withTenant(tenantId, async (client) => {
      return createPortrait(client, raw.name, raw.body_md, raw.source ?? "manual", userId);
    });

    return Response.json({ portrait });
  } catch (error) {
    return toResponse(error);
  }
}