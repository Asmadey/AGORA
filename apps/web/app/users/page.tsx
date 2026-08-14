import { PageHeader } from "@/components/AppShell";
import { UsersManager } from "@/components/agora/UsersManager";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listMembers } from "@/lib/server/users";

/**
 * Раздел «Пользователи» (этап Ж).
 *
 * Форма заведения показывается только владельцу: участник, который может
 * добавить себе второго владельца, обходит разделение ролей целиком. Проверка
 * при этом стоит и на маршруте — скрытая форма не защита, а удобство.
 */

export const dynamic = "force-dynamic";

export default async function UsersPage() {
  const { tenantId, role } = await requireSession();
  const members = await withTenant(tenantId, (client) => listMembers(client));

  return (
    <>
      <PageHeader
        title="Пользователи"
        subtitle={`${members.length} в команде`}
      />
      <div className="p-8">
        <UsersManager members={members} isOwner={role === "owner"} />
      </div>
    </>
  );
}
