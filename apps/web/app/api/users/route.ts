import { withTenant } from "@/lib/server/db";
import { requireOwner, requireSession, toResponse } from "@/lib/server/guard";
import { addMember, listMembers } from "@/lib/server/users";

/**
 * Участники команды (этап Ж).
 *
 * GET  /api/users — список. Виден любому участнику: состав команды не секрет
 *                   для тех, кто в ней состоит.
 * POST /api/users — завести пользователя. Только владелец.
 *
 * ─── Про пароль ────────────────────────────────────────────────────────────
 * Пароль вводит владелец в браузере и он уходит прямо в хеш. В логи, в ответ и
 * в переписку он не попадает — §6-бис CLAUDE.md: всё, что побывало в
 * переписке, считается скомпрометированным и требует перевыпуска.
 *
 * Поэтому же здесь нет генерации пароля на сервере с показом его в ответе:
 * сгенерированный пароль пришлось бы кому-то переслать, а переслать его
 * безопасно продукт не умеет.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Ниже этого пароль не принимается. Восемь символов — минимум OWASP. */
const MIN_PASSWORD = 8;

export async function GET() {
  try {
    const { tenantId } = await requireSession();
    const members = await withTenant(tenantId, (client) => listMembers(client));
    return Response.json({ members });
  } catch (error) {
    return toResponse(error);
  }
}

export async function POST(request: Request) {
  try {
    // requireOwner, а не requireSession: заведение пользователя — владельческое
    // действие, и участник, который может добавить себе второго владельца,
    // обходит разделение ролей целиком.
    const { tenantId } = await requireOwner();

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "тело не является корректным JSON" }, { status: 400 });
    }

    const payload = (body ?? {}) as Record<string, unknown>;
    const email = typeof payload.email === "string" ? payload.email.trim().toLowerCase() : "";
    const password = typeof payload.password === "string" ? payload.password : "";
    const name = typeof payload.name === "string" && payload.name.trim() ? payload.name.trim() : null;
    const role = payload.role === "owner" ? "owner" : "member";

    if (!email.includes("@")) {
      return Response.json({ error: "нужен корректный адрес почты" }, { status: 400 });
    }
    if (password.length < MIN_PASSWORD) {
      return Response.json(
        { error: `пароль короче ${MIN_PASSWORD} символов` },
        { status: 400 },
      );
    }

    const result = await withTenant(tenantId, (client) =>
      addMember(client, { email, name, password, role }),
    );

    // `created: false` — пользователь с таким адресом уже существовал и получил
    // членство в этой команде; пароль ему НЕ менялся. Это не мелочь для
    // вызывающего: иначе владелец решит, что задал пароль, и продиктует его.
    return Response.json(result, { status: result.created ? 201 : 200 });
  } catch (error) {
    return toResponse(error);
  }
}
