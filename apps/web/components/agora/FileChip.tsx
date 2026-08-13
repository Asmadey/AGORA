"use client";

import { FileVideo, FileText, Loader2, X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Плашка выбранного файла: имя, размер, крестик.
 *
 * ─── Зачем она нужна ───────────────────────────────────────────────────────
 * Прежде выбранный ролик нигде не отображался. Пользователь нажимал «выберите
 * файл», диалог закрывался, зона загрузки оставалась ровно такой же — и
 * единственным признаком, что файл вообще принят, был индикатор загрузки,
 * исчезавший через несколько секунд. Отличить «файл выбран» от «диалог закрыли
 * по Esc» было нечем, и естественная реакция — выбрать файл ещё раз.
 *
 * Размер показывается не для красоты: 700 МБ — предел загрузки, и увидеть вес
 * ролика надо до того, как заливка упрётся в лимит.
 *
 * ─── Что делает крестик ────────────────────────────────────────────────────
 * Отвязывает файл от прогона, а не удаляет объект из хранилища. Объект в S3
 * остаётся: маршрута удаления у нас нет, а притворяться, что удалили, нельзя.
 * Сирота в бакете стоит денег за хранение, но молчаливая ложь про удаление
 * стоила бы доверия к остальным сообщениям интерфейса.
 */

/** Человеческий размер. Двоичные килобайты — файловые менеджеры считают так же. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} Б`;
  const units = ["КБ", "МБ", "ГБ"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  // Один знак после запятой до 100 и ни одного после: «734 МБ» читается быстрее,
  // чем «734.2 МБ», а на десятых при таком размере ничего не держится.
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

export function FileChip({
  name,
  size,
  kind = "file",
  busy = false,
  hint,
  onRemove,
  className,
}: {
  name: string;
  /** Байты. `null` — размер неизвестен (например, восстановлено из черновика). */
  size?: number | null;
  kind?: "video" | "file";
  busy?: boolean;
  hint?: string;
  onRemove: () => void;
  className?: string;
}) {
  const Icon = kind === "video" ? FileVideo : FileText;

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border border-hairline bg-surface px-4 py-3",
        className,
      )}
    >
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-canvas text-slate">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
      </span>

      <span className="min-w-0 flex-1">
        {/* Имя обрезается с конца строки, а не многоточием посередине: у видео
            различающая часть обычно в начале («s01e04_final_v3.mp4»). */}
        <span className="block truncate text-sm font-medium">{name}</span>
        <span className="block text-xs text-slate">
          {busy ? "Загружается…" : hint ?? (size == null ? "размер неизвестен" : formatBytes(size))}
        </span>
      </span>

      <button
        type="button"
        onClick={onRemove}
        disabled={busy}
        aria-label={`Убрать файл ${name}`}
        title="Убрать файл"
        className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-slate transition-colors hover:bg-canvas hover:text-ink disabled:opacity-40"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
