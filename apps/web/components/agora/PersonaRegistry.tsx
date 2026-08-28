"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { PersonaSetChips, type PersonaSetChip } from "@/components/agora/PersonaSetChips";
import { Chip } from "@/components/agora/Primitives";

/**
 * Реестр персон с выбором и удалением.
 *
 * ─── Почему целиком клиентский, включая шапку ──────────────────────────────
 * Кнопка «Удалить» обязана стоять в шапке, а
 * состояние выбора живёт в карточках. Разведённые по серверному и клиентскому
 * дереву, они потребовали бы поднимать выбор в контекст ради одной кнопки.
 * `PageHeader` — чистая разметка и сам объявлен клиентским, так что перенос
 * шапки сюда ничего не стоит.
 *
 * ─── Почему кнопка появляется, а не гаснет ─────────────────────────────────
 * Неактивная кнопка удаления в шапке — постоянное напоминание о разрушительном
 * действии там, где обычно ничего не удаляют. Появляясь только при выборе, она
 * читается как продолжение выбора, а не как всегда доступная опасность.
 */

export interface PersonaCard {
  id: string;
  name: string;
  narrative: string | null;
  createdAt: string;
  author: string | null;
  dna: Record<string, unknown>;
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

/** Оттенок аватара из идентификатора: одна персона — один цвет навсегда. */
function hue(id: string): number {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

function generation(age: number): string {
  if (age <= 27) return "Зумер";
  if (age <= 43) return "Миллениал";
  if (age <= 59) return "Поколение X";
  return "Бумер";
}

export function PersonaRegistry({
  personas,
  sets,
}: {
  personas: PersonaCard[];
  sets: PersonaSetChip[];
}) {
  const router = useRouter();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const count = selected.size;
  const ids = useMemo(() => [...selected], [selected]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/personas", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      const data = (await res.json()) as { deleted?: number; requested?: number; error?: string };
      if (!res.ok) {
        setError(data.error ?? `удаление не удалось (${res.status})`);
        return;
      }
      // Расхождение названо вслух: запросили десять, удалилось семь — значит
      // три уже были удалены. Молчаливое «готово» скрыло бы это.
      if (typeof data.deleted === "number" && data.deleted !== ids.length) {
        setError(`удалено ${data.deleted} из ${ids.length}: остальных уже не было`);
      }
      setSelected(new Set());
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Персоны"
        subtitle="Цифровые двойники зрителей. Каждая персона сгенерирована как представитель сегмента из корпуса реальных респондентов — не как копия конкретного человека."
        actions={
          <>
            {count > 0 && (
              <button
                type="button"
                onClick={() => void remove()}
                disabled={busy}
                className="inline-flex items-center gap-2 rounded-md bg-danger px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                Удалить {count}
              </button>
            )}
          </>
        }
      />

      <div className="p-8">
        {sets.length > 0 && <PersonaSetChips sets={sets} />}

        {error && (
          <p className="mb-4 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>
        )}

        {personas.length === 0 ? (
          <p className="rounded-lg border border-dashed border-hairline p-8 text-center text-sm text-slate">
            Персон пока нет. Набор собирается шагом «Аудитория» в визарде запуска
            исследования — оттуда персоны и появятся здесь.
          </p>
        ) : (
          <>
            <div className="mb-6 flex items-center gap-4 text-sm text-slate">
              <span>{personas.length} персон</span>
              {count > 0 && (
                <button
                  type="button"
                  onClick={() => setSelected(new Set())}
                  className="underline underline-offset-4 hover:text-foreground"
                >
                  снять выбор ({count})
                </button>
              )}
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {personas.map((p) => {
                const dna = p.dna as Record<string, Record<string, unknown>>;
                const demo = dna?.demographics;
                const age = Number(demo?.age ?? 0);
                const city = String(demo?.city ?? "");
                const occupation = String(dna?.lifestyle_and_interests?.work_status ?? "");
                const h = hue(p.id);
                const checked = selected.has(p.id);

                return (
                  /*
                    Карточка — контейнер, а не ссылка целиком: чекбокс внутри
                    ссылки уводил бы на страницу персоны при каждом клике по
                    нему. Ссылкой осталась область содержимого, чекбокс лежит
                    поверх неё в углу.
                  */
                  <div
                    key={p.id}
                    className={`relative rounded-lg border bg-card p-5 transition-colors ${
                      checked ? "border-ink" : "border-hairline hover:border-muted-foreground/40"
                    }`}
                  >
                    <label className="absolute right-3 top-3 z-10 cursor-pointer p-1">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggle(p.id)}
                        aria-label={`Выбрать ${p.name}`}
                        className="h-4 w-4 accent-foreground"
                      />
                    </label>

                    <Link href={`/personas/${p.id}`} className="block">
                      <div className="flex items-start gap-3 pr-8">
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
                            <p className="truncate text-sm text-slate">{occupation}</p>
                          )}
                        </div>
                      </div>

                      <div className="mt-4 flex flex-wrap gap-1.5">
                        {age > 0 && <Chip>{generation(age)}</Chip>}
                        {age > 0 && <Chip tone="outline">{age} лет</Chip>}
                        {city && <Chip tone="outline">{city}</Chip>}
                      </div>

                      {p.narrative && (
                        <p className="mt-4 line-clamp-2 text-sm leading-relaxed text-slate">
                          {p.narrative}
                        </p>
                      )}

                      <p className="mt-4 text-xs text-slate">
                        Создана {new Date(p.createdAt).toLocaleDateString("ru-RU")}
                        {/* «Создал» рядом с «Создана»: в команде из нескольких
                            человек реестр показывает сотни карточек, и понять,
                            чья это аудитория, иначе было нечем — а удалять
                            чужое страшно именно поэтому. */}
                        {p.author && ` · Создал ${p.author}`}
                      </p>
                    </Link>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </>
  );
}
