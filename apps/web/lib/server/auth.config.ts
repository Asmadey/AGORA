import type { NextAuthConfig } from "next-auth";

/**
 * Базовая конфигурация Auth.js без провайдеров и без обращений к базе.
 *
 * Разделение на два файла — не стиль, а необходимость: middleware исполняется в
 * edge-рантайме, где нет ни сокетов, ни нативных модулей, а проверка пароля
 * тянет и pg, и argon2. Импорт полного конфига в middleware ломает сборку.
 * Поэтому здесь — только то, что умеет работать где угодно: маршруты, форма
 * токена и правило доступа. Провайдер живёт в auth.ts, который импортируется
 * исключительно из серверных маршрутов Node.
 */

/**
 * Открытые маршруты. Всё остальное закрыто по умолчанию.
 *
 * Сравнение идёт по префиксу (см. `isPublicPath`), поэтому запись открывает не
 * один адрес, а всё поддерево под ним. Отсюда `/api-docs` отдельным сегментом:
 * документация обязана отвечать без сессии, а открыть её внутри `/api` значило
 * бы открыть вместе с ней все маршруты арендатора.
 */
export const PUBLIC_PATHS = ["/login", "/api/auth", "/api/health", "/api-docs"] as const;

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export const authConfig = {
  // JWT, а не таблица сессий: провайдер Credentials в Auth.js v5 не поддерживает
  // стратегию database. Плата — отзыв членства не действует мгновенно, поэтому
  // guard.ts перепроверяет роль в базе на каждом действии, а не верит токену.
  session: { strategy: "jwt", maxAge: 60 * 60 * 24 * 7 },
  pages: { signIn: "/login" },
  // Self-host за обратным прокси: Auth.js по умолчанию не верит заголовку Host,
  // потому что подделанный Host уводит ссылку подтверждения на чужой домен.
  // Здесь домен задаётся своими руками в AUTH_URL, поэтому доверие уместно.
  trustHost: true,
  providers: [],
  callbacks: {
    // Вызывается middleware. Решение принимается без обращения к базе.
    authorized({ request, auth }) {
      const { pathname } = request.nextUrl;
      if (isPublicPath(pathname)) return true;
      if (auth?.user) return true;

      // Для страницы правильный ответ — перенаправление на форму входа (его
      // сделает Auth.js, получив false). Для API — нет: клиент ждёт JSON, а
      // получит 200 и HTML формы логина, что выглядит как успешный ответ с
      // мусором вместо данных. Поэтому здесь явный 401.
      if (pathname.startsWith("/api/")) {
        return Response.json({ error: "требуется вход" }, { status: 401 });
      }
      return false;
    },
    jwt({ token, user }) {
      if (user) {
        token.userId = user.id as string;
        token.tenantId = (user as { tenantId?: string }).tenantId;
        token.role = (user as { role?: string }).role;
        token.teamName = (user as { teamName?: string }).teamName;
      }
      return token;
    },
    session({ session, token }) {
      session.user.id = token.userId as string;
      session.user.tenantId = token.tenantId as string;
      session.user.role = token.role as "owner" | "member";
      session.user.teamName = token.teamName as string;
      return session;
    },
  },
} satisfies NextAuthConfig;
