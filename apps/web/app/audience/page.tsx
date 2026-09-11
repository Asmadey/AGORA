import { AudienceRegistry } from "@/components/agora/AudienceRegistry";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listPersonaSets } from "@/lib/server/personas";

/**
 * Аудитории — единственный раздел про наборы персон.
 *
 * До 11.09.2026 их было два: здесь лежал список наборов, а в «Персонах» —
 * все персоны арендатора вперемешку плюс второй список тех же наборов
 * плашками. Удаление набора жило только во втором, то есть не в том разделе,
 * который наборам и посвящён.
 *
 * Страница только читает: выбор, удаление и счётчики — в `AudienceRegistry`.
 *
 * Число персон берётся из `persona_count`, а не из заявленного размера: набор,
 * у которого заказано 50, а сохранено 12, — это отказ генерации на половине.
 */

export const dynamic = "force-dynamic";

export default async function AudiencePage() {
  const { tenantId } = await requireSession();
  const sets = await withTenant(tenantId, (client) => listPersonaSets(client));

  return (
    <AudienceRegistry
      sets={sets.map((s) => ({
        id: s.id,
        name: s.name,
        size: s.size,
        personaCount: s.personaCount,
        seed: s.seed,
        createdAt: s.createdAt,
      }))}
    />
  );
}
