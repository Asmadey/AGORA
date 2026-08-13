import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { collection } from "@/lib/server/mongo";
import { deleteObject } from "@/lib/server/s3";

/**
 * Удаление и отмена исследования.
 *
 * DELETE /api/tasks/{id}         — удалить, если можно; иначе запросить отмену
 * DELETE /api/tasks/{id}?force=1 — удалить, не дожидаясь воркера
 *
 * ─── Почему раньше было нельзя ─────────────────────────────────────────────
 * Прежняя версия отвечала 409 на QUEUED и RUNNING, и объяснение было честным:
 * у воркера не было канала отмены. Он читает чекпоинт и пишет прогресс, а
 * пропавшая строка задачи для него выглядит сбоем базы — и он уходит в повтор.
 *
 * Но у пользователя накопились прогоны, которые не возьмёт уже никто: воркер
 * перезапускался, очередь чистилась, задача осталась в QUEUED навсегда. Ответ
 * «дождитесь окончания» для них — обещание, которое не исполнится.
 *
 * ─── Что делается теперь ───────────────────────────────────────────────────
 * Канал отмены заведён по-настоящему: `tasks.cancel_requested_at` читает
 * воркер между узлами (`pipeline/graph.py`, `RunCancelled`). Отсюда три случая:
 *
 *   завершённый прогон            → удаляем сразу;
 *   зависший QUEUED (см. ниже)    → удаляем сразу, воркер его не взял;
 *   активный QUEUED или RUNNING   → ставим флаг отмены, отвечаем 202.
 *
 * Отмена не мгновенна: воркер проверяет её между узлами, а разбор кадров длится
 * минуты. Поэтому 202 и «отменяется», а не 200 и «отменено».
 *
 * ─── Что уходит вместе с задачей ───────────────────────────────────────────
 * Каскадом в Postgres: `reports`, `report_shares`, `chat_threads`. Отдельно —
 * документы Mongo (`reports`, `report_personas`) и ролик в S3. Транзакции между
 * тремя хранилищами нет и быть не может, поэтому порядок выбран так, чтобы
 * любой обрыв оставлял мусор, а не ложь: сначала внешние хранилища, строка в
 * Postgres — последней. Обрыв посередине оставит осиротевший файл, но не
 * исследование, ссылающееся на удалённые данные.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Сколько задача может простоять в QUEUED, прежде чем считаться зависшей.
 *
 * Пять минут — это заметно больше, чем нужно живому воркеру, чтобы забрать
 * задачу из очереди (там доли секунды), и заметно меньше, чем терпение
 * пользователя. Меньший порог удалял бы задачи, которые воркер вот-вот возьмёт;
 * больший — заставлял бы ждать неизвестно чего.
 */
const STALE_QUEUED_MINUTES = 5;

interface TaskRow {
  status: string;
  video_ref: string | null;
  stale: boolean;
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const { tenantId } = await requireSession();
    const force = new URL(request.url).searchParams.get("force") === "1";

    const outcome = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<TaskRow>(
        `SELECT status,
                video_ref,
                created_at < now() - make_interval(mins => $2) AS stale
           FROM tasks
          WHERE id = $1`,
        [id, STALE_QUEUED_MINUTES],
      );
      if (rows.length === 0) return { kind: "missing" as const };

      const { status, video_ref, stale } = rows[0];
      const active = status === "QUEUED" || status === "RUNNING";

      // Активный прогон, который воркер действительно ведёт: просим отменить.
      // Исключение — зависший QUEUED и явный force от пользователя.
      if (active && !force && !(status === "QUEUED" && stale)) {
        await client.query(
          `UPDATE tasks SET cancel_requested_at = COALESCE(cancel_requested_at, now())
            WHERE id = $1`,
          [id],
        );
        return { kind: "cancelling" as const, status };
      }

      await client.query(`DELETE FROM tasks WHERE id = $1`, [id]);
      return { kind: "deleted" as const, videoRef: video_ref, wasActive: active };
    });

    if (outcome.kind === "missing") {
      // 404, а не 403: чужой прогон под RLS не находится, и подтверждать его
      // существование ответом нельзя.
      return Response.json({ error: "исследование не найдено" }, { status: 404 });
    }

    if (outcome.kind === "cancelling") {
      return Response.json(
        {
          cancelling: true,
          status: outcome.status,
          message:
            outcome.status === "RUNNING"
              ? "Отмена запрошена. Воркер остановится между этапами — это может занять несколько минут."
              : "Отмена запрошена. Если воркер уже взял задачу, он остановится между этапами.",
        },
        { status: 202 },
      );
    }

    // ─── Уборка за пределами Postgres ────────────────────────────────────────
    // Отказы здесь не отменяют удаления: строки уже нет, и возвращать ошибку
    // значило бы предлагать повторить операцию, которая не повторяется.
    // Причины собираются и возвращаются — молчаливый мусор хуже названного.
    const leftovers: string[] = [];

    try {
      // tenant_id в фильтре обязателен: в Mongo нет RLS, и это единственное,
      // что не даёт удалить чужой отчёт по угаданному task_id.
      const filter = { tenant_id: tenantId, task_id: id };
      await (await collection("reports")).deleteMany(filter);
      await (await collection("report_personas")).deleteMany(filter);
    } catch (e) {
      leftovers.push(`документы отчёта в Mongo: ${(e as Error).message}`);
    }

    if (outcome.videoRef) {
      try {
        await deleteObject(outcome.videoRef);
      } catch (e) {
        leftovers.push(`ролик в хранилище: ${(e as Error).message}`);
      }
    }

    return Response.json({ ok: true, cancelledActive: outcome.wasActive, leftovers });
  } catch (error) {
    return toResponse(error);
  }
}
