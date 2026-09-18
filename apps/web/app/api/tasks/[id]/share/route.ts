import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { publicOrigin } from "@/lib/public-origin";
import {
  ACTIVE_SHARES_QUERY,
  REVOKE_ALL_SHARES_QUERY,
  REVOKE_SHARE_QUERY,
  shareUrl,
  ttlToExpiry,
  type Ttl,
} from "@/lib/share";
import { hashToken, newToken } from "@/lib/server/share-token";

/**
 * Публичная ссылка на отчёт (#29).
 *
 * POST   — выпустить ссылку. Возвращает адрес ОДИН раз: в базе лежит только
 *          SHA-256, и восстановить токен из неё нельзя. Потерянную ссылку не
 *          «показывают снова», а выпускают заново.
 * GET    — перечислить действующие ссылки без токенов.
 * DELETE — отозвать одну ссылку по shareId или все действующие ссылки.
 *
 * ─── Откуда берётся адрес ─────────────────────────────────────────────────
 * Из `AUTH_URL`, а при его отсутствии — из заголовков обратного прокси. НЕ из
 * `request.url`: Next.js слушает 0.0.0.0:3000 внутри контейнера, и первая
 * редакция выдавала ссылки вида `https://0.0.0.0:3000/…` — отправить такую
 * нельзя никому. Заметить это по коду было нельзя: в разработке, где прокси
 * нет, оба адреса совпадают. См. lib/public-origin.ts.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface Body {
  ttl?: Ttl;
  scope?: "full" | "aggregate";
}

interface ActiveShareRow {
  id: string;
  created_at: Date;
  expires_at: Date | null;
  scope: "full" | "aggregate";
  view_count: number;
}

function isoDate(value: Date | string | null): string | null {
  if (value === null) return null;
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { tenantId } = await requireSession();
    const { id } = await params;

    const shares = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<ActiveShareRow>(ACTIVE_SHARES_QUERY, [id]);
      return rows.map((row) => ({
        id: row.id,
        createdAt: isoDate(row.created_at),
        expiresAt: isoDate(row.expires_at),
        scope: row.scope,
        viewCount: row.view_count,
      }));
    });

    return Response.json({ active: shares });
  } catch (error) {
    return toResponse(error);
  }
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

    const shareId = await withTenant(tenantId, async (client) => {
      // Ссылка выпускается на ПРОГОН. Строки отчёта в Postgres нет и не будет:
      // отчёт живёт в MongoDB (#21), а таблица `reports` пуста — см. миграцию 38.
      const { rows } = await client.query<{ id: string }>(
        `INSERT INTO report_shares (tenant_id, task_id, token_hash, scope, expires_at, created_by)
         VALUES ($1, $2::uuid, $3, $4, $5, $6)
         RETURNING id`,
        [tenantId, id, hashToken(token), scope, expiresAt, userId],
      );
      return rows[0].id;
    });

    const origin = publicOrigin({
      authUrl: process.env.AUTH_URL,
      forwardedHost: request.headers.get("x-forwarded-host"),
      host: request.headers.get("host"),
      forwardedProto: request.headers.get("x-forwarded-proto"),
      requestUrl: request.url,
    });
    if (!origin) {
      // Ссылка с недостижимым адресом бесполезна ровно так же, как её
      // отсутствие, но выглядит рабочей. Отказ честнее.
      return Response.json(
        {
          error:
            "не удалось определить публичный адрес продукта: задайте AUTH_URL " +
            "либо настройте заголовки обратного прокси",
        },
        { status: 500 },
      );
    }

    return Response.json({
      shareId,
      url: shareUrl(origin, token),
      expiresAt: expiresAt?.toISOString() ?? null,
      scope,
    });
  } catch (error) {
    return toResponse(error);
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { tenantId } = await requireSession();
    const { id } = await params;
    const shareId = new URL(request.url).searchParams.get("shareId");

    const revoked = await withTenant(tenantId, async (client) => {
      const { rowCount } = await client.query(
        shareId ? REVOKE_SHARE_QUERY : REVOKE_ALL_SHARES_QUERY,
        shareId ? [shareId, id] : [id],
      );
      return rowCount ?? 0;
    });

    return Response.json({ revoked });
  } catch (error) {
    return toResponse(error);
  }
}
