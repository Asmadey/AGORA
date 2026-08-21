import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { listDatasets, listRecords } from "@/lib/server/corpus-db";

/**
 * Корпус: список датасетов и записи выбранного (этап Е).
 *
 * GET /api/corpus                     — датасеты команды с числом записей
 * GET /api/corpus?datasetId=…&offset= — записи страницей
 *
 * ─── Почему один маршрут на два ответа ─────────────────────────────────────
 * Раздел открывается списком датасетов и сразу показывает записи первого. Два
 * маршрута дали бы два состояния загрузки на одном экране и возможность
 * показать таблицу записей от датасета, который уже не выбран.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Сколько записей отдавать за раз. Больше — урезается, а не отвергается. */
const PAGE = 50;

export async function GET(request: Request) {
  try {
    const { tenantId } = await requireSession();
    const url = new URL(request.url);
    const datasetId = url.searchParams.get("datasetId");
    const offset = Number(url.searchParams.get("offset") ?? 0);

    return await withTenant(tenantId, async (client) => {
      const datasets = await listDatasets(client);
      if (!datasetId) {
        return Response.json({ datasets, records: null });
      }

      // Чужой датасет от несуществующего не отличается: RLS не показывает ни
      // тот, ни другой, и ответ обязан быть одинаковым — иначе по нему можно
      // проверять существование чужих данных.
      if (!datasets.some((d) => d.id === datasetId)) {
        return Response.json({ error: "датасет не найден" }, { status: 404 });
      }

      const records = await listRecords(client, datasetId, {
        limit: PAGE,
        offset: Number.isFinite(offset) ? offset : 0,
      });
      return Response.json({ datasets, records });
    });
  } catch (error) {
    return toResponse(error);
  }
}
