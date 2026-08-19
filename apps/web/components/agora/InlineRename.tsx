"use client";

import { Check, Pencil, X } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

/**
 * Правка названия на месте: карандаш, поле, крестик и галочка.
 *
 * ─── Почему не отдельная секция «Переименовать» ────────────────────────────
 * У проекта она стояла внизу страницы, под списком прогонов и рядом с
 * удалением. Чтобы поправить название, приходилось пролистать весь список и
 * найти форму там, где ищут опасные действия. Правка имени — не опасное
 * действие, и место ей рядом с именем.
 *
 * ─── Почему две кнопки, а не одна ──────────────────────────────────────────
 * Отмена нужна отдельной кнопкой: Esc знают не все, а клик мимо поля в форме,
 * которая сохраняет по Enter, легко теряет правку. Цвета разведены намеренно —
 * зелёная галочка и красный крестик читаются без подписи.
 *
 * ─── Почему один компонент на проект и исследование ────────────────────────
 * Владелец попросил у исследований «такой же механизм, как у проектов». Копия
 * разошлась бы с оригиналом на первой же правке — и разошлась бы молча, потому
 * что оба экрана рядом никто не держит открытыми.
 */
export function InlineRename({
  id,
  name,
  action,
  label,
  required = true,
  className,
  inputClassName,
}: {
  id: string;
  /** Что показывать, когда не правим. Может отличаться от значения в поле. */
  name: string;
  /** Серверное действие. Получает поля `id` и `name`. */
  action: (formData: FormData) => void;
  /** Для подписи кнопки и поля — они читаются вслух программой чтения экрана. */
  label: string;
  /**
   * Обязательно ли значение. У проекта — да: проект без имени неотличим от
   * соседнего. У исследования — нет: пустое означает «вернуть имя файла».
   */
  required?: boolean;
  className?: string;
  inputClassName?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);

  if (!editing) {
    return (
      <span className={cn("inline-flex items-center gap-2", className)}>
        {name}
        <button
          type="button"
          onClick={() => {
            // Значение берётся из пропса, а не из прошлой правки: между
            // открытиями имя могло смениться на другой вкладке.
            setValue(name);
            setEditing(true);
          }}
          aria-label={`Переименовать: ${label}`}
          className="text-slate transition-colors hover:text-foreground"
        >
          <Pencil className="h-4 w-4" />
        </button>
      </span>
    );
  }

  return (
    <form
      action={(formData) => {
        action(formData);
        setEditing(false);
      }}
      className={cn("inline-flex items-center gap-2", className)}
    >
      <input type="hidden" name="id" value={id} />
      <input
        name="name"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        required={required}
        maxLength={200}
        autoFocus
        aria-label={label}
        // Esc отменяет — но кнопка отмены всё равно есть: клавишу знают не все.
        onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
        className={cn(
          "min-w-0 rounded-md border border-hairline bg-background px-2 py-1 outline-none transition-colors focus:border-muted-foreground/60",
          inputClassName ?? "text-2xl",
        )}
      />
      <button
        type="button"
        onClick={() => setEditing(false)}
        aria-label="Отменить переименование"
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-danger text-white",
          "transition-opacity hover:opacity-90",
        )}
      >
        <X className="h-4 w-4" />
      </button>
      <button
        type="submit"
        aria-label="Сохранить название"
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-success text-white",
          "transition-opacity hover:opacity-90",
        )}
      >
        <Check className="h-4 w-4" />
      </button>
    </form>
  );
}
