"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FolderKanban,
  Users,
  BookUser,
  SlidersHorizontal,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Каркас приложения: левое меню по PRD §6 + рабочая область.
 *
 * Меню фиксированное и всегда видно — это внутренний инструмент, где переключение
 * между разделами частое, а не одноразовое. Скрывать навигацию в бургер здесь
 * означало бы экономить пиксели за счёт основной работы пользователя.
 *
 * Скролл принадлежит только рабочей области. Корневой контейнер держит высоту
 * ровно в экран (h-screen + overflow-hidden), меню не прокручивается вместе с
 * содержимым, а <main> получает собственный overflow-y-auto. Иначе при длинном
 * отчёте навигация уезжает вверх, и чтобы сменить раздел, нужно сначала
 * пролистать страницу обратно.
 */

const NAV = [
  { href: "/", label: "Проекты", icon: FolderKanban },
  { href: "/personas", label: "Персоны", icon: Users },
  { href: "/portraits", label: "Портреты аудиторий", icon: BookUser },
  { href: "/prompts", label: "Промпт-студия", icon: SlidersHorizontal },
  { href: "/settings", label: "Настройки", icon: Settings },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="hidden h-screen w-60 shrink-0 flex-col overflow-hidden border-r border-border bg-[hsl(222_47%_7%)] md:flex">
        <div className="flex h-14 items-center gap-2 border-b border-border px-5">
          <div className="grid h-7 w-7 place-items-center rounded-md bg-foreground text-[13px] font-bold text-background">
            A
          </div>
          <span className="text-[15px] font-semibold tracking-tight">AGORA</span>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-border px-5 py-3">
          <p className="text-xs text-muted-foreground">Команда</p>
          <p className="truncate text-sm">Студия «Ландыши»</p>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}

/** Шапка страницы: заголовок, пояснение и место под действия справа. */
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="border-b border-border px-8 py-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {subtitle && (
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}
