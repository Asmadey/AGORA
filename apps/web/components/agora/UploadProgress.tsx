"use client";

import { FileVideo, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { uploadPercent, uploadProgressLabel, type UploadState } from "@/lib/upload";

/**
 * Полоса загрузки ролика в S3.
 *
 * ─── Почему полоса, а не спиннер ───────────────────────────────────────────
 * Ролик весит до 700 МБ, заливка идёт минуты. Спиннер сообщает «что-то
 * происходит» и не отличается от повисшего запроса; полоса отвечает на
 * единственный вопрос, который в этот момент задают, — сколько ещё ждать.
 *
 * ─── Неопределённая полоса — отдельное состояние ───────────────────────────
 * Когда размер неизвестен (`lengthComputable` ложно), процент не показывается
 * вовсе, а полоса бежит. Нарисовать в этом случае ноль значило бы утверждать,
 * что не ушло ничего.
 */
export function UploadProgress({
  name,
  state,
  onCancel,
  className,
}: {
  name: string;
  state: UploadState;
  onCancel?: () => void;
  className?: string;
}) {
  const pct = uploadPercent(state);
  const failed = state.phase === "failed";

  return (
    <div
      className={cn(
        "rounded-lg border px-4 py-3",
        failed ? "border-danger/30 bg-danger-soft/50" : "border-hairline bg-surface",
        className,
      )}
    >
      <div className="flex items-center gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-canvas text-slate">
          <FileVideo className="h-4 w-4" />
        </span>

        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{name}</span>
          <span className={cn("block text-xs", failed ? "text-danger" : "text-slate")}>
            {uploadProgressLabel(state)}
          </span>
        </span>

        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            aria-label={`Убрать файл ${name}`}
            title="Убрать файл"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-slate transition-colors hover:bg-canvas hover:text-ink"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {!failed && state.phase !== "done" && (
        <div
          className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-hairline"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          // Отсутствие aria-valuenow — это и есть «неопределённо» для
          // скринридера; ноль он прочитал бы как «не начиналось».
          aria-valuenow={pct ?? undefined}
          aria-label={`Загрузка файла ${name}`}
        >
          <div
            className={cn(
              "h-full rounded-full bg-ink transition-[width] duration-200",
              pct === null && "w-1/3 animate-pulse",
            )}
            style={pct === null ? undefined : { width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}
