import { decideAudienceResume } from "@/lib/audience-resume";
import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { listPersonaSets } from "@/lib/server/personas";
import { enqueueAudience } from "@/lib/server/queue";

/** Продолжает failed-набор теми же критериями, корпусом и настройками. */
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { tenantId } = await requireSession();
    const { id } = await params;

    const result = await withTenant(tenantId, async (client) => {
      const sets = await listPersonaSets(client, id);
      if (sets.length === 0) return { kind: "missing" as const };

      const set = sets[0];
      const decision = decideAudienceResume(set, tenantId);
      if (decision.kind !== "queued") return decision;

      // Payload строится из строки набора, а не из текущих settings: иначе
      // продолжение смешало бы два разных разброса формулировок в одной базе.
      await enqueueAudience(decision.payload);
      return {
        kind: "queued" as const,
        generatedCount: set.generatedCount,
        size: set.size,
      };
    });

    if (result.kind === "missing") {
      // Чужой набор под RLS неотличим от несуществующего.
      return Response.json({ error: "набор не найден" }, { status: 404 });
    }
    if (result.kind === "not-resumable") {
      return Response.json(
        { error: `продолжить можно только для набора в статусе failed (сейчас ${result.status})` },
        { status: 409 },
      );
    }

    return Response.json({
      personaSetId: id,
      status: "generating",
      resumed: true,
      generatedCount: result.generatedCount,
      size: result.size,
    }, { status: 202 });
  } catch (error) {
    return toResponse(error);
  }
}
