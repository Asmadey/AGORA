import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { hashToken, newToken, shareUrl, ttlToExpiry, type Ttl } from "@/lib/share";

/**
 * Публичная ссылка на отчёт (#29).
 *
 * POST   — выпустить ссылку. Возвращает адрес ОДИН раз: в базе лежит только
 *          SHA-256, и восстановить токен из неё нельзя. Потерянную ссылку не
 *          «показывают снова», а выпускают заново.
 * DELETE — отозвать все действующие ссылки на отчёт.
 *
 * ─── Почему адрес строится от заголовков запроса ──────────────────────────
 * Прежний диалог показывал `https://agora.studio/s/…` — домен, которого у
 * продукта нет. Продукт живёт на sslip.io по адресу сервера, и любая константа
 * здесь разойдётся с реальностью. `request.url` — то, по чему пользователь
 * пришёл сюда сам.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface Body {
  ttl?: Ttl;
  scope?: "full" | "aggregate";
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { tenantId, userId } = await requireSession();
    const { id } = await params;

    const body = (await request.json().catch(() => ({}))) as Body;
    const ttl: Ttl = body.ttl ?? "7d";
    const scope = body.scope === "aggregate" ? "aggregate" : "full";

    let expiresAt: Date | null;
    try {
      expiresAt = ttlToExpiry(ttl);
    } catch {
      return Response.json({ error: `неизвестный срок жизни: ${ttl}` }, { status: 400 });
    }

    const token = newToken();

    await withTenant(tenantId, async (client) => {
      // Ссылка выпускается на ПРОГОН. Строки отчёта в Postgres нет и не будет:
      // отчёт живёт в MongoDB (#21), а таблица `reports` пуста — см. миграцию 38.
      await client.query(
        `INSERT INTO report_shares (tenant_id, task_id, token_hash, scope, expires_at, created_by)
         VALUES ($1, $2::uuid, $3, $4, $5, $6)`,
        [tenantId, id, hashToken(token), scope, expiresAt, userId],
      );
    });

    return Response.json({
      url: shareUrl(new URL(request.url).origin, token),
      expiresAt: expiresAt?.toISOString() ?? null,
      scope,
    });
  } catch (error) {
    return toResponse(error);
  }
}

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { tenantId } = await requireSession();
    const { id } = await params;

    const revoked = await withTenant(tenantId, async (client) => {
      const { rowCount } = await client.query(
        `UPDATE report_shares s SET revoked_at = now()
          FROM reports r
         WHERE s.report_id = r.id AND r.task_id = $1::uuid AND s.revoked_at IS NULL`,
        [id],
      );
      return rowCount ?? 0;
    });

    return Response.json({ revoked });
  } catch (error) {
    return toResponse(error);
  }
}
