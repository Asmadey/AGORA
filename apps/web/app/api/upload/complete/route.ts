import { NextRequest, NextResponse } from "next/server";
import { requireSession, toResponse } from "@/lib/server/guard";
import { withTenant } from "@/lib/server/db";
import {
  createPresignedGetUrl,
  probeVideo,
  headObjectSize,
  S3_LIMITS,
  type VideoProbeResult,
} from "@/lib/server/s3";

export const runtime = "nodejs";
export const maxDuration = 60;
export const dynamic = "force-dynamic";

/**
 * POST /api/upload/complete
 *
 * Подтверждает загрузку видео в S3 и запускает ffprobe-валидацию.
 * После успешной проверки записывает video_ref и mode в tasks (или в черновик).
 *
 * Запрос: { key, mode }
 *   key   — S3 object key, полученный из /api/upload/presign
 *   mode  — "short" | "long"
 *
 * Ответ:  { key, probe: { durationSec, codec, width, height, sizeBytes, format } }
 *
 * ─── Почему ffprobe здесь, а не в presign ──────────────────────────────
 * На этапе presign файла ещё нет в S3 — клиент только получил URL. ffprobe
 * работает с реальным объектом, значит может запуститься только после загрузки.
 * Это второй уровень защиты: presign проверяет тип и размер по данным клиента,
 * complete проверяет кодек и длительность по реальному содержимому.
 */
export async function POST(req: NextRequest) {
  try {
    const session = await requireSession();

    const body = await req.json();
    const { key, mode } = body as { key?: string; mode?: string };

    if (!key || typeof key !== "string") {
      return NextResponse.json({ error: "key обязателен" }, { status: 400 });
    }
    if (mode !== "short" && mode !== "long") {
      return NextResponse.json(
        { error: "mode должен быть «short» или «long»" },
        { status: 400 },
      );
    }

    // Ключ обязан принадлежать этому арендатору — проверка по префиксу.
    // S3 сам не проверяет, кто запросил complete; без этой проверки один
    // арендатор мог бы «подтвердить» чужой объект.
    const expectedPrefix = `tenants/${session.tenantId}/uploads/`;
    if (!key.startsWith(expectedPrefix)) {
      return NextResponse.json(
        { error: "Ключ не принадлежит текущему арендатору" },
        { status: 403 },
      );
    }

    // Размер объекта из S3 (HEAD, без скачивания)
    const sizeBytes = await headObjectSize(key);
    if (sizeBytes > S3_LIMITS.MAX_FILE_SIZE) {
      return NextResponse.json(
        { error: `Файл в S3 превышает 700 МБ: ${Math.round(sizeBytes / 1024 / 1024)} МБ` },
        { status: 400 },
      );
    }

    // ffprobe по presigned GET URL
    const presignedGet = createPresignedGetUrl(key);
    const probe = await probeVideo(presignedGet, sizeBytes);

    // Сохраняем video_ref и mode в tasks (новая задача)
    // Визард (#7) позже соберёт полный task; здесь — только контент + режим.
    const taskId = await withTenant(session.tenantId, async (client) => {
      const { rows } = await client.query<{ id: string }>(
        `INSERT INTO tasks (tenant_id, video_ref, mode, status, created_by)
         VALUES ($1, $2, $3, 'QUEUED', $4)
         RETURNING id`,
        [session.tenantId, key, mode, session.userId],
      );
      return rows[0].id;
    });

    const result: { key: string; taskId: string; probe: VideoProbeResult } = {
      key,
      taskId,
      probe,
    };
    return NextResponse.json(result);
  } catch (error) {
    return toResponse(error);
  }
}