import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { rerunPrefill, type SourceRun } from "@/lib/rerun";

/**
 * Исходные данные для перезапуска исследования (#30).
 *
 * Отдаёт то, что визард подставит в поля: материал, набор персон, настройки
 * прогона. Анкету не отдаёт намеренно — ради новых вопросов перезапуск и
 * делают, см. lib/rerun.ts.
 *
 * Отдельный маршрут, а не расширение GET прогона: у прогона нет GET, а заводить
 * его целиком ради четырёх полей значило бы описать в OpenAPI весь отчёт.
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

    const source = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<{
        id: string;
        mode: string | null;
        video_ref: string | null;
        source_name: string | null;
        persona_set_id: string | null;
        project_id: string | null;
        replication_count: number | null;
        settings_snapshot: Record<string, unknown> | null;
        title: string | null;
      }>(
        `SELECT id, mode, video_ref, source_name, persona_set_id, project_id,
                replication_count, settings_snapshot, title
           FROM tasks WHERE id = $1::uuid`,
        [id],
      );
      return rows[0] ?? null;
    });

    // RLS уже отрезал чужих арендаторов: строки просто нет. «Не ваш прогон» и
    // «нет такого» отвечают одинаково намеренно.
    if (!source) {
      return Response.json({ error: "прогон не найден" }, { status: 404 });
    }

    const snapshot = source.settings_snapshot ?? {};
    const run: SourceRun = {
      id: source.id,
      mode: source.mode,
      videoRef: source.video_ref,
      sourceName: source.source_name,
      personaSetId: source.persona_set_id,
      projectId: source.project_id,
      replicationCount: source.replication_count,
      whisperModel:
        typeof snapshot.whisperModel === "string" ? snapshot.whisperModel : null,
      title: source.title,
    };

    return Response.json({ prefill: rerunPrefill(run) });
  } catch (error) {
    return toResponse(error);
  }
}
