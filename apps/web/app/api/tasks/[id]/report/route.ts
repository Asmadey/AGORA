import { requireSession, toResponse } from "@/lib/server/guard";
import { loadReport } from "@/lib/server/reports";

/**
 * Отчёт прогона (задача #21).
 *
 * GET /api/tasks/{id}/report — агрегат, синтез, точки риска, дисклеймер.
 *
 * Карточки персон сюда НЕ входят: на 500 персонах с перекрытием 3 они весят
 * 2.1 МБ против 178 КБ самого отчёта. Их отдаёт соседний маршрут
 * /api/tasks/{id}/report/personas страницами — см. lib/server/reports.ts.
 *
 * ─── Почему 404, а не 403, на чужой прогон ─────────────────────────────────
 * Фильтр по tenant_id стоит в самом запросе, поэтому чужой отчёт не находится —
 * и ответ получается тот же, что на несуществующий идентификатор. Это не
 * упрощение, а нужное поведение: 403 подтвердил бы, что прогон с таким
 * идентификатором существует, то есть отдал бы факт наличия чужих данных.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { tenantId, userId } = await requireSession();
    const { id } = await params;

    const envelope = await loadReport({ tenantId, userId }, id);
    if (!envelope) {
      return Response.json(
        { error: "отчёт не найден: прогон не существует, не завершён или чужой" },
        { status: 404 },
      );
    }

    return Response.json({
      taskId: envelope.taskId,
      audienceSize: envelope.audienceSize,
      updatedAt: envelope.updatedAt,
      ...envelope.report,
    });
  } catch (error) {
    return toResponse(error);
  }
}
