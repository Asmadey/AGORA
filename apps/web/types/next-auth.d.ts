import type { DefaultSession } from "next-auth";

/**
 * Расширение типов сессии Auth.js полями арендатора (задача #3).
 *
 * Без этого tenantId и role приходится доставать приведением на каждом
 * обращении, и первая же опечатка становится ошибкой времени выполнения —
 * при том, что от этих двух полей зависит, чьи данные увидит запрос.
 */

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      /** teams.id, он же tenant_id для RLS. */
      tenantId: string;
      teamName: string;
      role: "owner" | "member";
    } & DefaultSession["user"];
  }

  interface User {
    tenantId?: string;
    teamName?: string;
    role?: "owner" | "member";
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    userId?: string;
    tenantId?: string;
    teamName?: string;
    role?: "owner" | "member";
  }
}

export {};
