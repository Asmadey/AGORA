import { withTenant } from "@/lib/server/db";
import { requireOwner, toResponse } from "@/lib/server/guard";
import { type PromptVersion } from "@/lib/server/prompts";

/**
 * API промпт-студии (задача #26) — активация существующей версии.
 *
 * POST /api/prompts/[key]/activate { version: number }
 *   Деактивирует текущую активную версию арендатора и активирует указанную.
 *   Только owner. Версия обязана существовать у этого арендатора —
 *   активировать чужую или дефолт нельзя.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ key: string }> },
) {
  try {
    const { tenantId } = await requireOwner();
    const { key } = await params;
    const decodedKey = decodeURIComponent(key);

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "тело запроса не является корректным JSON" }, { status: 400 });
    }

    const raw = body as { version?: number };
    if (!raw || typeof raw.version !== "number" || !Number.isInteger(raw.version) || raw.version < 1) {
      return Response.json({ error: "требуется поле version (целое > 0)" }, { status: 400 });
    }

    const result = await withTenant(tenantId, async (client) => {
      // Проверяем, что версия существует у арендатора
      const { rows: existing } = await client.query<{ id: string }>(
        `SELECT id FROM prompts WHERE key = $1 AND tenant_id = $2 AND version = $3`,
        [decodedKey, tenantId, raw.version],
      );
      if (existing.length === 0) {
        return { error: "версия не найдена у этого арендатора", status: 404 } as const;
      }

      // Деактивируем все активные версии арендатора для этого ключа.
      // Уникальный индекс prompts_tenant_key_active_uniq гарантирует, что
      // двух активных версий быть не может — БД держит ограничение, а не
      // приложение (кейс 15).
      await client.query(
        `UPDATE prompts SET is_active = false
         WHERE key = $1 AND tenant_id = $2 AND is_active = true`,
        [decodedKey, tenantId],
      );

      // Активируем указанную версию
      const { rows } = await client.query<PromptVersion>(
        `UPDATE prompts SET is_active = true
         WHERE key = $1 AND tenant_id = $2 AND version = $3
         RETURNING id, tenant_id, key, stage, template, variables,
                   model_params, version, is_active, is_default,
                   created_at::text as created_at`,
        [decodedKey, tenantId, raw.version],
      );

      return { prompt: rows[0] } as const;
    });

    if ("error" in result) {
      return Response.json({ error: result.error }, { status: result.status });
    }

    return Response.json({ prompt: result.prompt });
  } catch (error) {
    return toResponse(error);
  }
}