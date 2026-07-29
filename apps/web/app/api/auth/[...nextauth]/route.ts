import { handlers } from "@/lib/server/auth";

/**
 * Точка входа Auth.js: /api/auth/signin, /api/auth/callback/credentials,
 * /api/auth/session, /api/auth/signout (задача #3).
 *
 * Маршрут открыт в PUBLIC_PATHS — иначе форма входа требовала бы входа.
 */
export const { GET, POST } = handlers;

// Проверка пароля идёт через pg и argon2 — нативные модули, в edge их нет.
export const runtime = "nodejs";
