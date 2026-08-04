import Link from "next/link";

import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listPersonas, listPersonaSets } from "@/lib/server/personas";

/**
 * Раздел «Персоны» (задача #6, PRD §5.A, §9): сетка плашек → клик → карточка.
 *
 * На плашке ровно то, чем персона узнаётся в списке; всё остальное — в карточке.
 * До этой задачи страница читала MOCK_PERSONAS из lib/mock-data: выглядела
 * работающей, но к базе не обращалась, поэтому ни один пункт cdd проверить было
 * нельзя.
 *
 * Реестр наборов показан над сеткой — это половина преселекта «Создать /
 * Выбрать существующую» из критериев приёмки: набор с seed и размером виден
 * до генерации, а не после.
 */

export const dynamic = "force-dynamic";

/** Поколение по году рождения — на плашке оно информативнее возраста. */
function generation(age: number): string {
  const year = new Date().getFullYear() - age;
  if (year >= 2013) return "Альфа";
  if (year >= 1997) return "Z";
  if (year >= 1981) return "Y";
  if (year >= 1965) return "X";
  return "Бумеры";
}

/** Стабильный оттенок аватара из идентификатора: одна персона — один цвет. */
function hue(id: string): number {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export default async function PersonasPage() {
  const { tenantId } = await requireSession();

  const { personas, sets } = await withTenant(tenantId, async (client) => ({
    personas: await listPersonas(client),
    sets: await listPersonaSets(client),
  }));

  return (
    <>
      <PageHeader
        title="Персоны"
        subtitle="Цифровые двойники зрителей. Каждая персона сгенерирована как представитель сегмента из корпуса реальных респондентов — не как копия конкретного человека."
        actions={
          <Link
            href="/studies/new"
            className="rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary"
          >
            Сгенерировать набор
          </Link>
        }
      />

      <div className="p-8">
        {sets.length > 0 && (
          <div className="mb-6 space-y-1.5">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Наборы</p>
            <div className="flex flex-wrap gap-2">
              {sets.map((s) => (
                <span
                  key={s.id}
                  className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground"
                >
                  {s.name} · {s.personaCount} из {s.size}
                  {s.seed !== null && ` · seed ${s.seed}`}
                </span>
              ))}
            </div>
          </div>
        )}

        {personas.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            Персон пока нет. Сгенерируйте набор — он появится здесь.
          </p>
        ) : (
          <>
            <div className="mb-6 text-sm text-muted-foreground">{personas.length} персон</div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {personas.map((p) => {
                const demo = (p.dna as unknown as Record<string, Record<string, unknown>>)
                  ?.demographics;
                const age = Number(demo?.age ?? 0);
                const city = String(demo?.city ?? "");
                const occupation = String(
                  (p.dna as unknown as Record<string, Record<string, unknown>>)
                    ?.lifestyle_and_interests?.work_status ?? "",
                );
                const h = hue(p.id);
                return (
                  <Link
                    key={p.id}
                    href={`/personas/${p.id}`}
                    className="group rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5 transition-colors hover:border-muted-foreground/40"
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-sm font-semibold"
                        style={{
                          backgroundColor: `hsl(${h} 45% 22%)`,
                          color: `hsl(${h} 70% 78%)`,
                        }}
                      >
                        {initials(p.name)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <h2 className="truncate font-medium">{p.name}</h2>
                        {occupation && (
                          <p className="truncate text-sm text-muted-foreground">{occupation}</p>
                        )}
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-1.5">
                      {age > 0 && <Chip>{generation(age)}</Chip>}
                      {age > 0 && <Chip tone="outline">{age} лет</Chip>}
                      {city && <Chip tone="outline">{city}</Chip>}
                    </div>

                    {p.narrative && (
                      <p className="mt-4 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
                        {p.narrative}
                      </p>
                    )}

                    <p className="mt-4 text-xs text-muted-foreground">
                      Создана {new Date(p.createdAt).toLocaleDateString("ru-RU")}
                    </p>
                  </Link>
                );
              })}
            </div>
          </>
        )}
      </div>
    </>
  );
}
