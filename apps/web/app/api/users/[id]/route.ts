import { withTenant } from "@/lib/server/db";
import { requireOwner, toResponse } from "@/lib/server/guard";
import { LastOwnerError, removeMember } from "@/lib/server/users";

/**
 * Удаление участника из команды (этап Ж).
 *
 * Снимается ЧЛЕНСТВО, а не пользователь: `users` глобальна, и один человек
 * состоит в нескольких командах. Удаление записи пользователя выкинуло бы его
 * из всех сразу — то есть владелец одной команды распоряжался бы доступом в
 * чужие.
 *
 * Владелец не может удалить сам себя, пока он единственный: команда без
 * владельца — состояние, из которого нет выхода изнутри продукта.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { tenantId } = await requireOwner();
    const { id } = await params;

    const removed = await withTenant(tenantId, (client) => removeMember(client, id));
    // 404 и на чужого участника, и на несуществующего: список членства виден
    // только внутри команды, и ответ не должен подтверждать существование
    // пользователя снаружи.
    if (!removed) return Response.json({ error: "участник не найден" }, { status: 404 });
    return Response.json({ deleted: true });
  } catch (error) {
    if (error instanceof LastOwnerError) {
      // 409, а не 400: запрос корректен, ему мешает состояние команды.
      return Response.json({ error: error.message }, { status: 409 });
    }
    return toResponse(error);
  }
}
