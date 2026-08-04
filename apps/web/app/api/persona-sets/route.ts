import { withTenant } from "@/lib/server/db";
import { requireOwner, requireSession, toResponse } from "@/lib/server/guard";
import { createPersonaSet, listPersonaSets } from "@/lib/server/personas";

/**
 * Наборы персон (задача #6) — список и создание.
 *
 * GET  /api/persona-sets          — все наборы арендатора
 * GET  /api/persona-sets?id=<uuid> — один набор в том же формате
 * POST /api/persona-sets          — создать набор. Только owner.
 *
 * Пункт cdd «persona_set сохраняется и переиспользуется в новом прогоне»
 * держится именно на этом маршруте: преселект «Создать / Выбрать существующую»
 * читает список отсюда, а повторный прогон получает те же параметры генерации
 * и тот же seed — то есть воспроизводимый состав аудитории.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request) {
  try {
    const { tenantId } = await requireSession();
    const id = new URL(request.url).searchParams.get("id") ?? undefined;

    const personaSets = await withTenant(tenantId, async (client) => {
      return listPersonaSets(client, id);
    });
    return Response.json({ personaSets });
  } catch (error) {
    return toResponse(error);
  }
}

interface CreateBody {
  name?: string;
  size?: number;
  seed?: number | null;
  generationConfig?: Record<string, unknown>;
}

export async function POST(request: Request) {
  try {
    const { tenantId } = await requireOwner();

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "тело запроса не является корректным JSON" }, { status: 400 });
    }

    const raw = (body ?? {}) as CreateBody;
    if (typeof raw.name !== "string" || !raw.name.trim()) {
      return Response.json({ error: "требуется поле name (непустая строка)" }, { status: 400 });
    }
    // size проверяется здесь, а не только ограничением CHECK в таблице: отказ
    // базы приедет пятисоткой, а пользователю нужен внятный 400 с причиной.
    if (typeof raw.size !== "number" || !Number.isInteger(raw.size) || raw.size <= 0) {
      return Response.json({ error: "требуется поле size (целое больше нуля)" }, { status: 400 });
    }
    const seed =
      raw.seed === undefined || raw.seed === null ? null : Number(raw.seed);
    if (seed !== null && (!Number.isInteger(seed) || seed < 0)) {
      return Response.json({ error: "seed должен быть неотрицательным целым" }, { status: 400 });
    }

    const personaSet = await withTenant(tenantId, async (client) => {
      return createPersonaSet(client, raw.name!.trim(), raw.size!, raw.generationConfig ?? {}, seed);
    });
    return Response.json({ personaSet }, { status: 201 });
  } catch (error) {
    return toResponse(error);
  }
}
