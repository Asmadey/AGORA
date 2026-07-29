import NextAuth from "next-auth";

import { authConfig } from "@/lib/server/auth.config";

/**
 * Закрытие маршрутов сессией Auth.js (задача #3).
 *
 * Пришло на смену basic-auth заглушке. Здесь берётся authConfig без провайдеров:
 * middleware исполняется в edge-рантайме, а проверка пароля тянет pg и argon2 —
 * нативный код, которого в edge нет. Middleware отвечает только на вопрос
 * «есть ли действующий подписанный токен»; кто этот пользователь и что ему
 * можно — решает guard.ts уже в Node.
 *
 * Правило по умолчанию — «закрыто». Список исключений (/login, /api/auth,
 * /api/health) задан явно в PUBLIC_PATHS в auth.config.ts, поэтому новый
 * маршрут оказывается защищённым сам собой. Обратный порядок — перечислять то,
 * что нужно защитить, — означал бы, что забытый маршрут открыт; забывают именно
 * в эту сторону.
 */
export const { auth: middleware } = NextAuth(authConfig);

export default middleware;

export const config = {
  // Статика Next.js не содержит данных арендатора и не должна будить проверку на
  // каждом файле. Всё остальное, включая /api, проходит через middleware.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
