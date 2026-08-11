"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/agora/States";

/**
 * Граница ошибки приложения (App Router).
 *
 * Без неё отказ серверного компонента даёт стандартный экран Next.js: заголовок
 * латиницей, никакого контекста и никакого способа повторить, кроме перезагрузки
 * вручную. Половина отказов здесь — временные (база не поднялась, Mongo моргнул),
 * и кнопка «повторить» решает их без обращения в поддержку.
 *
 * `digest` показывается намеренно. В production Next.js вырезает текст ошибки из
 * ответа, чтобы не отдать наружу внутренности, и оставляет только этот
 * идентификатор — по нему строку находят в логе сервера. Без него пользователь
 * не может сообщить ничего, кроме «не работает».
 */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // В консоль браузера — чтобы при разработке причина была под рукой, а не
    // только в терминале сервера.
    console.error("Отказ экрана:", error);
  }, [error]);

  return (
    <div className="p-8">
      <ErrorState
        title="Экран не открылся"
        reason={
          error.digest
            ? `${error.message || "внутренняя ошибка"} · digest ${error.digest}`
            : error.message || "внутренняя ошибка"
        }
        retry={
          <button
            onClick={reset}
            className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
          >
            Повторить
          </button>
        }
      />
    </div>
  );
}
