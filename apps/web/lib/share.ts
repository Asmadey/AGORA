import { createHash, randomBytes } from "node:crypto";

/**
 * Публичная ссылка на отчёт (#29): выпуск токена и построение адреса.
 *
 * ─── Что здесь чинится ────────────────────────────────────────────────────
 * Диалог выдумывал токен четырьмя вызовами `Math.random` прямо в браузере и
 * показывал ссылку на `https://agora.studio/s/…` — домен, которого у продукта
 * нет. Ничего не сохранялось, отзывать было нечего, открывать — некуда.
 *
 * Со стороны отличить это от работающей функции было нельзя: диалог
 * открывается, срок выбирается, ссылка копируется в буфер. Обнаружить можно
 * было, только отправив её кому-нибудь.
 *
 * ─── Почему токен выпускает сервер ────────────────────────────────────────
 * `Math.random` не криптографический: последовательность предсказуема по
 * нескольким выданным значениям. Для ссылки, открывающей отчёт БЕЗ входа в
 * систему, это то же самое, что открытый доступ.
 *
 * ─── Почему в базу идёт хеш ───────────────────────────────────────────────
 * Так заведена схема: `report_shares.token_hash`, а политика читает
 * `app.current_share_token_hash()` — SHA-256 от `app.share_token` в hex.
 * Утечка дампа базы не даёт доступа к отчётам.
 *
 * ─── Почему адрес строится от источника запроса ───────────────────────────
 * У продукта нет постоянного домена: он живёт на sslip.io по адресу сервера.
 * Любая константа здесь разойдётся с реальностью — ровно это и произошло.
 */

/** Сколько байт энтропии в токене. 32 — как у ключа сессии. */
const TOKEN_BYTES = 32;

export type Ttl = "24h" | "7d" | "30d" | "never";

export const TTL_OPTIONS: { value: Ttl; label: string }[] = [
  { value: "24h", label: "24 часа" },
  { value: "7d", label: "7 дней" },
  { value: "30d", label: "30 дней" },
  { value: "never", label: "бессрочно" },
];

const TTL_HOURS: Record<Exclude<Ttl, "never">, number> = {
  "24h": 24,
  "7d": 24 * 7,
  "30d": 24 * 30,
};

export function newToken(): string {
  return randomBytes(TOKEN_BYTES).toString("base64url");
}

/** SHA-256 в hex — ровно то, что считает `app.current_share_token_hash()`. */
export function hashToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

export function shareUrl(origin: string, token: string): string {
  return `${origin.replace(/\/+$/, "")}/s/${token}`;
}

/**
 * Срок жизни → момент истечения. `null` — бессрочная ссылка.
 *
 * Неизвестное значение — исключение, а не тихий откат на «навсегда»: опечатка
 * в поле сделала бы ссылку бессрочной, и заметить это было бы нечем.
 */
export function ttlToExpiry(ttl: Ttl, now: Date = new Date()): Date | null {
  if (ttl === "never") return null;
  const hours = TTL_HOURS[ttl];
  if (hours === undefined) {
    throw new Error(`неизвестный срок жизни ссылки: ${ttl}`);
  }
  return new Date(now.getTime() + hours * 3600 * 1000);
}
