import "server-only";

import { argon2Verify } from "hash-wasm";
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

import { authConfig } from "./auth.config";
import { withoutTenant } from "./db";

/**
 * Auth.js self-host, вход по логину и паролю (Decision Log #9, задача #3).
 *
 * Внешние провайдеры сознательно не подключены: продукт продаётся как self-host,
 * а OAuth добавляет обязательную зависимость от чужого сервиса к процедуре входа.
 * Схема users совместима с адаптером Auth.js, так что добавление провайдера
 * позже — это новая миграция с таблицей accounts, а не переделка того, что есть.
 *
 * ─── Что здесь про безопасность ────────────────────────────────────────
 * · Пароль проверяется argon2id. Параметры едут внутри самого хеша (формат PHC),
 *   поэтому их можно поднять, не ломая уже заведённые учётные записи.
 * · Реализация — WebAssembly (hash-wasm), а не нативный модуль. Причина
 *   практическая: каталог node_modules общий для macOS разработчика, Linux
 *   помощника и alpine-образа воркера, а нативная сборка привязана к платформе —
 *   установленная на одной, она ломает запуск на двух других. WASM одинаков
 *   везде. Плата — проверка идёт заметно медленнее нативной, но это одна
 *   операция на вход, а не на запрос.
 * · При несуществующем адресе всё равно выполняется проверка против фиктивного
 *   хеша. Иначе время ответа отвечает на вопрос «есть ли такой пользователь»
 *   даже при одинаковом тексте ошибки.
 * · Сообщение об ошибке одно на оба случая — неверный адрес и неверный пароль.
 */

/**
 * Настоящий argon2id-хеш от строки, которой заведомо нет среди паролей.
 * Нужен только ради времени ответа, поэтому и параметры совпадают с боевыми:
 * иначе проверка «в пустоту» отработает быстрее настоящей и разница снова
 * начнёт отвечать на вопрос «есть ли такой пользователь».
 */
const DUMMY_HASH =
  "$argon2id$v=19$m=19456,t=2,p=1$Zerp259diwW55jiWM/zbzw$edZSB58uQYjDYp4O4VJkyn9L2qbylNBCV4e5wmBmua4";

interface Membership {
  team_id: string;
  team_name: string;
  role: "owner" | "member";
}

async function findUser(email: string) {
  return withoutTenant(async (client) => {
    const { rows } = await client.query<{
      id: string;
      email: string;
      name: string | null;
      password_hash: string | null;
    }>("SELECT * FROM app.find_user_by_email($1)", [email]);
    return rows[0] ?? null;
  });
}

async function membershipsOf(userId: string): Promise<Membership[]> {
  return withoutTenant(async (client) => {
    const { rows } = await client.query<Membership>(
      "SELECT * FROM app.memberships_of_user($1)",
      [userId],
    );
    return rows;
  });
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  providers: [
    Credentials({
      credentials: {
        email: { label: "Почта", type: "email" },
        password: { label: "Пароль", type: "password" },
      },
      async authorize(credentials) {
        const email = typeof credentials?.email === "string" ? credentials.email.trim() : "";
        const password = typeof credentials?.password === "string" ? credentials.password : "";
        if (!email || !password) return null;

        const user = await findUser(email);

        // Сравнение выполняется всегда — и когда сравнивать не с чем.
        const hash = user?.password_hash ?? DUMMY_HASH;
        let valid = false;
        try {
          valid = await argon2Verify({ password, hash });
        } catch {
          valid = false; // повреждённый хеш — отказ, а не пятисотка
        }
        if (!user || !user.password_hash || !valid) return null;

        // Человек без команды войти не может: арендатор — обязательная часть
        // сессии, без него любой запрос к данным упрётся в default deny RLS
        // и выдаст пустоту вместо внятного отказа.
        const memberships = await membershipsOf(user.id);
        if (memberships.length === 0) return null;

        const active = memberships[0];
        return {
          id: user.id,
          email: user.email,
          name: user.name,
          tenantId: active.team_id,
          teamName: active.team_name,
          role: active.role,
        };
      },
    }),
  ],
});
