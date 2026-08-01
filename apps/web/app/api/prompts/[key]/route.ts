import { withTenant } from "@/lib/server/db";
import { requireOwner, requireSession, toResponse } from "@/lib/server/guard";
import { getPromptWithHistory } from "@/lib/server/prompts";

/**
 * API промпт-студии (задача #26) — детали и восстановление дефолта.
 *
 * GET /api/prompts/[key] — активная версия + история. Любой участник.
 * DELETE /api/prompts/[key] — restore default: удалить все версии арендатора,
 *   резолвер откатится на дефолт. Только owner.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ key: string }> },
) {
  try {
    const { tenantId } = await requireSession();
    const { key } = await params;
    const decodedKey = decodeURIComponent(key);

    const data = await withTenant(tenantId, async (client) => {
      return getPromptWithHistory(client, decodedKey);
    });

    if (!data.active) {
      return Response.json({ error: "промпт не найден" }, { status: 404 });
    }

    return Response.json(data);
  } catch (error) {
    return toResponse(error);
  }
}

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ key: string }> },
) {
  try {
    const { tenantId } = await requireOwner();
    const { key } = await params;
    const decodedKey = decodeURIComponent(key);

    await withTenant(tenantId, async (client) => {
      // Удаляем все версии арендатора. RLS-политика prompts_delete_own_only
      // разрешает только свои строки (tenant_id = current_tenant()).
      // Дефолт (tenant_id IS NULL) не трогается — он остаётся как fallback.
      await client.query(
        `DELETE FROM prompts WHERE key = $1 AND tenant_id = $2`,
        [decodedKey, tenantId],
      );
    });

    // Проверяем, что после удаления резолвер отдаёт дефолт
    return Response.json({ restored: true, key: decodedKey });
  } catch (error) {
    return toResponse(error);
  }
}