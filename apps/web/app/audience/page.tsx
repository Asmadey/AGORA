import Link from "next/link";
import { UsersRound } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { EmptyState } from "@/components/agora/States";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listPersonaSets } from "@/lib/server/personas";
import { AudienceBuilder } from "./AudienceBuilder";

/**
 * Наборы аудитории.
 *
 * Экран показывает то же, что лежит в таблице `persona_sets`, — и это правка,
 * а не оформление. Прежняя версия генерировала набор через `/api/audience`
 * (то есть в базу он попадал), но список читала из localforage. Две копии
 * расходились при первом же входе с другой машины: база знала о наборах,
 * которых экран не показывал.
 *
 * Число персон берётся из `persona_count`, а не из заявленного размера:
 * набор, у которого заказано 50, а сохранено 12, — это отказ генерации на
 * половине, и увидеть его надо здесь, а не в отчёте по прогону.
 */

export const dynamic = "force-dynamic";

export default async function AudiencePage() {
  const { tenantId } = await requireSession();
  const sets = await withTenant(tenantId, (client) => listPersonaSets(client));

  return (
    <>
      <PageHeader
        title="Аудитории"
        subtitle="Наборы синтетических персон. Каждый набор заземлён на корпус из 165 реальных респондентов: доли по возрасту, гео и полу берутся оттуда, а не задаются на глаз."
      />

      <div className="space-y-6 p-8">
        <AudienceBuilder />

        {sets.length === 0 ? (
          <EmptyState
            icon={<UsersRound className="h-5 w-5" />}
            title="Наборов пока нет"
            description="Набор персон нужен для запуска исследования. Сгенерируйте первый — или создайте его прямо в визарде запуска, шагом «Аудитория»."
            action={{ href: "/studies/new", label: "Открыть визард запуска" }}
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {sets.map((s) => {
              const incomplete = s.personaCount < s.size;
              return (
                <div
                  key={s.id}
                  className="rounded-xl border border-hairline bg-card p-5"
                >
                  <h2 className="truncate font-medium">{s.name}</h2>

                  <div className="mt-4 flex flex-wrap items-center gap-1.5">
                    <Chip tone={incomplete ? "outline" : "muted"}>
                      {s.personaCount} из {s.size} персон
                    </Chip>
                    {s.seed !== null && <Chip tone="outline">seed {s.seed}</Chip>}
                  </div>

                  {/* Неполный набор назван прямо. Молча показанное «12» вместо
                      «12 из 50» читается как заказанный размер, и прогон на нём
                      выглядит нормальным до самого отчёта. */}
                  {incomplete && (
                    <p className="mt-3 text-xs leading-relaxed text-amber-200/80">
                      Набор заполнен не полностью: генерация оборвалась или была
                      остановлена.
                    </p>
                  )}

                  <div className="mt-4 flex items-center justify-between gap-2">
                    <span className="text-xs text-muted-foreground">
                      {new Date(s.createdAt).toLocaleDateString("ru-RU")}
                    </span>
                    <Link
                      href={`/personas/sets/${s.id}`}
                      className="text-xs text-slate underline underline-offset-4 transition-colors hover:text-ink"
                    >
                      Посмотреть персон
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
