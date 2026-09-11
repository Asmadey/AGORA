"use client";

import { useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";

/**
 * Критерии генерации набора — свёрнутым списком.
 *
 * ─── Почему свёрнуто по умолчанию ─────────────────────────────────────────
 * Их читают в одном случае: когда набор нужно воспроизвести или объяснить
 * перекос в заземлении. В остальное время это девять строк параметров между
 * заголовком и составом набора — то есть между вопросом «на ком я проверяю» и
 * ответом на него.
 *
 * ─── Почему seed первым ───────────────────────────────────────────────────
 * Из всех параметров он единственный отвечает за воспроизводимость целиком:
 * те же критерии с другим seed дают другой набор. Остальное — условия отбора,
 * и они читаются после того, как понятно, о каком прогоне речь.
 *
 * Значения показываются как есть, а не пересказом: по ним набор
 * воспроизводится, и переписывание своими словами — лишний повод разойтись с
 * тем, что реально ушло в генератор.
 */
export function GenerationCriteria({
  config,
  seed,
}: {
  config: Record<string, unknown>;
  seed: number | null;
}) {
  const [open, setOpen] = useState(false);

  const entries = useMemo(() => {
    const rest = Object.entries(config).filter(([k]) => k !== "seed");
    const head: [string, unknown][] = seed !== null ? [["seed", seed]] : [];
    // Если seed лежит и в конфиге, и отдельной колонкой — берём колонку: она
    // и есть то, чем набор воспроизводится.
    if (seed === null && "seed" in config) head.push(["seed", config.seed]);
    return [...head, ...rest];
  }, [config, seed]);

  if (entries.length === 0) return null;

  return (
    <section className="rounded-xl border border-hairline bg-card p-5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 text-left"
      >
        <ChevronRight
          className={`h-4 w-4 shrink-0 text-slate transition-transform ${open ? "rotate-90" : ""}`}
        />
        <span className="cursor-pointer text-sm font-semibold">Критерии генерации</span>
        <span className="ml-auto text-xs text-slate">
          {open ? "свернуть" : "показать"}
        </span>
      </button>

      {open && (
        <>
          <p className="mt-2 text-xs text-slate">
            Тот же набор с тем же seed воспроизводится по этим параметрам
          </p>
          <dl className="mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {entries.map(([key, value]) => (
              <div key={key} className="flex justify-between gap-3 text-sm">
                <dt className="text-slate">{key}</dt>
                <dd className="text-right">
                  {Array.isArray(value) ? value.join(", ") : String(value ?? "—")}
                </dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </section>
  );
}
