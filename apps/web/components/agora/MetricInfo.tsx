"use client";

import { useEffect, useState } from "react";
import { Info, X } from "lucide-react";

/**
 * «Откуда это число» — попап у показателя.
 *
 * ─── Что было ─────────────────────────────────────────────────────────────
 * Раскрывающийся `<details>` внутри карточки. Он работал, но раздувал карточку
 * при раскрытии и уезжал вниз вместе с ней: шесть карточек в ряд, у каждой своё
 * раскрытие, и высота ряда прыгала. Владелец попросил заменить его попапом —
 * таким же, как «О персоне».
 *
 * ─── Цена, которую пришлось возместить ────────────────────────────────────
 * У прежнего `<details>` было записанное обоснование: последний шаг цепочки —
 * «нажимаете таймкод, плеер перематывается туда», а плеер стоит на этой же
 * странице выше. Диалог перекрывает его собой, и нажавший таймкод увидел бы
 * тёмную шторку вместо перемотки — то есть ровно тот шаг, ради которого вся
 * цепочка и строится, пропал бы.
 *
 * Поэтому попап ЗАКРЫВАЕТСЯ, когда внутри нажали таймкод: обработчик стоит на
 * содержимом и срабатывает на любой ссылке вида `#t=…`. Перемотка после этого
 * видна, и цепочка «число → ответы → материал» остаётся целой.
 */
export function MetricInfo({
  label,
  children,
}: {
  /** Название показателя — уходит в aria-label и в заголовок попапа. */
  label: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`Откуда число: ${label}`}
        className="inline-flex shrink-0 items-center gap-1 rounded-md border border-hairline px-1.5 py-0.5 text-xs text-slate transition-colors hover:border-hairline-strong hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
      >
        <Info className="h-3.5 w-3.5" />
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          onClick={() => setOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label={`Откуда число: ${label}`}
        >
          <div
            className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-hairline bg-background p-6 text-left"
            onClick={(e) => {
              e.stopPropagation();
              // Нажали таймкод — попап уходит, чтобы перемотка была видна.
              // Проверяем именно ссылку на момент, а не любой клик: закрывать
              // попап на попытку выделить текст было бы хуже, чем не закрывать.
              const link = (e.target as HTMLElement).closest?.("a[href^='#t=']");
              if (link) setOpen(false);
            }}
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <h2 className="min-w-0 text-lg font-semibold">{label}</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="shrink-0 rounded-md p-1 text-slate transition-colors hover:bg-secondary hover:text-foreground"
                aria-label="Закрыть"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {children}
          </div>
        </div>
      )}
    </>
  );
}
