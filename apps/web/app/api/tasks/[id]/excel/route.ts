import {
  EXCEL_MEDIA_TYPE,
  excelDisposition,
  excelUpstreamError,
} from "@/lib/excel-download";
import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";

/**
 * Выгрузка ответов прогона книгой Excel.
 *
 * GET /api/tasks/{id}/excel — файл в форме полевого файла заказчика: две
 * строки шапки (блок, вопрос), параметры аудитории слева, строка на персону.
 *
 * ─── Что делает веб, а что служба агента ───────────────────────────────────
 * Веб отвечает за ДОСТУП и за ИМЯ: сессия, принадлежность прогона арендатору,
 * готовность отчёта, заголовки ответа. Агент отвечает за КНИГУ: развёртку
 * анкеты в колонки, сведение повторов, отсев по правилам QA.
 *
 * Граница проходит здесь не по вкусу, а по §6: книгу собирает `openpyxl`, а
 * нативные npm-модули в `apps/web` запрещены. Ровно та же модель, что у чата
 * (#28), и по той же причине — вторая реализация формы на TypeScript
 * разошлась бы с первой молча.
 *
 * ─── Почему поток, а не подписанная ссылка ─────────────────────────────────
 * Книга собирается из уже сохранённых артефактов за доли секунды и
 * воспроизводима в любой момент. Складывать её в S3 значило бы завести
 * отдельный жизненный цикл объекта (кто и когда удалит), состояние «файл
 * готовится» в интерфейсе и копию, которая разойдётся с отчётом при первом же
 * пересчёте. Расшифровка и отчёт отдаются тем же способом — потоком с
 * `Content-Disposition`.
 *
 * ─── Почему 404, а не 403, на чужой прогон ─────────────────────────────────
 * То же, что у соседнего маршрута отчёта: фильтр по арендатору стоит в самом
 * запросе, и 403 подтвердил бы, что прогон с таким идентификатором есть.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Адрес службы агента во внутренней сети compose. */
const AGENT_API_URL = process.env.AGENT_API_URL || "http://agent-api:8001";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id: runId } = await params;
    const { tenantId } = await requireSession();

    const guard = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<{ status: string }>(
        "SELECT status FROM tasks WHERE id = $1::uuid",
        [runId],
      );
      const task = rows[0];
      if (!task) return { error: "прогон не найден", status: 404 } as const;
      if (task.status !== "REPORT_READY") {
        // Книга по незавершённому прогону собралась бы из одной шапки и
        // выглядела бы как потерянные данные, а не как рано нажатая кнопка.
        return {
          error: "исследование ещё не завершено — выгружать пока нечего",
          status: 409,
        } as const;
      }
      return { ok: true } as const;
    });

    if ("error" in guard) {
      return Response.json({ error: guard.error }, { status: guard.status });
    }

    const upstream = await fetch(`${AGENT_API_URL}/api/export/excel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: tenantId, task_id: runId }),
    });

    if (!upstream.ok || !upstream.body) {
      const detail = await upstream.text().catch(() => "");
      return Response.json(
        { error: excelUpstreamError(upstream.status, detail) },
        { status: upstream.status === 404 ? 404 : 502 },
      );
    }

    // Тело отдаётся как есть: книга приезжает готовыми байтами, и разбирать её
    // в вебе нечем и незачем.
    return new Response(upstream.body, {
      headers: {
        "Content-Type": EXCEL_MEDIA_TYPE,
        "Content-Disposition": excelDisposition(runId),
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return toResponse(error);
  }
}
