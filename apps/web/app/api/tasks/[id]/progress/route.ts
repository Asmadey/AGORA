import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import {
  progressSnapshot,
  subscribeProgress,
  type ProgressEvent,
} from "@/lib/server/progress";

/**
 * SSE-поток прогресса прогона (задача #12, Decision Log #3).
 *
 * GET /api/tasks/<id>/progress → text/event-stream
 *
 * ─── Порядок: сперва снимок, потом подписка ────────────────────────────────
 * Первым в поток уходит текущее состояние из ключа Valkey, и только затем
 * открывается подписка на канал. Это и есть «переподключается без потери
 * состояния» из cdd.
 *
 * Обратный порядок терял бы события, случившиеся между чтением ключа и
 * подпиской. Порядок «только подписка» терял бы всё, что произошло до
 * подключения: пользователь, вернувшийся через десять минут в середину
 * транскрипции, видел бы пустой экран до следующей смены узла — то есть
 * несколько минут, неотличимых от зависшего прогона.
 *
 * ─── Почему прогон проверяется в базе, а не только по сессии ───────────────
 * Идентификатор прогона — uuid в URL. Сессия говорит, кто пришёл, но не
 * говорит, его ли это прогон. Без проверки принадлежности открытый поток на
 * чужой идентификатор отвечал бы 200 вместо 404 — и это уже утечка: по коду
 * ответа видно, что такой прогон существует.
 *
 * ─── Почему heartbeat ──────────────────────────────────────────────────────
 * Транскрипция 15-минутного ролика идёт минуты без единого события. Прокси и
 * балансировщики закрывают молчащее соединение по таймауту, и браузер получает
 * обрыв там, где всё исправно. Комментарий `: ping` раз в 20 секунд держит
 * соединение и в поток событий не попадает — по спецификации SSE строка,
 * начинающаяся с двоеточия, игнорируется.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const HEARTBEAT_MS = 20_000;

/** Терминальные статусы: после них слать нечего, поток закрывается. */
const TERMINAL = new Set(["REPORT_READY", "FAILED"]);

async function belongsToTenant(tenantId: string, taskId: string): Promise<boolean> {
  return withTenant(tenantId, async (client) => {
    const { rowCount } = await client.query(
      "SELECT 1 FROM tasks WHERE id = $1::uuid",
      [taskId],
    );
    return (rowCount ?? 0) > 0;
  });
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  let tenantId: string;
  try {
    ({ tenantId } = await requireSession());
  } catch (e) {
    return toResponse(e);
  }

  const { id } = await params;

  // RLS отрезает чужих арендаторов на уровне базы: строки просто нет, и «не
  // ваш прогон» неотличимо от «нет такого». Это верное поведение — разные
  // ответы на эти два случая сами по себе сообщали бы о существовании чужого.
  let exists: boolean;
  try {
    exists = await belongsToTenant(tenantId, id);
  } catch (e) {
    return toResponse(e);
  }
  if (!exists) {
    return Response.json({ error: "прогон не найден" }, { status: 404 });
  }

  const encoder = new TextEncoder();
  let unsubscribe: (() => Promise<void>) | null = null;
  let heartbeat: ReturnType<typeof setInterval> | null = null;

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      let closed = false;

      const send = (event: ProgressEvent) => {
        if (closed) return;
        controller.enqueue(
          encoder.encode(`event: progress\ndata: ${JSON.stringify(event)}\n\n`),
        );
        if (TERMINAL.has(event.status)) {
          void shutdown();
        }
      };

      const shutdown = async () => {
        if (closed) return;
        closed = true;
        if (heartbeat) clearInterval(heartbeat);
        if (unsubscribe) await unsubscribe();
        try {
          controller.close();
        } catch {
          // Поток уже закрыт клиентом — закрывать нечего.
        }
      };

      try {
        // 1. Снимок: то, что уже произошло.
        const snapshot = await progressSnapshot(id);
        if (snapshot) {
          send(snapshot);
        } else {
          // Прогон в очереди и ещё ничего не написал. Явное событие лучше
          // молчания: экран показывает «в очереди», а не пустоту.
          send({ task_id: id, node: "pipeline", status: "QUEUED", at: Date.now() / 1000 });
        }

        // 2. Подписка: то, что произойдёт дальше.
        if (!closed) {
          unsubscribe = await subscribeProgress(id, send);
        }
      } catch (e) {
        controller.enqueue(
          encoder.encode(
            `event: progress\ndata: ${JSON.stringify({
              task_id: id,
              node: "pipeline",
              status: "FAILED",
              at: Date.now() / 1000,
              error: e instanceof Error ? e.message : "прогресс недоступен",
            })}\n\n`,
          ),
        );
        await shutdown();
        return;
      }

      heartbeat = setInterval(() => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(": ping\n\n"));
        } catch {
          void shutdown();
        }
      }, HEARTBEAT_MS);

      // Уход клиента обязан снять подписку. Без этого каждая закрытая вкладка
      // оставляет за собой соединение к Valkey до упора в лимит.
      request.signal.addEventListener("abort", () => void shutdown());
    },

    async cancel() {
      if (heartbeat) clearInterval(heartbeat);
      if (unsubscribe) await unsubscribe();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // Отключает буферизацию у nginx: без этого прокси копит события и отдаёт
      // их пачкой, превращая поток в один запоздалый ответ.
      "X-Accel-Buffering": "no",
    },
  });
}
