import { CONTEXT_EXTENSIONS, CONTEXT_FILE_MAX_BYTES, contextMimeType } from "@/lib/context-file";
import { createPresignedPutUrl, S3_LIMITS } from "@/lib/server/s3";
import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

/**
 * POST /api/audience-context
 *
 * Резервирует tenant-scoped строку и возвращает presigned PUT для PDF/XLS.
 * Сам бинарный файл не проходит через Node: браузер кладёт его прямо в S3,
 * а воркер позже скачивает ключ из строки, закрытой RLS.
 */
export async function POST(request: Request) {
  try {
    const { tenantId } = await requireSession();
    const body = (await request.json()) as {
      fileName?: unknown;
      contentType?: unknown;
      fileSize?: unknown;
    };

    const fileName = typeof body.fileName === "string" ? body.fileName.trim() : "";
    const contentType = typeof body.contentType === "string" ? body.contentType : "";
    const fileSize = body.fileSize;
    const lower = fileName.toLowerCase();
    const extension = CONTEXT_EXTENSIONS.find((ext) => lower.endsWith(ext));

    if (!fileName || fileName.length > 255 || fileName.includes("/")) {
      return Response.json({ error: "fileName должен быть коротким именем файла" }, { status: 400 });
    }
    if (!extension || [".txt", ".md"].includes(extension)) {
      return Response.json(
        { error: "этот маршрут принимает только .pdf, .xls и .xlsx" },
        { status: 400 },
      );
    }
    if (
      typeof fileSize !== "number" ||
      !Number.isInteger(fileSize) ||
      fileSize < 0 ||
      fileSize > CONTEXT_FILE_MAX_BYTES
    ) {
      return Response.json(
        { error: `размер файла должен быть от 0 до ${CONTEXT_FILE_MAX_BYTES / 1024 / 1024} МБ` },
        { status: 400 },
      );
    }

    // MIME приходит от браузера и не является источником истины, но проверяем
    // его мягко: application/octet-stream допустим для старого XLS, где
    // браузер часто не знает тип. Расширение остаётся обязательным.
    const expectedMime = contextMimeType(fileName);
    if (contentType && contentType !== expectedMime && contentType !== "application/octet-stream") {
      return Response.json(
        { error: `тип ${contentType} не соответствует расширению ${extension}` },
        { status: 400 },
      );
    }

    const { url, key } = createPresignedPutUrl(tenantId, fileName, expectedMime);
    const id = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<{ id: string }>(
        `INSERT INTO audience_context_files
           (tenant_id, filename, content_type, size_bytes, s3_key, status)
         VALUES (app.current_tenant(), $1, $2, $3, $4, 'uploaded')
         RETURNING id::text`,
        [fileName, expectedMime, fileSize, key],
      );
      return rows[0].id;
    });

    return Response.json({
      id,
      uploadUrl: url,
      key,
      contentType: expectedMime,
      expiresInSeconds: S3_LIMITS.EXPIRES_SECONDS,
    });
  } catch (error) {
    return toResponse(error);
  }
}

/** Убирает незавершённую резервацию, не раскрывая объект другому арендатору. */
export async function DELETE(request: Request) {
  try {
    const { tenantId } = await requireSession();
    const body = (await request.json()) as { id?: unknown };
    if (typeof body.id !== "string" || !isUuid(body.id)) {
      return Response.json({ error: "id обязателен" }, { status: 400 });
    }
    await withTenant(tenantId, (client) =>
      client.query(
        "UPDATE audience_context_files SET status='failed' WHERE id = $1::uuid AND status='uploaded'",
        [body.id],
      ).then(() => undefined),
    );
    return Response.json({ ok: true });
  } catch (error) {
    return toResponse(error);
  }
}
