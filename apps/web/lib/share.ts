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
 * Выпуск токена и его отпечаток живут в lib/server/share-token.ts: они тянут
 * `node:crypto`, а этот модуль импортирует клиентский диалог.
 *
 * ─── Почему адрес строится от источника запроса ───────────────────────────
 * У продукта нет постоянного домена: он живёт на sslip.io по адресу сервера.
 * Любая константа здесь разойдётся с реальностью — ровно это и произошло.
 */

export type Ttl = "24h" | "7d" | "30d" | "never";

export type ShareLinkState = "active" | "expired" | "revoked" | "missing";

export interface ActiveShare {
  id: string;
  createdAt: string;
  expiresAt: string | null;
  scope: "full" | "aggregate";
  viewCount: number;
}

/**
 * These statements are kept beside the public-link rules so the route cannot
 * silently drift back to joining the empty `reports` table. The route still
 * runs them through `withTenant`, so RLS remains the tenant boundary.
 */
export const ACTIVE_SHARES_QUERY = `
  SELECT s.id,
         s.created_at,
         s.expires_at,
         s.scope,
         COUNT(v.id)::int AS view_count
    FROM report_shares s
    LEFT JOIN report_share_views v ON v.share_id = s.id
   WHERE s.task_id = $1::uuid
     AND s.revoked_at IS NULL
     AND (s.expires_at IS NULL OR s.expires_at > now())
   GROUP BY s.id, s.created_at, s.expires_at, s.scope
   ORDER BY s.created_at DESC`;

export const REVOKE_ALL_SHARES_QUERY = `
  UPDATE report_shares
     SET revoked_at = now()
   WHERE task_id = $1::uuid
     AND revoked_at IS NULL`;

export const REVOKE_SHARE_QUERY = `
  UPDATE report_shares
     SET revoked_at = now()
   WHERE id = $1::uuid
     AND task_id = $2::uuid
     AND revoked_at IS NULL`;

/**
 * До миграции 52 публичная роль по RLS видела только живую строку. После
 * миграции, которая возвращает строку для определения её состояния, эта чистая
 * функция держит различие HTTP-ответов в одном проверенном месте, а не
 * дублирует расчёт дат в обработчиках страницы и маршрута.
 */
export function classifyShareState(
  row: { revokedAt: string | Date | null; expiresAt: string | Date | null } | null,
  now: Date = new Date(),
): ShareLinkState {
  if (!row) return "missing";
  if (row.revokedAt !== null) return "revoked";
  if (row.expiresAt !== null && new Date(row.expiresAt).getTime() <= now.getTime()) {
    return "expired";
  }
  return "active";
}

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

export function shareUrl(origin: string, token: string): string {
  return `${origin.replace(/\/+$/, "")}/share/${token}`;
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
