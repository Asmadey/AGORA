import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { deleteRecord, listDatasets, upsertRecord } from "@/lib/server/corpus-db";

/**
 * Правка корпуса: добавление, изменение и удаление записей (этап Е).
 *
 * PUT    /api/corpus/records  — создать либо перезаписать по respondent_id
 * DELETE /api/corpus/records?id=… — удалить
 *
 * ─── Почему правка не ломает прежние исследования ──────────────────────────
 * Каждая аудитория снимает слепок корпуса в момент создания, и генератор
 * сэмплирует персон по слепку, а не по живой таблице. Поэтому правка меняет
 * будущие аудитории и не трогает прошлые — иначе набор персон, собранный
 * месяц назад, перестал бы воспроизводиться по своему seed, причём молча.
 *
 * ─── Почему PUT, а не POST ─────────────────────────────────────────────────
 * Операция идемпотентна по (датасет, respondent_id): повторная отправка той же
 * записи не создаёт вторую. Респондент с тем же идентификатором — это тот же
 * респондент, и удвоить его вес в долях значило бы исказить заземление так, что
 * заметно это стало бы только по расхождению метрики.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function PUT(request: Request) {
  try {
    const { tenantId } = await requireSession();

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "тело не является корректным JSON" }, { status: 400 });
    }

    const payload = (body ?? {}) as Record<string, unknown>;
    const datasetId = typeof payload.datasetId === "string" ? payload.datasetId : null;
    const respondentId =
      typeof payload.respondentId === "string" ? payload.respondentId.trim() : "";
    const data = payload.data;

    if (!datasetId) {
      return Response.json({ error: "не указан datasetId" }, { status: 400 });
    }
    if (!respondentId) {
      // Пустой идентификатор — не мелочь: записи различаются по нему, и запись
      // без него сливалась бы с другой такой же при следующем сохранении.
      return Response.json({ error: "не указан respondentId" }, { status: 400 });
    }
    if (typeof data !== "object" || data === null || Array.isArray(data)) {
      return Response.json(
        { error: "поле data должно быть объектом карточки респондента" },
        { status: 400 },
      );
    }

    const record = await withTenant(tenantId, async (client) => {
      const datasets = await listDatasets(client);
      if (!datasets.some((d) => d.id === datasetId)) return null;
      return upsertRecord(client, datasetId, respondentId, data as Record<string, unknown>);
    });

    if (!record) return Response.json({ error: "датасет не найден" }, { status: 404 });
    return Response.json({ record });
  } catch (error) {
    return toResponse(error);
  }
}

export async function DELETE(request: Request) {
  try {
    const { tenantId } = await requireSession();
    const id = new URL(request.url).searchParams.get("id");
    if (!id) return Response.json({ error: "не указан id записи" }, { status: 400 });

    const removed = await withTenant(tenantId, (client) => deleteRecord(client, id));
    // 404 и на чужую запись, и на несуществующую: RLS их не различает, и ответ
    // не должен различать тоже.
    if (!removed) return Response.json({ error: "запись не найдена" }, { status: 404 });
    return Response.json({ deleted: true });
  } catch (error) {
    return toResponse(error);
  }
}
