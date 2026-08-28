import { PersonaRegistry } from "@/components/agora/PersonaRegistry";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listPersonas, listPersonaSets } from "@/lib/server/personas";

/**
 * Реестр персон (задача #6).
 *
 * Страница только читает данные: выбор, удаление и шапка живут в
 * `PersonaRegistry`. Кнопка «Удалить» обязана стоять в шапке, а состояние
 * выбора — в карточках; разведённые по серверному и клиентскому дереву, они
 * потребовали бы контекста ради одной кнопки.
 *
 * Кнопки «Сгенерировать набор» здесь больше нет (решение владельца,
 * 26.08.2026): она была обычной ссылкой в визард, а набор собирается там же,
 * шагом «Аудитория».
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
