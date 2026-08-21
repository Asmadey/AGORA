import { PersonaRegistry } from "@/components/agora/PersonaRegistry";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listPersonas, listPersonaSets } from "@/lib/server/personas";

/**
 * Реестр персон (задача #6).
 *
 * Страница только читает данные: выбор, удаление и шапка живут в
 * `PersonaRegistry`. Кнопка «Удалить» обязана стоять рядом с «Сгенерировать
 * набор», а состояние выбора — в карточках; разведённые по серверному и
 * клиентскому дереву, они потребовали бы контекста ради одной кнопки.
 */

export const dynamic = "force-dynamic";

export default async function PersonasPage() {
  const { tenantId } = await requireSession();

  const { personas, sets } = await withTenant(tenantId, async (client) => ({
    personas: await listPersonas(client),
    sets: await listPersonaSets(client),
  }));

  return (
    <PersonaRegistry
      personas={personas.map((p) => ({
        id: p.id,
        name: p.name,
        narrative: p.narrative,
        createdAt: p.createdAt,
        author: p.author,
        dna: p.dna as unknown as Record<string, unknown>,
      }))}
      sets={sets.map((s) => ({
        id: s.id,
        name: s.name,
        size: s.size,
        personaCount: s.personaCount,
        seed: s.seed,
      }))}
    />
  );
}
