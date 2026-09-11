"use client";

import { useEffect, useRef, useState } from "react";
import { HelpCircle } from "lucide-react";

/**
 * Кружок со знаком вопроса и объяснением рядом с заголовком.
 *
 * ─── Почему не только по наведению ────────────────────────────────────────
 * Владелец попросил подсказку «наводя на которую». Наведение оставлено, но
 * одного его мало: на сенсорном экране наводить нечем, а с клавиатуры до
 * подсказки не добраться вовсе. Поэтому панель открывают три вещи — наведение,
 * щелчок и фокус, — и закрывают Escape или щелчок мимо.
 *
 * ─── Почему панель, а не всплывающая подсказка ────────────────────────────
 * Объяснение здесь длиной в несколько абзацев. Нативный `title` показал бы его
 * одной строкой через секунду ожидания и оборвал по ширине экрана, а обычный
 * tooltip требует держать курсор на месте, пока читаешь. Панель остаётся
 * открытой, пока её не закроют.
 */
export function Hint({
  label,
  children,
}: {
  /** Что объясняем — уходит в aria-label, иначе кнопка читается как «вопрос». */
  label: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    function onClick(e: MouseEvent) {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  return (
    <span
      className="relative inline-flex align-middle"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onFocus={() => setOpen(true)}
        className="grid h-5 w-5 place-items-center rounded-full text-stone transition-colors hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
      >
        <HelpCircle className="h-[18px] w-[18px]" />
      </button>

      {open && (
        <div
          ref={box}
          role="tooltip"
          // Ширина в символах, а не в пикселях: строка длиннее ~70 знаков
          // читается заметно хуже, и на широком экране панель иначе
          // растянулась бы во всю доступную ширину.
          className="absolute left-0 top-7 z-50 max-h-[70vh] w-[min(34rem,calc(100vw-3rem))] overflow-y-auto rounded-xl border border-hairline bg-card p-5 text-left shadow-lg"
        >
          {children}
        </div>
      )}
    </span>
  );
}

/** Абзац подсказки. Вынесен, чтобы ритм был одинаковым во всех подсказках. */
export function HintText({ children }: { children: React.ReactNode }) {
  return <p className="mt-3 text-sm leading-relaxed text-slate first:mt-0">{children}</p>;
}

/** Подзаголовок внутри подсказки. */
export function HintTitle({ children }: { children: React.ReactNode }) {
  return <p className="mt-4 text-sm font-semibold text-ink first:mt-0">{children}</p>;
}
