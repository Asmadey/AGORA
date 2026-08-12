"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Крестик удаления на плашке прогона.
 *
 * ─── Почему подтверждение, а не сразу ──────────────────────────────────────
 * Крестик стоит в углу карточки, по которой кликают, чтобы её открыть, — то
 * есть ровно там, куда попадают мимо. Удаление прогона уносит отчёт, за
 * который заплачено моделью, и отменить его нечем: `DELETE` каскадом сносит
 * `reports`. Поэтому первое нажатие превращает крестик в вопрос, а не в
 * действие. Диалог здесь был бы тяжелее самой задачи и увёл бы фокус со
 * списка.
 *
 * ─── Почему отказ показывается текстом ─────────────────────────────────────
 * Идущий прогон удалить нельзя (маршрут отвечает 409), и это не ошибка
 * пользователя, а состояние системы. «Не удалось» отправило бы нажимать ещё
 * раз; текст маршрута объясняет, чего дождаться.
 */
export function DeleteRunButton({
  runId,
  className,
}: {
  runId: string;
  className?: string;
}) {
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Кнопка живёт внутри ссылки на прогон: без остановки всплытия любой клик
  // по ней открывал бы отчёт вместо удаления.
  const swallow = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  async function remove(e: React.MouseEvent) {
    swallow(e);
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/tasks/${runId}`, { method: "DELETE" });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        setError(payload.error ?? `сервер ответил ${res.status}`);
        setAsking(false);
        return;
      }
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
      setAsking(false);
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <span
        onClick={swallow}
        className={cn(
          "max-w-[16rem] rounded-md bg-danger-soft px-2 py-1 text-[11px] leading-snug text-danger",
          className,
        )}
      >
        {error}
      </span>
    );
  }

  if (asking) {
    return (
      <span onClick={swallow} className={cn("flex items-center gap-1", className)}>
        <button
          type="button"
          onClick={remove}
          disabled={busy}
          className="rounded-full bg-danger px-2.5 py-1 text-[11px] font-medium text-white disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : "Удалить"}
        </button>
        <button
          type="button"
          onClick={(e) => {
            swallow(e);
            setAsking(false);
          }}
          className="rounded-full px-2 py-1 text-[11px] text-slate hover:text-ink"
        >
          Отмена
        </button>
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={(e) => {
        swallow(e);
        setAsking(true);
      }}
      aria-label="Удалить прогон"
      title="Удалить прогон"
      className={cn(
        "grid h-7 w-7 shrink-0 place-items-center rounded-full text-stone transition-colors",
        "hover:bg-danger-soft hover:text-danger",
        className,
      )}
    >
      <X className="h-3.5 w-3.5" />
    </button>
  );
}
