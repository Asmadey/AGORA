import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { PersonaDnaView } from "@/components/agora/PersonaDnaView";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { getPersona } from "@/lib/server/personas";

/**
 * Полная карточка персоны (задача #6).
 *
 * Отрисовка DNA живёт в `PersonaDnaView`: те же данные показывает попап «О
 * персоне» в карточке ответа, и написанные порознь два экрана разошлись бы
 * сначала подписями, потом составом полей. Там же объяснено, почему обход идёт
 * структурой, а не перечислением полей.
 *
 * ─── Почему канонический тип, а не рукописный ──────────────────────────────
 * До этой задачи страница строилась на apps/web/lib/agora-types.ts — рукописной
 * модели, расходившейся со схемой и по именам (bigFive против big_five), и по
 * составу: в схеме communication_style содержит directness и conflict_style,
 * которых там не было, а его tone и vocabulary отсутствуют в схеме. Из 47
 * листовых полей канона карточка показывала 12.
 */

export default async function PersonaCardPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { tenantId } = await requireSession();

  const persona = await withTenant(tenantId, async (client) => getPersona(client, id));

  // Чужая персона неотличима от несуществующей: RLS не вернёт строку. Разный
  // ответ на эти два случая сам сообщал бы, что объект есть у другого арендатора.
  if (!persona) {
    notFound();
    return null;
  }

  const dna = persona.dna as unknown as Record<string, unknown>;

  return (
    <div className="mx-auto max-w-5xl p-8">
      <Link
        href="/personas"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-slate transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Все персоны
      </Link>

      <header className="mb-6">
        <h1 className="text-2xl font-semibold">{persona.name}</h1>
        <p className="mt-1 text-sm text-slate">
          Создана {new Date(persona.createdAt).toLocaleDateString("ru-RU")}
          {persona.seed !== null && ` · seed ${persona.seed}`}
        </p>
      </header>

      <PersonaDnaView dna={dna} narrative={persona.narrative} />
    </div>
  );
}
