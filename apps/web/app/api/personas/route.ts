import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { deletePersonas, listPersonas } from "@/lib/server/personas";

/**
 * Список персон арендатора (задача #6).
 *
 * GET    /api/personas              — все персоны арендатора
 * GET    /api/personas?setId=<uuid> — персоны конкретного набора
 * DELETE /api/personas              — удалить персон по списку идентификаторов
 *
 * Фильтр по набору — параметром, а не отдельным маршрутом: это одна и та же
 * выборка с дополнительным условием, и разводить её по двум эндпоинтам значит
 * дублировать проекцию строк, которая обязана совпадать.
 *
 * ─── Почему удаление пачкой, а не по одному ─────────────────────────────────
 * Реестр показывает сотни персон, и убирают их десятками. Удаление по одному
 * означало бы столько же круглых поездок по сети, а на середине списка —
 * наполовину удалённую выборку без способа понять, что именно удалилось.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request) {
  try {
    const { tenantId } = await requireSession();
    const setId = new URL(request.url).searchParams.get("setId") ?? undefined;

    const personas = await withTenant(tenantId, async (client) => {
      return listPersonas(client, setId);
    });
    return Response.json({ personas });
  } catch (error) {
    return toResponse(error);
  }
}

/** Максимум за один запрос: столько персон помещается на экране реестра. */
const MAX_DELETE = 500;

export async function DELETE(request: Request) {
  try {
    const { tenantId } = await requireSession();

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json(
        { error: "тело запроса не является корректным JSON" },
        { status: 400 },
      );
    }

    const raw = (body as { ids?: unknown })?.ids;
    if (!Array.isArray(raw) || raw.length === 0) {
      return Response.json(
        { error: "требуется поле ids — непустой список идентификаторов" },
        { status: 400 },
      );
    }
    if (raw.length > MAX_DELETE) {
      return Response.json(
        { error: `за один запрос удаляется не больше ${MAX_DELETE} персон` },
        { status: 400 },
      );
    }

    const ids = raw.filter((v): v is string => typeof v === "string" && v.length > 0);
    if (ids.length !== raw.length) {
      return Response.json(
        { error: "в ids есть значения, не являющиеся идентификаторами" },
        { status: 400 },
      );
    }

    // Чужие идентификаторы просто не находятся: RLS не покажет строку другого
    // арендатора. Отдельной проверки на владение нет намеренно — политика
    // надёжнее проверки, потому что её нельзя забыть.
    const deleted = await withTenant(tenantId, (client) => deletePersonas(client, ids));

    // Расхождение названо вслух: запрошено 10, удалено 7 — значит три уже были
    // удалены или принадлежат другой команде. Молчаливое «успех» на таком
    // ответе скрыло бы и то, и другое.
    return Response.json({ deleted, requested: ids.length });
  } catch (error) {
    return toResponse(error);
  }
}
