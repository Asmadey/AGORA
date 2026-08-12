import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { deleteProject, getProject, renameProject } from "@/lib/server/projects";

/**
 * Один проект: чтение, переименование, удаление.
 *
 * GET    /api/projects/{id}
 * PATCH  /api/projects/{id}   { name }
 * DELETE /api/projects/{id}
 *
 * **404, а не 403, на чужой проект.** Фильтр по арендатору стоит не в коде, а в
 * политике RLS, поэтому чужая строка просто не находится — и это тот же ответ,
 * что на несуществующий идентификатор. 403 подтвердил бы, что проект с таким
 * идентификатором есть, то есть отвечал бы на вопрос, которого не задавали.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_NAME = 200;

const NOT_FOUND = { error: "проект не найден" };

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const { tenantId } = await requireSession();
    const project = await withTenant(tenantId, (client) => getProject(client, id));
    if (!project) return Response.json(NOT_FOUND, { status: 404 });
    return Response.json({ project });
  } catch (error) {
    return toResponse(error);
  }
}

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
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

    const name = String((body as { name?: unknown })?.name ?? "").trim();
    if (!name || name.length > MAX_NAME) {
      return Response.json(
        { error: `требуется поле name (непустая строка не длиннее ${MAX_NAME})` },
        { status: 400 },
      );
    }

    const ok = await withTenant(tenantId, (client) => renameProject(client, id, name));
    if (!ok) return Response.json(NOT_FOUND, { status: 404 });
    return Response.json({ ok: true });
  } catch (error) {
    return toResponse(error);
  }
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const { tenantId } = await requireSession();
    const ok = await withTenant(tenantId, (client) => deleteProject(client, id));
    if (!ok) return Response.json(NOT_FOUND, { status: 404 });
    return Response.json({ ok: true });
  } catch (error) {
    return toResponse(error);
  }
}
