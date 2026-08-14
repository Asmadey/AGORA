"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Trash2, X } from "lucide-react";

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
  variant = "icon",
  onDeleted,
}: {
  runId: string;
  className?: string;
  /**
   * `icon` — крестик в углу карточки списка. `danger` — явная красная кнопка
   * на экране исследования.
   *
   * Один компонент на оба места, а не два: удаление здесь — это не «нажать
   * DELETE», а разбор пяти исходов (202 отмены, зависший QUEUED, недоудалённые
   * объекты, отказ, успех). Написанный дважды, он разойдётся по обработке
   * ровно тех случаев, ради которых и написан.
   */
  variant?: "icon" | "danger";
  /** Куда уходить после удаления. По умолчанию — обновить текущий экран. */
  onDeleted?: () => void;
}) {
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Отмена запрошена, но воркер ещё не остановился. Отдельно от ошибки: это
  // нормальный ход событий, а не отказ.
  const [notice, setNotice] = useState<string | null>(null);

  // Кнопка живёт внутри ссылки на прогон: без остановки всплытия любой клик
  // по ней открывал бы отчёт вместо удаления.
  const swallow = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  async function remove(e: React.MouseEvent, force = false) {
    swallow(e);
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`/api/tasks/${runId}${force ? "?force=1" : ""}`, {
        method: "DELETE",
      });
      const payload = await res.json().catch(() => ({}));

      // 202 — воркер ведёт этот прогон, отмена запрошена и сработает между
      // этапами. Показываем это как состояние, а не как ошибку: пользователь
      // сделал ровно то, что хотел, просто результат придёт не сразу.
      if (res.status === 202) {
        setNotice(payload.message ?? "Отмена запрошена");
        setAsking(false);
        router.refresh();
        return;
      }

      if (!res.ok) {
        setError(payload.error ?? `сервер ответил ${res.status}`);
        setAsking(false);
        return;
      }

      // Мусор, оставшийся в хранилищах, называется вслух: молчание про
      // неудалённый ролик означало бы, что за место платят неизвестно за что.
      if (Array.isArray(payload.leftovers) && payload.leftovers.length > 0) {
        setNotice(`Удалено. Осталось убрать: ${payload.leftovers.join("; ")}`);
        router.refresh();
        return;
      }
      if (onDeleted) {
        onDeleted();
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

  if (notice) {
    return (
      <span
        onClick={swallow}
        className={cn(
          "max-w-[18rem] rounded-md bg-surface px-2 py-1 text-[11px] leading-snug text-slate",
          className,
        )}
      >
        {notice}
      </span>
    );
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
          onClick={(e) => remove(e)}
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

  if (variant === "danger") {
    return (
      <button
        type="button"
        onClick={(e) => {
          swallow(e);
          setAsking(true);
        }}
        className={cn(
          "inline-flex items-center gap-2 rounded-md border border-danger px-4 py-2 text-sm",
          "text-danger transition-colors hover:bg-danger hover:text-white",
          className,
        )}
      >
        <Trash2 className="h-4 w-4" />
        Удалить
      </button>
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
