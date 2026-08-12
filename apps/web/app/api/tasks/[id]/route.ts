import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";

/**
 * Удаление прогона.
 *
 * DELETE /api/tasks/{id}
 *
 * ─── Что уходит вместе с прогоном ──────────────────────────────────────────
 * Строка в `tasks` и всё, что на неё каскадом: `reports`, `report_shares`,
 * `chat_threads`. Документы отчёта в Mongo остаются — они лежат в другой базе,
 * без транзакции с Postgres, и удалять их вторым шагом значит завести
 * состояние «в Postgres уже нет, в Mongo ещё есть» при любом отказе между
 * шагами. Осиротевший документ невидим: на него нет ссылки ни с одного экрана,
 * а `tenant_id` в нём остаётся, поэтому чужим он не станет.
 *
 * ─── Идущий прогон удалять нельзя ──────────────────────────────────────────
 * У воркера нет способа узнать, что задачу отменили: он читает чекпоинт и
 * пишет прогресс, а строки уже нет. Обращение к пропавшей задаче он поймёт как
 * сбой базы и уйдёт в повтор. Поэтому RUNNING и QUEUED отклоняются с 409 и
 * внятным текстом, а не удаляются молча.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const { tenantId } = await requireSession();

    const outcome = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<{ status: string }>(
        `SELECT status FROM tasks WHERE id = $1`,
        [id],
      );
      if (rows.length === 0) return "missing" as const;

      const status = rows[0].status;
      if (status === "QUEUED" || status === "RUNNING") return status;

      await client.query(`DELETE FROM tasks WHERE id = $1`, [id]);
      return "deleted" as const;
    });

    // 404, а не 403: чужой прогон под RLS не находится, и подтверждать его
    // существование ответом нельзя.
    if (outcome === "missing") {
      return Response.json({ error: "прогон не найден" }, { status: 404 });
    }
    if (outcome === "QUEUED" || outcome === "RUNNING") {
      return Response.json(
        {
          error:
            outcome === "RUNNING"
              ? "прогон идёт: воркер разбирает ролик и не узнает об удалении. Дождитесь окончания или отказа"
              : "прогон стоит в очереди: воркер может взять его в любой момент. Дождитесь окончания или отказа",
        },
        { status: 409 },
      );
    }

    return Response.json({ ok: true });
  } catch (error) {
    return toResponse(error);
  }
}
