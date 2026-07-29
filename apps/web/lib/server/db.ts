import "server-only";

import { readFileSync } from "node:fs";
import { Pool, type PoolClient } from "pg";

/**
 * Доступ к Postgres под арендатором (задачи #2, #3).
 *
 * Всё обращение приложения к данным идёт через withTenant/withoutTenant. Прямой
 * экспорт пула наружу намеренно отсутствует: запрос вне транзакции с тенант-
 * контекстом либо не увидит ничего (RLS по умолчанию запрещает), либо — если
 * кто-то отключит политику — увидит чужое. Единая точка входа делает это
 * невозможным по конструкции, а не по договорённости.
 *
 * ─── Три вещи, на которых здесь легко ошибиться ────────────────────────
 *
 * 1. `SET LOCAL app.tenant_id = $1` не работает. Команда SET в PostgreSQL не
 *    принимает параметры запроса; единственная альтернатива — склеить значение
 *    в текст SQL, то есть отдать арендатору управление собственным контекстом.
 *    Правильный вызов — функция `set_config(name, value, is_local)`: она обычная,
 *    значит параметризуется, а третий аргумент true даёт ту же семантику SET LOCAL.
 *
 * 2. Соединение берётся из пула и возвращается в него. Настройка, поставленная
 *    без is_local, переживёт возврат и достанется следующему арендатору. Поэтому
 *    контекст ставится только внутри транзакции и только локально.
 *
 * 3. agora_login объявлен NOINHERIT (миграция 04): сам по себе он не имеет прав
 *    на таблицы, их даёт `SET LOCAL ROLE agora_app`. Это не формальность —
 *    забытый вызов роняет запрос с «permission denied», а не тихо отдаёт данные
 *    в обход политик.
 */

const APP_ROLE = "agora_app";

let pool: Pool | null = null;

function sslOptions() {
  const caPath = process.env.PGSSLROOTCERT;
  if (!caPath) return undefined;
  // verify-full: проверяем и цепочку, и имя хоста. Понижение до rejectUnauthorized:false
  // здесь недопустимо — в строке подключения едет пароль.
  return { ca: readFileSync(caPath, "utf8"), rejectUnauthorized: true };
}

function getPool(): Pool {
  if (pool) return pool;

  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new Error("DATABASE_URL не задан: серверные маршруты не могут работать без базы");
  }

  pool = new Pool({
    connectionString,
    ssl: sslOptions(),
    max: Number(process.env.PGPOOL_MAX ?? 10),
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 10_000,
  });

  // Соединение может умереть в простое (managed-инстанс, перезапуск, сеть).
  // Без обработчика ошибка простаивающего клиента валит процесс Node целиком.
  pool.on("error", (err) => {
    console.error("[db] ошибка простаивающего соединения:", err.message);
  });

  return pool;
}

async function inTransaction<T>(
  tenantId: string | null,
  fn: (client: PoolClient) => Promise<T>,
): Promise<T> {
  const client = await getPool().connect();
  try {
    await client.query("BEGIN");
    await client.query(`SET LOCAL ROLE ${APP_ROLE}`);
    if (tenantId !== null) {
      await client.query("SELECT set_config('app.tenant_id', $1, true)", [tenantId]);
    }
    const result = await fn(client);
    await client.query("COMMIT");
    return result;
  } catch (error) {
    try {
      await client.query("ROLLBACK");
    } catch {
      // Соединение уже мертво — откатывать нечего, важнее не потерять исходную ошибку.
    }
    throw error;
  } finally {
    client.release();
  }
}

/**
 * Работа от имени арендатора. Всё, что выполнится внутри, увидит ровно его строки:
 * политики RLS сверяются с app.current_tenant(), а он читает поставленный здесь ключ.
 */
export function withTenant<T>(tenantId: string, fn: (client: PoolClient) => Promise<T>): Promise<T> {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(tenantId)) {
    // Значение приезжает из подписанного токена, но подпись не делает его uuid.
    throw new Error("tenantId не является uuid");
  }
  return inTransaction(tenantId, fn);
}

/**
 * Работа без арендатора — только для функций идентичности из миграции 05,
 * которым тенант ещё неизвестен (поиск пользователя при входе, список команд).
 * Прикладные таблицы отсюда не видны: без контекста политики отдают пустоту.
 */
export function withoutTenant<T>(fn: (client: PoolClient) => Promise<T>): Promise<T> {
  return inTransaction(null, fn);
}

/** Закрытие пула — для скриптов и тестов, чтобы процесс не висел на открытых сокетах. */
export async function closePool(): Promise<void> {
  if (!pool) return;
  const p = pool;
  pool = null;
  await p.end();
}
