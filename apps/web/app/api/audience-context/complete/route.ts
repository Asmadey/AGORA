import { headObjectSize } from "@/lib/server/s3";
import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

/**
 * POST /api/audience-context/complete
 *
 * Проверяет, что объект действительно появился в S3. Извлечение текста здесь
 * намеренно не делается: браузер получает только факт загрузки, а PDF/XLS
 * разбирается в том же воркере, где живёт portrait.distill.
 */
export async function POST(request: Request) {
  try {
    const { tenantId } = await requireSession();
    const body = (await request.json()) as { id?: unknown };
    if (typeof body.id !== "string" || !isUuid(body.id)) {
      return Response.json({ error: "id обязателен" }, { status: 400 });
    }

    const file = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<{
        id: string;
        s3_key: string;
        size_bytes: number | null;
      }>(
        "SELECT id::text, s3_key, size_bytes FROM audience_context_files WHERE id = $1::uuid",
        [body.id],
      );
      return rows[0] ?? null;
    });
    if (!file) {
      return Response.json({ error: "файл контекста не найден" }, { status: 404 });
    }

    let actualSize: number;
    try {
      actualSize = await headObjectSize(file.s3_key);
    } catch (error) {
      const reason = `объект контекста не найден в S3: ${(error as Error).message}`;
      await withTenant(tenantId, (client) =>
        client.query(
          "UPDATE audience_context_files SET status='failed' WHERE id = $1::uuid",
          [file.id],
        ).then(() => undefined),
      );
      return Response.json({ error: reason }, { status: 400 });
    }

    if (actualSize !== file.size_bytes || actualSize === 0) {
      const reason =
        actualSize === 0
          ? "файл контекста пуст"
          : `размер объекта не совпал: ожидалось ${file.size_bytes}, получено ${actualSize}`;
      await withTenant(tenantId, (client) =>
        client.query(
          "UPDATE audience_context_files SET status='failed' WHERE id = $1::uuid",
          [file.id],
        ).then(() => undefined),
      );
      return Response.json({ error: reason }, { status: 400 });
    }

    return Response.json({ id: file.id, status: "uploaded", sizeBytes: actualSize });
  } catch (error) {
    return toResponse(error);
  }
}
