import { NextRequest, NextResponse } from "next/server";
import { requireSession, toResponse } from "@/lib/server/guard";
import { createPresignedPutUrl, S3_LIMITS } from "@/lib/server/s3";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/upload/presign
 *
 * Возвращает presigned PUT URL для прямой загрузки видео в S3 TimeWeb.
 * Файл не проходит через сервер Next.js — браузер грузит прямо в S3.
 *
 * Запрос: { fileName, contentType, fileSize }
 * Ответ:  { uploadUrl, key, expiresInSeconds }
 *
 * ─── Почему валидация размера здесь, а не в complete ───────────────────
 * Размер известен до загрузки (File.size в браузере). Отказать здесь —
 * сэкономить 700 МБ трафика в никуда. Но это не единственная проверка:
 * complete всё равно прогоняет ffprobe, который увидит реальный размер
 * объекта в S3. Двойная проверка — намеренная: клиентскую информацию
 * нельзя доверять без подтверждения сервером.
 */
export async function POST(req: NextRequest) {
  try {
    const session = await requireSession();

    const body = await req.json();
    const { fileName, contentType, fileSize } = body as {
      fileName?: string;
      contentType?: string;
      fileSize?: number;
    };

    if (!fileName || typeof fileName !== "string") {
      return NextResponse.json({ error: "fileName обязателен" }, { status: 400 });
    }
    if (!contentType || typeof contentType !== "string") {
      return NextResponse.json({ error: "contentType обязателен" }, { status: 400 });
    }

    // Валидация MIME-типа
    if (!S3_LIMITS.ALLOWED_MIME_TYPES.includes(contentType)) {
      return NextResponse.json(
        {
          error: `Тип «${contentType}» не поддерживается. Разрешённые: ${S3_LIMITS.ALLOWED_MIME_TYPES.join(", ")}`,
        },
        { status: 400 },
      );
    }

    // Валидация расширения
    const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
    if (!S3_LIMITS.ALLOWED_EXTENSIONS.includes(ext)) {
      return NextResponse.json(
        {
          error: `Расширение «.${ext}» не поддерживается. Разрешённые: ${S3_LIMITS.ALLOWED_EXTENSIONS.join(", ")}`,
        },
        { status: 400 },
      );
    }

    // Преварительная проверка размера (complete перепроверит)
    if (typeof fileSize === "number" && fileSize > S3_LIMITS.MAX_FILE_SIZE) {
      return NextResponse.json(
        {
          error: `Файл превышает лимм 700 МБ: ${Math.round(fileSize / 1024 / 1024)} МБ`,
        },
        { status: 400 },
      );
    }

    // Генерация presigned URL с tenant_id в ключе
    const { url, key } = createPresignedPutUrl(session.tenantId, fileName, contentType);

    return NextResponse.json({
      uploadUrl: url,
      key,
      expiresInSeconds: S3_LIMITS.EXPIRES_SECONDS,
    });
  } catch (error) {
    return toResponse(error);
  }
}