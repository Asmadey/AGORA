import { loadTimeline } from "@/lib/server/content-pack";
import { createPresignedGetUrl } from "@/lib/server/s3";
import { withShareToken } from "@/lib/server/db";
import { parseScope } from "@/lib/share-scope";

/**
 * Материал прогона по публичной ссылке: плеер и таймлайн без входа в систему.
 *
 * ─── Почему отдельный маршрут, а не тот же, что у внутренней страницы ─────
 * `/api/tasks/[id]/timeline` начинается с `requireSession()`. У гостя сессии
 * нет и быть не должно — его право на этот прогон даёт токен в адресе, а не
 * учётная запись. Добавить в тот маршрут «или токен» значило бы завести в
 * закрытом сегменте ветку, открытую наружу; такую ветку легко не заметить при
 * следующей правке.
 *
 * ─── Почему сегмент /share, а не /api/share ───────────────────────────────
 * `PUBLIC_PATHS` сопоставляется по префиксу, и `/share` там уже есть — этот
 * маршрут публичен ровно потому, что лежит внутри уже публичного сегмента, а
 * не потому, что кто-то добавил ещё одно исключение. Новый префикс под `/api`
 * открыл бы наружу целое поддерево, и следующий маршрут в нём оказался бы
 * публичным сам собой.
 *
 * ─── Что защищает от чужого прогона ───────────────────────────────────────
 * Не этот файл, а база. Соединение идёт под ролью `agora_share`, которой
 * политика `tasks_public_share_read` (миграция 39) отдаёт ровно одну строку —
 * прогон, на который выпущена живая ссылка с предъявленным токеном. Отозванная
 * или просроченная ссылка не вернёт ничего, и код об этом не спрашивает.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;

  const grant = await withShareToken(token, async (client) => {
    const { rows } = await client.query<{
      task_id: string | null;
      tenant_id: string;
      scope: string;
    }>(
      `SELECT task_id, tenant_id, scope
         FROM report_shares
        WHERE token_hash = app.current_share_token_hash()
          AND revoked_at IS NULL
          AND (expires_at IS NULL OR expires_at > now())`,
    );
    const row = rows[0];
    if (!row?.task_id) return null;

    // Область проверяется ЗДЕСЬ, а не политикой. Политика отвечает на вопрос
    // «какой прогон открывает этот токен»; «что из него показывать» — решение
    // страницы, и для заголовка оно другое, чем для материала. Ссылка «только
    // сводка» обязана сохранить заголовок и не отдать ролик.
    if (parseScope(row.scope) !== "full") return null;

    const { rows: taskRows } = await client.query<{
      video_ref: string | null;
      playback_ref: string | null;
    }>("SELECT video_ref, playback_ref FROM tasks WHERE id = $1", [row.task_id]);

    return {
      taskId: row.task_id,
      tenantId: row.tenant_id,
      // Копия для просмотра главнее исходника — та же причина, что во
      // внутреннем маршруте: она H.264 720p с индексом в начале файла.
      videoRef: taskRows[0]?.playback_ref ?? taskRows[0]?.video_ref ?? null,
    };
  }).catch(() => null);

  // Один ответ на «ссылки нет», «ссылка отозвана», «область — только сводка» и
  // «прогона не существует». Разные коды рассказали бы держателю ссылки, что
  // именно не так, — то есть подтвердили бы существование того, чего он не
  // должен видеть.
  if (!grant) return Response.json({ error: "недоступно" }, { status: 404 });

  // Отчёт и пакет материала лежат в MongoDB, куда RLS не достаёт. Фильтр по
  // арендатору берётся из строки ссылки, а не из адреса.
  const timeline = await loadTimeline({ tenantId: grant.tenantId, userId: "" }, grant.taskId);

  if (grant.videoRef === null && timeline === null) {
    return Response.json({ error: "недоступно" }, { status: 404 });
  }

  return Response.json({
    video: grant.videoRef ? safeUrl(grant.videoRef) : null,
    timeline,
  });
}

/**
 * Подпись ссылки на ролик. null — S3 не настроен.
 *
 * Отсутствие ссылки не отменяет таймлайн: описания сцен и реплики читаются и
 * без видео, а плеер в этом случае просто не показывается.
 */
function safeUrl(key: string): string | null {
  try {
    return createPresignedGetUrl(key);
  } catch {
    return null;
  }
}
