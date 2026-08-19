"use client";

import { ChevronDown, Download } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * Скачивание материалов прогона — кнопка с выпадающим списком.
 *
 * ─── Почему перенесено из тела страницы в шапку ────────────────────────────
 * Секция «Материалы» стояла в середине отчёта, между деревом JSON и сводными
 * метриками. Человек, пришедший забрать расшифровку, искал её в шапке — там, где
 * все прочие действия над прогоном, — не находил и листал отчёт целиком.
 *
 * ─── Почему меню, а не три кнопки подряд ───────────────────────────────────
 * В шапке уже пять действий. Три ссылки рядом с ними превратили бы её в восемь
 * равнозначных кнопок, среди которых «Удалить» перестаёт выделяться, — а это
 * единственное действие, которое нельзя отменить.
 *
 * ─── Ссылка на ролик ───────────────────────────────────────────────────────
 * Подписывается на час и приходит готовой из серверного компонента. Она уедет в
 * переписку и в историю браузера, и вечная ссылка на чужое видео оттуда уже не
 * отзывается.
 */
export function DownloadMenu({
  runId,
  videoUrl,
}: {
  runId: string;
  /** Подписанная ссылка на исходник или null, если ролика нет. */
  videoUrl: string | null;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // Закрытие по клику снаружи и по Esc. Без первого меню остаётся раскрытым
  // после перехода к другому действию и перекрывает содержимое отчёта.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const item =
    "block w-full px-4 py-2 text-left text-sm transition-colors hover:bg-secondary";

  return (
    <div className="relative" ref={box}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="inline-flex items-center gap-2 rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary"
      >
        <Download className="h-4 w-4" />
        Скачать
        <ChevronDown
          className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-1 min-w-[14rem] overflow-hidden rounded-md border border-hairline bg-card py-1 shadow-lg"
        >
          <a href={`/api/tasks/${runId}/transcript`} role="menuitem" className={item}>
            Расшифровка · txt
          </a>
          <a
            href={`/api/tasks/${runId}/report`}
            download={`report-${runId}.json`}
            role="menuitem"
            className={item}
          >
            Отчёт · json
          </a>
          {videoUrl && (
            <a href={videoUrl} role="menuitem" className={item}>
              Исходный ролик
            </a>
          )}
          {videoUrl && (
            <p className="border-t border-hairline px-4 pb-1 pt-2 text-xs text-slate">
              Ссылка на ролик подписана на час — по истечении откройте страницу
              заново.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
