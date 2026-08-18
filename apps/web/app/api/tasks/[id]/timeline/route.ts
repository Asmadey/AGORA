import { loadTimeline } from "@/lib/server/content-pack";
import { requireSession, toResponse } from "@/lib/server/guard";
import { withTenant } from "@/lib/server/db";
import { createPresignedGetUrl } from "@/lib/server/s3";

/**
 * Таймлайн материала и ссылка на ролик — для плеера на экране исследования.
 *
 * ─── Почему маршрут, а не серверный компонент ──────────────────────────────
 * Подписанная ссылка живёт час. Отрисованная на сервере страница кешируется
 * браузером и историей навигации, и открытая назавтра показала бы протухшие
 * ссылки на все кадры сразу — то есть пустой таймлайн без единой ошибки.
 * Маршрут запрашивается при открытии вкладки, и подписи всегда свежие.
 *
 * ─── Почему ролик и таймлайн вместе ────────────────────────────────────────
 * Порознь их не бывает: плеер без таймлайна — это просто видео, таймлайн без
 * плеера некуда перематывать. Два запроса дали бы два состояния загрузки и
 * возможность показать один без другого.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const { tenantId, userId } = await requireSession();

    // Ключ ролика читается из задачи под тенант-контекстом: RLS отвечает за то,
    // что чужой прогон сюда не попадёт. Отсутствие строки и чужая строка
    // неотличимы — так и должно быть.
    const videoRef = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<{
        video_ref: string | null;
        playback_ref: string | null;
      }>(
        "SELECT video_ref, playback_ref FROM tasks WHERE id = $1",
        [id],
      );
      // Копия для просмотра главнее исходника: она H.264 720p с индексом в
      // начале файла, то есть играет в любом браузере и перематывается сразу.
      // Исходник может оказаться в HEVC — Chrome покажет чёрный прямоугольник, —
      // а его moov обычно лежит в конце, и прыжок на вторую минуту означает
      // скачать весь файл. Исходник остаётся доступен отдельной ссылкой в
      // «Материалах»: там он нужен именно как исходник.
      return rows[0]?.playback_ref ?? rows[0]?.video_ref ?? null;
    });

    const timeline = await loadTimeline({ tenantId, userId }, id);

    // 404 на несуществующий прогон, 200 с пустым таймлайном — на существующий,
    // у которого пакет не сохранён. Разные факты: первый отправляет проверять
    // ссылку, второй — читать `degraded` отчёта.
    if (videoRef === null && timeline === null) {
      return Response.json({ error: "прогон не найден" }, { status: 404 });
    }

    return Response.json({
      video: videoRef ? safeUrl(videoRef) : null,
      timeline,
    });
  } catch (error) {
    return toResponse(error);
  }
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
