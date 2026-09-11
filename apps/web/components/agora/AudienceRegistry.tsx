"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowRight, Loader2, Trash2, UsersRound } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { EmptyState } from "@/components/agora/States";

/**
 * Раздел «Аудитории»: наборы персон, выбор и удаление.
 *
 * ─── Почему разделов стало один вместо двух ───────────────────────────────
 * `/audience` показывал НАБОРЫ, `/personas` — всех персон арендатора
 * вперемешку плюс `PersonaSetChips`, то есть второй список тех же наборов.
 *
 * Список наборов жил в двух местах, а удалить набор можно было только из
 * плашек внутри «Персон» — то есть не в том разделе, который наборам и
 * посвящён. «Аудитории» показывали наборы и не давали с ними ничего сделать.
 *
 * Плоский реестр отвечал не на тот вопрос. Перед запуском спрашивают «на ком я
 * буду проверять ролик», а не «покажи всех персон за всё время»: 484 плашки
 * подряд не просматривают. Ответ на нужный вопрос даёт страница набора.
 *
 * ─── Почему клиентский целиком ────────────────────────────────────────────
 * Тот же довод, что у `PersonaRegistry`: кнопка «Удалить» стоит в шапке, а
 * выбор живёт в карточках. Разведённые по серверному и клиентскому дереву, они
 * потребовали бы контекста ради одной кнопки.
 */

export interface AudienceCard {
  id: string;
  name: string;
  size: number;
  personaCount: number;
  seed: number | null;
  createdAt: string;
}

/** Набор, который не удалился: на нём уже считался прогон. */
interface Blocked {
  id: string;
  name: string;
  runs: number;
}

export function AudienceRegistry({ sets }: { sets: AudienceCard[] }) {
  const router = useRouter();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<Blocked[]>([]);

  const count = selected.size;
  const personaTotal = useMemo(
    () => sets.reduce((sum, s) => sum + s.personaCount, 0),
    [sets],
  );

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function remove() {
    const ids = [...selected];
    if (ids.length === 0) return;
    setBusy(true);
    setError(null);
    setBlocked([]);
    try {
      const res = await fetch("/api/audience", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      const data = (await res.json()) as {
        error?: string;
        deleted?: number;
        blocked?: Blocked[];
      };
      if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);

      // Отказ по занятым наборам — не ошибка запроса, а результат: удалить
      // набор, на котором считался отчёт, значит оставить отчёт без состава
      // аудитории. Молчание здесь читалось бы как «кнопка не работает».
      if (data.blocked?.length) setBlocked(data.blocked);

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
        title="Аудитории"
        subtitle="Наборы синтетических персон. Каждый набор заземлён на корпус из 165 реальных респондентов: доли по возрасту, гео и полу берутся оттуда, а не задаются на глаз."
        actions={
          count > 0 && (
            <button
              type="button"
              onClick={() => void remove()}
              disabled={busy}
              className="inline-flex items-center gap-2 rounded-md bg-danger px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Удалить {count}
            </button>
          )
        }
      />

      <div className="space-y-6 p-8">
        <div className="flex flex-wrap gap-3">
          <Counter label="Создано аудиторий" value={sets.length} />
          <Counter label="Создано персон" value={personaTotal} />
        </div>

        {error && (
          <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>
        )}

        {blocked.length > 0 && (
          <div className="rounded-md border border-warning/30 bg-warning-soft/60 px-3 py-2 text-sm">
            <p className="font-medium">Не удалены — на них уже считались прогоны:</p>
            <ul className="mt-1 space-y-0.5 text-xs">
              {blocked.map((b) => (
                <li key={b.id}>
                  {b.name} — {b.runs} прогон(ов)
                </li>
              ))}
            </ul>
          </div>
        )}

        {sets.length === 0 ? (
          <EmptyState
            icon={<UsersRound className="h-5 w-5" />}
            title="Аудиторий пока нет"
            description="Аудитория нужна для запуска исследования и создаётся вместе с ним — шагом «Аудитория» в визарде запуска."
            action={{ href: "/studies/new", label: "Открыть визард запуска" }}
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {sets.map((s) => {
              const incomplete = s.personaCount < s.size;
              const picked = selected.has(s.id);
              return (
                // flex-col + mt-auto на подвале: без этого предупреждение о
                // неполном наборе сдвигает дату и ссылку вниз, и в сетке они
                // стоят на разной высоте.
                <div
                  key={s.id}
                  className={`flex flex-col rounded-xl border bg-card p-5 transition-colors ${
                    picked ? "border-ink" : "border-hairline"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={picked}
                      onChange={() => toggle(s.id)}
                      aria-label={`Выбрать «${s.name}»`}
                      className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-ink"
                    />
                    <h2 className="min-w-0 flex-1 truncate font-medium">{s.name}</h2>
                  </div>

                  <div className="mt-4 flex flex-wrap items-center gap-1.5">
                    {/* Просто число: «12 из 12» отвечает на вопрос, которого не
                        задавали, и заставляет вычитать. Неполнота набора
                        остаётся отдельной подписью ниже. */}
                    <Chip tone={incomplete ? "outline" : "muted"}>{s.personaCount} персон</Chip>
                    {s.seed !== null && <Chip tone="outline">seed {s.seed}</Chip>}
                  </div>

                  {incomplete && (
                    <p className="mt-3 text-xs leading-relaxed text-warning">
                      Заполнена не полностью: заказано {s.size}, генерация оборвалась
                      или была остановлена.
                    </p>
                  )}

                  <div className="mt-4 flex items-center justify-between gap-2 pt-1 mt-auto">
                    <span className="text-xs text-slate">
                      {new Date(s.createdAt).toLocaleDateString("ru-RU")}
                    </span>
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/personas/sets/${s.id}`}
                        className="text-xs text-slate underline underline-offset-4 transition-colors hover:text-ink"
                      >
                        Посмотреть персоны
                      </Link>
                      <Link
                        href={`/personas/sets/${s.id}`}
                        aria-label={`Открыть «${s.name}»`}
                        className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-hairline text-slate transition-colors hover:border-ink hover:text-ink"
                      >
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </div>
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

function Counter({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-hairline bg-card px-5 py-4">
      <div className="text-2xl font-medium tabular-nums">{value}</div>
      <div className="mt-0.5 text-xs text-slate">{label}</div>
    </div>
  );
}
