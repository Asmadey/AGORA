#!/usr/bin/env node
/**
 * Посев учётных записей (задача #3).
 *
 * Нужен дважды: чтобы вообще войти в свежую базу — регистрации в продукте нет,
 * команда заводится владельцем, — и чтобы CDD-проверка «member не может
 * выполнить owner-действие» имела на ком проверяться.
 *
 * Скрипт идёт под ролью, заданной в DATABASE_URL, и обязан работать до того, как
 * существует хоть один арендатор. Поэтому запись в teams/team_members идёт с уже
 * установленным тенант-контекстом: политика требует team_id = app.current_tenant(),
 * и первую строку команды можно вставить, только объявив её идентификатор заранее.
 *
 * Запуск:
 *   set -a; source .env.local; set +a
 *   node apps/web/scripts/seed-auth.mjs --team "Моя команда" --email me@example.com --password '…'
 *   node apps/web/scripts/seed-auth.mjs --team-id <uuid> --email m@example.com --password '…' --role member
 */
import { randomBytes, randomUUID } from "node:crypto";

import { parseArgs } from "node:util";

import { argon2id } from "hash-wasm";
import pg from "pg";

const { values } = parseArgs({
  options: {
    team: { type: "string" },
    "team-id": { type: "string" },
    email: { type: "string" },
    password: { type: "string" },
    role: { type: "string", default: "owner" },
  },
});

if (!values.email || !values.password) {
  console.error("нужны --email и --password");
  process.exit(2);
}
if (!values.team && !values["team-id"]) {
  console.error("нужен --team (создать команду) или --team-id (добавить в существующую)");
  process.exit(2);
}
if (!["owner", "member"].includes(values.role)) {
  console.error("--role: owner | member");
  process.exit(2);
}

// Сертификат передаётся параметром строки подключения, а не полем ssl: pg
// собирает конфигурацию как Object.assign({}, config, parse(connectionString)),
// и разобранная строка затирает явно заданный ssl вместе с корневым
// сертификатом. Та же логика в apps/web/lib/server/db.ts — там же объяснение.
function dsn() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    console.error("DATABASE_URL не задан: сделайте `set -a; source .env.local; set +a`");
    process.exit(2);
  }
  const caPath = process.env.PGSSLROOTCERT;
  if (!caPath || url.includes("sslrootcert=")) return url;
  return `${url}${url.includes("?") ? "&" : "?"}sslrootcert=${encodeURIComponent(caPath)}`;
}

const client = new pg.Client({ connectionString: dsn() });

// Параметры argon2id по OWASP: 19 МиБ памяти, 2 прохода, параллелизм 1.
// Они уезжают внутрь строки хеша (формат PHC), поэтому поднять их позже можно
// без миграции — старые записи продолжат проверяться своими параметрами.
const passwordHash = await argon2id({
  password: values.password,
  salt: randomBytes(16),
  memorySize: 19456,
  iterations: 2,
  parallelism: 1,
  hashLength: 32,
  outputType: "encoded",
});

await client.connect();
try {
  await client.query("BEGIN");
  await client.query("SET LOCAL ROLE agora_app");

  const teamId = values["team-id"] ?? randomUUID();
  await client.query("SELECT set_config('app.tenant_id', $1, true)", [teamId]);

  if (values.team) {
    await client.query(
      "INSERT INTO teams (id, name) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
      [teamId, values.team],
    );
  }

  // users не под RLS: пользователь глобален и может состоять в нескольких командах.
  // Повторный посев тем же адресом меняет пароль, а не заводит вторую запись.
  const { rows } = await client.query(
    `INSERT INTO users (email, name, password_hash)
     VALUES ($1, $2, $3)
     ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash
     RETURNING id`,
    [values.email, values.email.split("@")[0], passwordHash],
  );
  const userId = rows[0].id;

  await client.query(
    `INSERT INTO team_members (team_id, user_id, role)
     VALUES ($1, $2, $3)
     ON CONFLICT (team_id, user_id) DO UPDATE SET role = EXCLUDED.role`,
    [teamId, userId, values.role],
  );

  await client.query("COMMIT");
  console.log(`готово: ${values.email} — ${values.role} в команде ${teamId}`);

  if (values.team) {
    // Второй вызов нужен почти всегда: без участника нечем проверить, что
    // owner-действие ему запрещено. Печатаем команду целиком, чтобы идентификатор
    // команды не пришлось переносить руками.
    console.log("\nДобавить участника в эту же команду:");
    console.log(
      `  node apps/web/scripts/seed-auth.mjs --team-id ${teamId} \\\n` +
        `       --email member@example.com --password 'другой-пароль' --role member`,
    );
  }
} catch (error) {
  await client.query("ROLLBACK");
  console.error("посев не выполнен:", error.message);
  process.exitCode = 1;
} finally {
  await client.end();
}
