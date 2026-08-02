import { NextRequest, NextResponse } from "next/server";

import { loadDraft, saveDraft, type SessionUser } from "@/lib/server/mongo";
import { requireSession, toResponse } from "@/lib/server/guard";

/**
 * Черновики визарда (задача #7).
 *
 * requireSession() не возвращает null — она БРОСАЕТ HttpError(401). Прежняя
 * редакция проверяла `if (!session)`, то есть ветку, в которую нельзя попасть, а
 * настоящее исключение не ловила: неаутентифицированный запрос давал бы 500
 * вместо 401. Здесь, как в остальных маршрутах, ошибка приводится к ответу
 * через toResponse.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ projectId: string }> },
) {
  try {
    // Principal — плоский объект { userId, tenantId, role, email }, вложенного
    // user в нём нет. Обращение session.user.id не компилировалось.
    const { userId, tenantId } = await requireSession();
    const { projectId } = await params;
    const user: SessionUser = { userId, tenantId };

    const draft = await loadDraft(user, projectId);
    return NextResponse.json({ draft });
  } catch (error) {
    return toResponse(error);
  }
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ projectId: string }> },
) {
  try {
    const { userId, tenantId } = await requireSession();
    const { projectId } = await params;

    let body: unknown;
    try {
      body = await req.json();
    } catch {
      return NextResponse.json(
        { error: "тело запроса не является корректным JSON" },
        { status: 400 },
      );
    }
    if (typeof body !== "object" || body === null || Array.isArray(body)) {
      return NextResponse.json({ error: "черновик должен быть объектом" }, { status: 400 });
    }

    const user: SessionUser = { userId, tenantId };
    await saveDraft(user, projectId, body as Record<string, unknown>);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return toResponse(error);
  }
}