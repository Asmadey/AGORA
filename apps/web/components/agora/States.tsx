import Link from "next/link";
import type { ReactNode } from "react";
import { AlertTriangle, Inbox } from "lucide-react";

/**
 * Четыре состояния экрана: загрузка, пусто, ошибка, данные.
 *
 * Экран, нарисованный только для «данных», выглядит сломанным ровно тогда, когда
 * пользователю тяжелее всего: в первую секунду, на пустом аккаунте и при отказе
 * базы. Три первых состояния забывают потому, что при разработке их не видно —
 * у разработчика данные всегда есть.
 *
 * Примитивы собраны в один файл, а не написаны по месту, по той же причине, по
 * которой у отчёта один разбор: пять экранов, каждый со своей пустотой, дадут
 * пять разных объяснений одного и того же, и пользователь будет гадать, значат
 * ли они разное.
 *
 * ─── Почему skeleton, а не спиннер ───────────────────────────────────────────
 * Спиннер сообщает «идёт загрузка» и больше ничего. Skeleton по форме будущего
 * контента сообщает, чего ждать и сколько его будет, — и когда данные приезжают,
 * страница не прыгает, потому что высота уже занята.
 */

/** Серый прямоугольник под будущий контент. Размер задаётся классами. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-secondary/60 ${className}`}
      // Скринридеру пульсирующая заглушка не нужна: она не содержит смысла, а
      // объявлять её как контент значило бы зачитывать пустоту.
      aria-hidden="true"
    />
  );
}

/** Полоса-заголовок и строки под неё — форма любого списка в приложении. */
export function SkeletonList({ rows = 5, height = "h-20" }: { rows?: number; height?: string }) {
  return (
    <div className="space-y-3" role="status" aria-label="Загрузка">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={`w-full ${height}`} />
      ))}
      <span className="sr-only">Загрузка</span>
    </div>
  );
}

/** Сетка плашек — форма реестра персон и портретов. */
export function SkeletonGrid({ cards = 8 }: { cards?: number }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
         role="status" aria-label="Загрузка">
      {Array.from({ length: cards }, (_, i) => (
        <Skeleton key={i} className="h-36 w-full" />
      ))}
      <span className="sr-only">Загрузка</span>
    </div>
  );
}

/** Шапка страницы на время загрузки: заголовок и подпись уже занимают место. */
export function SkeletonHeader() {
  return (
    <div className="border-b border-hairline px-8 py-6">
      <Skeleton className="h-7 w-56" />
      <Skeleton className="mt-3 h-4 w-full max-w-xl" />
    </div>
  );
}

/**
 * Пусто — с объяснением и следующим шагом.
 *
 * «Ничего не найдено» оставляет пользователя гадать, сломалось оно или он ещё
 * ничего не создал. Поэтому обязательны две вещи: что означает пустота и что
 * сделать дальше.
 */
export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description: string;
  action?: { href: string; label: string };
  icon?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-hairline px-8 py-14 text-center">
      <div className="mx-auto mb-4 grid h-11 w-11 place-items-center rounded-full bg-secondary text-slate">
        {icon ?? <Inbox className="h-5 w-5" />}
      </div>
      <h2 className="text-sm font-medium">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-slate">
        {description}
      </p>
      {action && (
        <Link
          href={action.href}
          className="mt-5 inline-block rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
        >
          {action.label}
        </Link>
      )}
    </div>
  );
}

/**
 * Ошибка — с текстом причины и способом повторить.
 *
 * Причина показывается, а не прячется за «что-то пошло не так»: пользователь
 * этого сервиса — исследователь, который сам разворачивал self-host, и «не
 * удалось подключиться к базе» для него действие, а не шум. Скрытая причина
 * превращает диагностику в переписку.
 */
export function ErrorState({
  title = "Не удалось загрузить",
  reason,
  retry,
}: {
  title?: string;
  reason?: string;
  retry?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-warning/30 bg-warning-soft/60 px-8 py-12 text-center">
      <div className="mx-auto mb-4 grid h-11 w-11 place-items-center rounded-full bg-amber-500/10 text-warning">
        <AlertTriangle className="h-5 w-5" />
      </div>
      <h2 className="text-sm font-medium text-amber-200">{title}</h2>
      {reason && (
        <p className="mx-auto mt-2 max-w-lg break-words font-mono text-xs leading-relaxed text-slate">
          {reason}
        </p>
      )}
      {retry && <div className="mt-5">{retry}</div>}
    </div>
  );
}
