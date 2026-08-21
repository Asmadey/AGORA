import "server-only";

import { randomBytes } from "node:crypto";

import { argon2id } from "hash-wasm";
import type { PoolClient } from "pg";

/**
 * Участники команды (этап Ж).
 *
 * ─── Почему пароль хешируется здесь, а не в маршруте ───────────────────────
 * Параметры argon2id — это контракт: они уезжают внутрь строки хеша в формате
 * PHC, и проверка при входе читает их оттуда. Написанные в двух местах, они
 * разойдутся, и разойдутся тихо: пользователь, заведённый одним путём, войдёт,
 * а заведённый другим — тоже войдёт, просто его пароль будет защищён слабее.
 * Заметить это по продукту невозможно.
 *
 * Значения совпадают с `scripts/seed-auth.mjs` (OWASP: 19 МиБ, 2 прохода,
 * параллелизм 1, 32 байта) — и это единственное оставшееся дублирование, потому
 * что скрипт запускается до того, как существует хоть одна команда, и импортить
 * ему отсюда нечего.
 *
 * ─── Почему argon2 из WebAssembly ──────────────────────────────────────────
 * Нативные npm-модули в apps/web запрещены (§6 CLAUDE.md): собранный под Linux
 * пакет ломает запуск на macOS, и это уже стоило прохода. `hash-wasm` — тот же
 * argon2id без нативной сборки.
 */

export interface TeamMember {
  userId: string;
  email: string;
  name: string | null;
  role: "owner" | "member";
  /**
   * Когда человек вошёл в ЭТУ команду — `team_members.joined_at`.
   *
   * Не дата заведения учётной записи: `users` глобальна, и участник команды Б
   * мог завести аккаунт годом раньше, работая в команде А. Список состава
   * команды отвечает на вопрос «с какого момента он здесь», а не «с какого
   * момента он вообще существует».
   */
  joinedAt: string;
}

/** Параметры argon2id по OWASP. Уезжают внутрь строки хеша — см. модульный докстринг. */
async function hashPassword(password: string): Promise<string> {
  return argon2id({
    password,
    salt: randomBytes(16),
    memorySize: 19456,
    iterations: 2,
    parallelism: 1,
    hashLength: 32,
    outputType: "encoded",
  });
}

export async function listMembers(client: PoolClient): Promise<TeamMember[]> {
  const { rows } = await client.query<{
    user_id: string;
    email: string;
    name: string | null;
    role: "owner" | "member";
    joined_at: Date;
  }>(
    `SELECT m.user_id, u.email, u.name, m.role, m.joined_at
     FROM team_members m
     JOIN users u ON u.id = m.user_id
     WHERE m.team_id = app.current_tenant()
     ORDER BY m.role, u.email`,
  );
  return rows.map((r) => ({
    userId: r.user_id,
    email: r.email,
    name: r.name,
    role: r.role,
    joinedAt: r.joined_at.toISOString(),
  }));
}

/**
 * Заводит пользователя и членство в команде.
 *
 * ─── Почему существующий пользователь не получает новый пароль ─────────────
 * `users` — глобальная таблица: один человек состоит в нескольких командах.
 * Владелец команды Б, добавляя к себе участника команды А, не должен менять
 * ему пароль — иначе добавление в команду становится способом отобрать чужой
 * доступ. Поэтому здесь ON CONFLICT DO NOTHING по адресу, а пароль ставится
 * только новому пользователю.
 */
export async function addMember(
  client: PoolClient,
  params: { email: string; name: string | null; password: string; role: "owner" | "member" },
): Promise<{ member: TeamMember; created: boolean }> {
  const passwordHash = await hashPassword(params.password);

  const inserted = await client.query<{ id: string }>(
    `INSERT INTO users (email, name, password_hash)
     VALUES ($1, $2, $3)
     ON CONFLICT (email) DO NOTHING
     RETURNING id`,
    [params.email, params.name, passwordHash],
  );

  const created = inserted.rows.length > 0;
  const userId =
    inserted.rows[0]?.id ??
    (
      await client.query<{ id: string }>("SELECT id FROM users WHERE email = $1", [
        params.email,
      ])
    ).rows[0]?.id;

  if (!userId) throw new Error("пользователь не создан и не найден");

  await client.query(
    `INSERT INTO team_members (team_id, user_id, role)
     VALUES (app.current_tenant(), $1, $2)
     ON CONFLICT (team_id, user_id) DO UPDATE SET role = EXCLUDED.role`,
    [userId, params.role],
  );

  const { rows } = await client.query<{
    email: string;
    name: string | null;
    role: "owner" | "member";
    joined_at: Date;
  }>(
    `SELECT u.email, u.name, m.role, m.joined_at
     FROM team_members m JOIN users u ON u.id = m.user_id
     WHERE m.team_id = app.current_tenant() AND m.user_id = $1`,
    [userId],
  );

  return {
    member: {
      userId,
      email: rows[0].email,
      name: rows[0].name,
      role: rows[0].role,
      joinedAt: rows[0].joined_at.toISOString(),
    },
    created,
  };
}

export class LastOwnerError extends Error {
  constructor() {
    super(
      "нельзя удалить последнего владельца команды: без владельца никто не сможет " +
        "завести пользователя, сменить настройки и удалить исследование",
    );
  }
}

/**
 * Снимает членство. Пользователь остаётся — он может состоять в других командах.
 *
 * Последний владелец не удаляется. Команда без владельца — это состояние, из
 * которого нет выхода изнутри продукта: владельческие действия требуют роли,
 * которой больше ни у кого нет, и вернуть её можно только запросом в базу.
 */
export async function removeMember(
  client: PoolClient,
  userId: string,
): Promise<boolean> {
  const { rows } = await client.query<{ role: "owner" | "member"; owners: string }>(
    `SELECT m.role,
            (SELECT COUNT(*) FROM team_members o
              WHERE o.team_id = app.current_tenant() AND o.role = 'owner') AS owners
     FROM team_members m
     WHERE m.team_id = app.current_tenant() AND m.user_id = $1`,
    [userId],
  );
  const row = rows[0];
  if (!row) return false;
  if (row.role === "owner" && Number(row.owners) <= 1) throw new LastOwnerError();

  const { rowCount } = await client.query(
    "DELETE FROM team_members WHERE team_id = app.current_tenant() AND user_id = $1",
    [userId],
  );
  return (rowCount ?? 0) > 0;
}
