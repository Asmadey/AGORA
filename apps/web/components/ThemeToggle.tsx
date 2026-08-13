"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";
import { applyTheme, storeTheme, storedTheme, systemTheme, type Theme } from "@/lib/theme";

/**
 * Переключатель светлой и тёмной темы.
 *
 * Состояние читается в эффекте, а не при первом рендере: на сервере нет ни
 * localStorage, ни matchMedia, и попытка узнать тему при отрисовке дала бы
 * расхождение разметки с клиентской — React ответил бы ошибкой гидратации.
 * До первого эффекта кнопка рисуется в нейтральном виде, а сама тема к этому
 * моменту уже применена скриптом из <head>, так что мигания не будет.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    setTheme(storedTheme() ?? systemTheme());
  }, []);

  // Пока пользователь не выбрал тему сам, интерфейс следует за системой:
  // переключение в настройках ОС меняет его на лету. После явного выбора
  // подписка снимается — иначе система переспорила бы человека.
  useEffect(() => {
    if (storedTheme()) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const next = media.matches ? "dark" : "light";
      setTheme(next);
      applyTheme(next);
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const next: Theme = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={() => {
        setTheme(next);
        storeTheme(next);
        applyTheme(next);
      }}
      // Подпись говорит, что произойдёт по нажатию, а не что сейчас включено:
      // скринридер читает кнопку как действие, и «тёмная тема» на кнопке,
      // которая включает светлую, означала бы ровно обратное.
      aria-label={next === "dark" ? "Включить тёмную тему" : "Включить светлую тему"}
      title={next === "dark" ? "Тёмная тема" : "Светлая тема"}
      className={cn(
        "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
        "border border-hairline bg-canvas text-ink transition-colors",
        "hover:bg-surface",
        className,
      )}
    >
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}
