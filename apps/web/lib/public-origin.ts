/**
 * Адрес продукта для ссылок, уходящих наружу.
 *
 * ─── Что чинится ──────────────────────────────────────────────────────────
 * Публичная ссылка на отчёт строилась от `new URL(request.url).origin`, и на
 * боевом сервере получалось `https://0.0.0.0:3000/share/…`. Отправить такую
 * ссылку нельзя никому.
 *
 * Next.js слушает 0.0.0.0:3000 внутри контейнера, а наружу смотрит nginx.
 * `request.url` — адрес ВНУТРЕННЕГО запроса, а не тот, который человек видит в
 * браузере. Заметить это по коду нельзя: в разработке, где прокси нет, оба
 * совпадают, и ошибка просыпается только на сервере.
 *
 * ─── Порядок источников ───────────────────────────────────────────────────
 * 1. `AUTH_URL` — канонический адрес продукта. Он уже обязан быть верным: на
 *    нём держится вход через Auth.js, и ошибка в нём ломает логин, то есть
 *    замечается в тот же день.
 * 2. Заголовки обратного прокси. `x-forwarded-host`, если он есть, иначе
 *    `host` — nginx его сохраняет (`proxy_set_header Host $host`).
 * 3. `request.url` — последний рубеж, годный в разработке.
 *
 * ─── Почему негодный адрес — это null, а не «как-нибудь» ──────────────────
 * `0.0.0.0` и `::` означают «слушаю на всех интерфейсах», а не адрес. Ссылка с
 * ними бесполезна ровно так же, как её отсутствие, — но выглядит рабочей.
 * Вызывающий обязан обработать null и сказать правду, а не выдать бесполезное.
 */

export interface OriginSources {
  /** Значение переменной окружения AUTH_URL. */
  authUrl?: string | null;
  /** Заголовок x-forwarded-host, если прокси его ставит. */
  forwardedHost?: string | null;
  /** Заголовок host. */
  host?: string | null;
  /** Заголовок x-forwarded-proto. */
  forwardedProto?: string | null;
  /** request.url — адрес, по которому запрос пришёл в приложение. */
  requestUrl?: string | null;
}

/** Адреса, по которым снаружи не постучаться. */
const UNROUTABLE = new Set(["0.0.0.0", "::", "[::]", ""]);

function usable(origin: string | null): string | null {
  if (!origin) return null;
  try {
    const url = new URL(origin);
    if (UNROUTABLE.has(url.hostname)) return null;
    return `${url.protocol}//${url.host}`;
  } catch {
    return null;
  }
}

export function publicOrigin(sources: OriginSources): string | null {
  const fromAuth = usable(sources.authUrl ?? null);
  if (fromAuth) return fromAuth;

  const host = (sources.forwardedHost || sources.host || "").trim();
  if (host) {
    // Протокол по умолчанию https: прокси перед TLS — норма, голый http
    // наружу — исключение, и ошибиться в эту сторону безопаснее.
    const proto = (sources.forwardedProto || "https").split(",")[0].trim();
    const fromHeaders = usable(`${proto}://${host}`);
    if (fromHeaders) return fromHeaders;
  }

  return usable(sources.requestUrl ?? null);
}
