"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signOut } from "next-auth/react";
import {
  FolderKanban,
  Users,
  BookUser,
  SlidersHorizontal,
  Settings,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Каркас приложения: левое меню по PRD §6 + рабочая область.
 *
 * Меню видно только авторизованным пользователям. До входа показывается
 * только рабочая область (форма логина), без навигации.
 *
 * Скролл принадлежит только рабочей области. Корневой контейнер держит высоту
 * ровно в экран (h-screen + overflow-hidden), меню не прокручивается вместе с
 * содержимым, а <main> получает собственный overflow-y-auto.
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
  const { data: session, status } = useSession();

  const isAuthenticated = status === "authenticated" && !!session?.user;

  return (
    <div className="flex h-screen overflow-hidden">
      {isAuthenticated && (
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
            <p className="truncate text-sm">{session?.user?.teamName ?? "—"}</p>
            <div className="mt-3 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-xs text-muted-foreground">
                  {session?.user?.name ?? session?.user?.email ?? ""}
                </p>
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground/60">
                  {session?.user?.role ?? ""}
                </p>
              </div>
              <button
                onClick={() => signOut({ callbackUrl: "/login" })}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                title="Выйти"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </aside>
      )}

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