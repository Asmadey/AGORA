import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { Chip } from "@/components/agora/Primitives";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { getPersona } from "@/lib/server/personas";
import { categoryLabel, fieldLabel, SCALE_1_5 } from "@/lib/persona-dna-labels";

/**
 * Полная карточка персоны (задача #6).
 *
 * ─── Почему обход структурой, а не перечисление полей ──────────────────────
 * Требование cdd: «присутствует КАЖДОЕ непустое поле DNA — ни одно поле не
 * потеряно при рендере». Перечисленный вручную список это требование не
 * удерживает: добавили поле в canonical JSON Schema — карточка про него не
 * знает, и заметить это можно только глазами.
 *
 * Здесь карточка обходит фактический объект DNA. Новое поле появляется на
 * экране само; словарь подписей влияет лишь на то, будет ли у него русское
 * название или имя из схемы.
 *
 * ─── Почему канонический тип, а не рукописный ──────────────────────────────
 * До этой задачи страница строилась на apps/web/lib/agora-types.ts — рукописной
 * модели, расходившейся со схемой и по именам (bigFive против big_five), и по
 * составу: в схеме communication_style содержит directness и conflict_style,
 * которых там не было, а его tone и vocabulary отсутствуют в схеме. Из 47
 * листовых полей канона карточка показывала 12.
 */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5">
      <h2 className="text-sm font-semibold">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** Шкала 1–5: число без максимума не читается. */
function Scale({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="flex gap-0.5" aria-hidden>
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className={`h-1.5 w-4 rounded-sm ${i <= value ? "bg-foreground/70" : "bg-border"}`}
          />
        ))}
      </span>
      <span className="text-xs text-muted-foreground">{value} из 5</span>
    </span>
  );
}

function renderValue(key: string, value: unknown) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground">—</span>;
    return (
      <span className="flex flex-wrap gap-1">
        {value.map((v, i) => (
          <Chip key={`${String(v)}-${i}`} tone="outline">
            {String(v)}
          </Chip>
        ))}
      </span>
    );
  }
  if (typeof value === "number" && SCALE_1_5.has(key)) return <Scale value={value} />;
  if (value === null || value === undefined || value === "") {
    return <span className="text-muted-foreground">—</span>;
  }
  return <span>{String(value)}</span>;
}

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
  const categories = Object.entries(dna).filter(
    ([, v]) => v !== null && typeof v === "object" && !Array.isArray(v),
  ) as [string, Record<string, unknown>][];

  return (
    <div className="mx-auto max-w-5xl p-8">
      <Link
        href="/personas"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Все персоны
      </Link>

      <header className="mb-6">
        <h1 className="text-2xl font-semibold">{persona.name}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Создана {new Date(persona.createdAt).toLocaleDateString("ru-RU")}
          {persona.seed !== null && ` · seed ${persona.seed}`}
        </p>
      </header>

      {persona.narrative && (
        <section className="mb-6 rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5">
          <h2 className="text-sm font-semibold">Описание</h2>
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
            {persona.narrative}
          </p>
        </section>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {categories.map(([category, fields]) => (
          <Section key={category} title={categoryLabel(category)}>
            <dl className="space-y-2 text-sm">
              {Object.entries(fields).map(([key, value]) => (
                <div key={key} className="flex flex-wrap items-baseline gap-x-2">
                  <dt className="text-muted-foreground">{fieldLabel(key)}:</dt>
                  <dd>{renderValue(key, value)}</dd>
                </div>
              ))}
            </dl>
          </Section>
        ))}
      </div>
    </div>
  );
}
