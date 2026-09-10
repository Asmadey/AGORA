"use client";

import { SessionProvider } from "next-auth/react";
import type { Session } from "next-auth";

/**
 * Провайдеры приложения.
 *
 * ─── Почему сессия приезжает параметром, а не добывается здесь ────────────
 * Без начального значения `useSession()` стартует со `status: "loading"` и
 * идёт за `/api/auth/session` уже из браузера. На СЕРВЕРНОЙ отрисовке это
 * значит «не авторизован», а `AppShell` прячет за этим условием всё левое
 * меню — то есть в отправленном HTML тега `<aside>` нет вовсе.
 *
 * Пользователь видел это так: справа уже нарисованы исследования, слева пусто,
 * и меню появляется после гидратации и сетевого похода. Меню не «медленное» —
 * его в первой отрисовке просто нет.
 *
 * Сессия снимается в корневом layout через `auth()` и передаётся сюда. Это
 * проверка подписи JWT-куки, без обращения к базе: стратегия JWT здесь не
 * выбор, а следствие Credentials-провайдера.
 */
export function Providers({
  children,
  session,
}: {
  children: React.ReactNode;
  /** `null` — гость. Именно `null`, а не `undefined`: `undefined` означает
   *  «неизвестно» и снова заставит провайдер идти за сессией в браузер. */
  session: Session | null;
}) {
  return <SessionProvider session={session}>{children}</SessionProvider>;
}
