import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { resolvePrompt, substituteVariables, extractPlaceholderNames } from "@/lib/server/prompts";

/**
 * API промпт-студии (задача #26) — dry-run (предпросмотр подстановки).
 *
 * POST /api/prompts/[key]/preview { values: Record<string, string> }
 *   Подставляет тестовые значения в активный шаблон БЕЗ вызова модели.
 *   Возвращает подставленный текст. Любой участник — это превью, а не правка.
 *
 *   Если не все переменные получили значение — 400 с перечнем недостающих,
 *   а не текст с дырой: в модель ушёл бы {{foo}}, и это неочевидно.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ key: string }> },
) {
  try {
    const { tenantId } = await requireSession();
    const { key } = await params;
    const decodedKey = decodeURIComponent(key);

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "тело запроса не является корректным JSON" }, { status: 400 });
    }

    const raw = body as { values?: Record<string, string> };
    if (!raw || typeof raw.values !== "object" || raw.values === null) {
      return Response.json({ error: "требуется поле values (объект)" }, { status: 400 });
    }

    const values = raw.values;

    const prompt = await withTenant(tenantId, async (client) => {
      return resolvePrompt(client, decodedKey);
    });

    if (!prompt) {
      return Response.json({ error: "промпт не найден" }, { status: 404 });
    }

    // Подстановка без вызова модели
    const result = substituteVariables(prompt.template, values);
    if (!result.ok) {
      return Response.json(
        { error: "недостающие значения переменных", missing: result.missing },
        { status: 400 },
      );
    }

    return Response.json({
      text: result.text,
      variables: extractPlaceholderNames(prompt.template),
      version: prompt.version,
      is_default: prompt.is_default,
    });
  } catch (error) {
    return toResponse(error);
  }
}