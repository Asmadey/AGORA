"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signOut } from "next-auth/react";
import {
  FolderKanban,
  ListChecks,
  ClipboardList,
  Users,
  UsersRound,
  BookUser,
  BookOpen,
  Database,
  ShieldCheck,
  UserCog,
  Plus,
  SlidersHorizontal,
  Settings,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/ThemeToggle";

/**
 * Каркас приложения: левое меню по PRD §6 + рабочая область.
 *
 * Меню видно только авторизованным пользователям. До входа показывается
 * только рабочая область (форма логина), без навигации.
 *
 * Скролл принадлежит только рабочей области. Корневой контейнер держит высоту
 * ровно в экран (h-screen + overflow-hidden), меню не прокручивается вместе с
 * содержимым, а <main> получает собственный overflow-y-auto.
 *
 * ─── Почему меню — это находка, а не оформление ────────────────────────────
 * Прежний состав перечислял пять пунктов и называл `/` «Проектами», хотя по
 * этому адресу список прогонов. Проектов, аудиторий и анкет в меню не было
 * вовсе: три готовых экрана существовали в сборке, отвечали по своим адресам —
 * и не были достижимы ни одним кликом. Единственное, что на них ссылалось, —
 * `NavBar.tsx`, который ни в один layout не подключён.
 *
 * Это тот же класс дефекта, что и данные во вкладке: сборка зелёная, маршруты
 * отвечают, экраны отрисовываются, а продукта у пользователя нет. Меню —
 * единственное место, где видно, из чего продукт состоит, поэтому список
 * разделов здесь обязан совпадать с деревом `app/`.
 */

const NAV = [
  { href: "/researches", label: "Исследования", icon: ListChecks },
  { href: "/projects", label: "Проекты", icon: FolderKanban },
  { href: "/audience", label: "Аудитории", icon: UsersRound },
  { href: "/surveys", label: "Анкеты", icon: ClipboardList },
  { href: "/personas", label: "Персоны", icon: Users },
  { href: "/portraits", label: "Портреты аудиторий", icon: BookUser },
  // Корпус — то, на чём стоит заземление: из него считаются доли, по которым
  // сэмплируются персоны. До этапа Е он лежал файлом в репозитории, то есть
  // принадлежал разработчику, а не исследователю.
  { href: "/corpus", label: "Корпус", icon: Database },
  { href: "/prompts", label: "Промпт-студия", icon: SlidersHorizontal },
  // Судья стоит отдельным разделом, а не блоком в Настройках: настройки
  // отвечают «как считать», а этот раздел — «кому верить».
  { href: "/qa-judge", label: "QA судья", icon: ShieldCheck },
  { href: "/users", label: "Пользователи", icon: UserCog },
  { href: "/settings", label: "Настройки", icon: Settings },
  // Страница /api-docs существовала с задачи #26, но попасть на неё можно
  // было только по прямой ссылке: пункта меню не было.
  { href: "/api-docs", label: "API-документация", icon: BookOpen },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { data: session, status } = useSession();

  const isAuthenticated = status === "authenticated" && !!session?.user;

  return (
    <div className="flex h-screen overflow-hidden">
      {isAuthenticated && (
        <aside className="hidden h-screen w-60 shrink-0 flex-col overflow-hidden border-r border-hairline bg-surface md:flex">
          <div className="flex h-14 items-center gap-2 border-b border-hairline px-5">
            {/* Жёлтый знак по DESIGN.md: на белом холсте он единственная
                насыщенная точка и потому работает опознавательным знаком.
                Чёрный квадрат на белом сливался бы с текстом. */}
            <div className="grid h-7 w-7 place-items-center rounded-md bg-brand-yellow text-[13px] font-bold text-ink">
              A
            </div>
            <span className="text-[15px] font-semibold tracking-tight">AGORA</span>
            <ThemeToggle className="ml-auto h-7 w-7" />
          </div>

          {/* Запуск исследования — главное действие продукта, и он стоит над
              разделами, а не среди них: визард это не место, куда ходят
              смотреть, а то, ради чего сюда пришли. Раньше попасть в него можно
              было только из карточки персоны или по прямой ссылке. */}
          <div className="px-3 pt-3">
            <Link
              href="/studies/new"
              className="flex items-center justify-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-ink/90"
            >
              <Plus className="h-4 w-4 shrink-0" />
              Новое исследование
            </Link>
          </div>

          <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
            {NAV.map(({ href, label, icon: Icon }) => {
              // Отчёт прогона живёт на /runs/<id>, но принадлежит разделу
              // «Исследования»: без этой связи открытый отчёт гасил подсветку
              // целиком, и по меню выходило, что пользователь нигде.
              const active =
                pathname.startsWith(href) ||
                (href === "/researches" && pathname.startsWith("/runs"));
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                    active
                      ? "bg-canvas font-medium text-ink shadow-[0_1px_2px_rgba(5,0,56,0.06)]"
                      : "text-slate hover:bg-canvas/70 hover:text-ink",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {label}
                </Link>
              );
            })}
          </nav>

          {/* Название команды отсюда убрано: одна команда на арендатора, и
              подпись «Команда / AGORA Team» повторяла то, что и так следует из
              входа. Роль оставлена — от неё зависит, что можно нажать. */}
          <div className="border-t border-hairline px-5 py-3">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm">
                  {session?.user?.name ?? session?.user?.email ?? ""}
                </p>
                <p className="text-[11px] uppercase tracking-wide text-stone">
                  {session?.user?.role ?? ""}
                </p>
              </div>
              <button
                onClick={() => signOut({ callbackUrl: "/login" })}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-slate transition-colors hover:bg-secondary hover:text-ink"
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
  back,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  /**
   * Возврат — слева от заголовка, а не в общей группе действий справа.
   *
   * «Назад» и «сделать что-то» — разные жанры. В одном ряду справа возврат
   * читается как ещё одно действие над содержимым страницы и теряется среди
   * них тем вернее, чем больше действий рядом. Слева он попадает туда, где
   * взгляд начинает строку.
   */
  back?: React.ReactNode;
}) {
  return (
    <header className="border-b border-hairline px-8 py-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {/* mt-1 равняет кнопку по первой строке заголовка: у 28px/1.25
              верхний край буквы ниже верха строки, и без сдвига кнопка
              выглядит приподнятой. */}
          {back && <div className="mt-1 shrink-0">{back}</div>}
          <div className="min-w-0">
            {/* heading-3 из DESIGN.md: 28px/1.25, средняя насыщенность.
                Отрицательный трекинг из спецификации оставлен только крупным
                размерам — на 28px он уже съедает воздух между буквами. */}
            <h1 className="text-[28px] font-medium leading-[1.25] tracking-tight">{title}</h1>
            {subtitle && (
              <p className="mt-1 max-w-2xl text-sm text-slate">{subtitle}</p>
            )}
          </div>
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}