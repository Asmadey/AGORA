import Link from "next/link";
import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { MOCK_PERSONAS } from "@/lib/mock-data";

/**
 * Раздел «Персоны» (PRD §5.A, §9): сетка плашек → клик → полная карточка.
 * На плашке ровно то, что нужно, чтобы узнать персону в списке; всё остальное —
 * внутри карточки.
 */
export default function PersonasPage() {
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
        <div className="mb-6 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>Набор «Ландыши, базовая аудитория»</span>
          <span className="text-border">·</span>
          <span>{MOCK_PERSONAS.length} персон</span>
          <span className="text-border">·</span>
          <span>seed 481502</span>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {MOCK_PERSONAS.map((p) => (
            <Link
              key={p.id}
              href={`/personas/${p.id}`}
              className="group rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5 transition-colors hover:border-muted-foreground/40"
            >
              <div className="flex items-start gap-3">
                <div
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-sm font-semibold"
                  style={{
                    backgroundColor: `hsl(${p.avatarHue} 45% 22%)`,
                    color: `hsl(${p.avatarHue} 70% 78%)`,
                  }}
                >
                  {p.name.split(" ").map((w) => w[0]).join("")}
                </div>
                <div className="min-w-0 flex-1">
                  <h2 className="truncate font-medium">{p.name}</h2>
                  <p className="truncate text-sm text-muted-foreground">{p.jobTitle}</p>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-1.5">
                <Chip>{p.generation}</Chip>
                <Chip tone="outline">{p.dna.demographics.age} лет</Chip>
                <Chip tone="outline">{p.location}</Chip>
              </div>

              <p className="mt-4 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
                {p.narrative}
              </p>

              <p className="mt-4 text-xs text-muted-foreground">Создана {p.createdAt}</p>
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}
