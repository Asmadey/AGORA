"use client";

import { Check, Pencil, X } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

/**
 * Заголовок проекта с правкой на месте.
 *
 * ─── Почему не отдельная секция «Переименовать» ────────────────────────────
 * Она стояла внизу страницы, под списком прогонов и рядом с удалением. Чтобы
 * поправить название, приходилось пролистать весь список и найти форму там, где
 * ищут опасные действия. Правка имени — не опасное действие, и место ей рядом с
 * именем.
 *
 * ─── Почему две кнопки, а не одна ──────────────────────────────────────────
 * Отмена нужна отдельной кнопкой: Esc знают не все, а клик мимо поля в форме,
 * которая сохраняет по Enter, легко теряет правку. Цвета разведены намеренно —
 * зелёная галочка и красный крестик читаются без подписи.
 */
export function ProjectTitle({
  id,
  name,
  action,
}: {
  id: string;
  name: string;
  /** Серверное действие переименования. То же, что было у прежней формы. */
  action: (formData: FormData) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);

  if (!editing) {
    return (
      <span className="inline-flex items-center gap-2">
        {name}
        <button
          type="button"
          onClick={() => {
            // Значение берётся из пропса, а не из прошлой правки: между
            // открытиями имя могло смениться на другой вкладке.
            setValue(name);
            setEditing(true);
          }}
          aria-label="Переименовать проект"
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
      className="inline-flex items-center gap-2"
    >
      <input type="hidden" name="id" value={id} />
      <input
        name="name"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        required
        maxLength={200}
        autoFocus
        aria-label="Название проекта"
        // Esc отменяет — но кнопка отмены всё равно есть: клавишу знают не все.
        onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
        className="min-w-0 rounded-md border border-hairline bg-background px-2 py-1 text-2xl outline-none transition-colors focus:border-muted-foreground/60"
      />
      <button
        type="button"
        onClick={() => setEditing(false)}
        aria-label="Отменить переименование"
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded-md bg-danger text-white",
          "transition-opacity hover:opacity-90",
        )}
      >
        <X className="h-4 w-4" />
      </button>
      <button
        type="submit"
        aria-label="Сохранить название"
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded-md bg-success text-white",
          "transition-opacity hover:opacity-90",
        )}
      >
        <Check className="h-4 w-4" />
      </button>
    </form>
  );
}
