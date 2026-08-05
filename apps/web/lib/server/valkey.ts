import "server-only";

import { createClient, type RedisClientType } from "redis";

/**
 * Подключение к Valkey (задача #12, Decision Log #3).
 *
 * ─── Почему клиент один, а подписчик — отдельный ───────────────────────────
 * Соединение, вошедшее в режим подписки, не принимает обычных команд: на нём
 * доступны только SUBSCRIBE/UNSUBSCRIBE. Читать снимок прогресса тем же
 * соединением, на котором висит подписка, нельзя — GET вернёт ошибку.
 *
 * Поэтому здесь два разных вызова: `valkey()` отдаёт общий клиент для чтения
 * (он переиспользуется между запросами), а `subscriber()` создаёт СВОЁ
 * соединение на каждый SSE-поток и закрывает его при обрыве. Общий подписчик
 * не годится: отписка одного ушедшего клиента снимала бы подписку у всех
 * остальных, смотрящих тот же прогон.
 *
 * ─── Почему клиент кешируется на globalThis ────────────────────────────────
 * В dev-режиме Next пересобирает модули на каждое изменение, и модульная
 * переменная обнуляется. Без кеша на globalThis каждая пересборка оставляла бы
 * за собой открытое соединение — за час работы их набираются сотни, и упирается
 * это в лимит соединений Valkey, а выглядит как «перестал открываться прогресс».
 */

const URL_ENV = "VALKEY_URL";

function url(): string {
  const value = process.env[URL_ENV];
  if (!value) {
    throw new Error(
      `${URL_ENV} не задан — прогресс прогона отдаётся из Valkey (Decision Log #3)`,
    );
  }
  return value;
}

const cache = globalThis as unknown as { __agoraValkey?: Promise<RedisClientType> };

export function valkey(): Promise<RedisClientType> {
  if (!cache.__agoraValkey) {
    cache.__agoraValkey = (async () => {
      const client = createClient({ url: url() }) as RedisClientType;
      // Без обработчика error одна сетевая ошибка роняет процесс Node целиком:
      // EventEmitter без слушателя 'error' бросает необработанное исключение.
      client.on("error", () => {});
      await client.connect();
      return client;
    })().catch((e) => {
      // Неудачное подключение не должно застревать в кеше навсегда: иначе
      // единственный отказ Valkey при старте делает прогресс недоступным до
      // перезапуска процесса.
      cache.__agoraValkey = undefined;
      throw e;
    });
  }
  return cache.__agoraValkey;
}

/** Отдельное соединение под подписку. Закрывать обязан вызывающий. */
export async function subscriber(): Promise<RedisClientType> {
  const client = createClient({ url: url() }) as RedisClientType;
  client.on("error", () => {});
  await client.connect();
  return client;
}
