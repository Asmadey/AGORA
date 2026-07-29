import "server-only";

import { auth } from "./auth";
import { withTenant } from "./db";

/**
 * Единая точка, где решается 401 и 403 (CDD задачи #3).
 *
 * Роут не должен сам разбираться с сессией: разбираться будут по-разному, и
 * первое же расхождение станет дырой. Здесь два вызова — requireSession для
 * «нужен вход» и requireOwner для «нужны права владельца команды».
 *
 * ─── Почему роль перечитывается из базы ────────────────────────────────
 * Роль лежит в подписанном токене. Подпись доказывает, что значение выдали мы,
 * и ничего не говорит о том, что оно всё ещё верно: владелец мог перевести
 * человека в member или исключить из команды после выдачи токена, а срок жизни
 * токена — неделя. Поэтому owner-действие сверяется с team_members на месте.
 * Стоимость — один запрос в той же транзакции, которая всё равно идёт в базу.
 */

export class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "HttpError";
  }
}

export interface Principal {
  userId: string;
  tenantId: string;
  role: "owner" | "member";
  email: string;
}

/** Требует действующую сессию. Иначе 401. */
export async function requireSession(): Promise<Principal> {
  const session = await auth();
  const user = session?.user;

  if (!user?.id || !user.tenantId) {
    throw new HttpError(401, "требуется вход");
  }

  return {
    userId: user.id,
    tenantId: user.tenantId,
    role: user.role,
    email: user.email ?? "",
  };
}

/** Требует роль owner в текущей команде, подтверждённую базой. Иначе 401 или 403. */
export async function requireOwner(): Promise<Principal> {
  const principal = await requireSession();

  const actualRole = await withTenant(principal.tenantId, async (client) => {
    const { rows } = await client.query<{ membership_role: string | null }>(
      "SELECT app.membership_role($1, $2) AS membership_role",
      [principal.userId, principal.tenantId],
    );
    return rows[0]?.membership_role ?? null;
  });

  if (actualRole === null) {
    // Членство отозвано — токен ещё жив, прав уже нет.
    throw new HttpError(403, "вы больше не состоите в этой команде");
  }
  if (actualRole !== "owner") {
    throw new HttpError(403, "действие доступно только владельцу команды");
  }

  return { ...principal, role: "owner" };
}

/**
 * Превращает HttpError в ответ, всё остальное — в 500 без подробностей.
 * Текст неожиданной ошибки наружу не уходит: в нём бывает и строка подключения,
 * и фрагмент SQL. В журнал — уходит.
 */
export function toResponse(error: unknown): Response {
  if (error instanceof HttpError) {
    return Response.json({ error: error.message }, { status: error.status });
  }
  console.error("[api] необработанная ошибка:", error);
  return Response.json({ error: "внутренняя ошибка" }, { status: 500 });
}
