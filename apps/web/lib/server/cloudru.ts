import "server-only";

import type { ConsumptionItem } from "@/lib/consumption";

/**
 * Клиент API контроля затрат cloud.ru.
 *
 * Две ручки: выпуск токена в IAM и постраничное чтение потребления. Обе описаны
 * в `docs/api cloud.ru` (каталог держится вне git — в примерах провайдера ключи
 * лежат открытым текстом).
 *
 * ─── Почему ключи только из окружения ─────────────────────────────────────
 * Это ключи биллинга: ими читают расходы всего договора. В базе продукта им
 * делать нечего — там они размножились бы по резервным копиям без способа
 * отозвать, ровно как ключ провайдера моделей, который поэтому и лежит
 * зашифрованным в одной колонке.
 *
 * ─── Почему токен кэшируется в памяти ─────────────────────────────────────
 * IAM отдаёт его на час. Запрашивать заново на каждое открытие страницы значит
 * добавлять к ней лишний круг и упираться в лимиты провайдера на ровном месте.
 * Память процесса — правильное место: токен переживает несколько запросов и не
 * переживает перезапуск.
 */

const IAM_URL = "https://iam.api.cloud.ru/api/v1/auth/token";
const CONSUMPTION_URL = "https://organization.api.cloud.ru/v2/consumption";

/** Сколько строк просить за раз. Больше — меньше кругов, но тяжелее ответ. */
const PAGE_SIZE = 500;

/** Потолок страниц. Защита от бесконечного цикла, если провайдер зациклит токен. */
const MAX_PAGES = 40;

/** За сколько до истечения обновлять токен. */
const REFRESH_MARGIN_MS = 60_000;

export class CloudRuNotConfigured extends Error {}

let cached: { token: string; projectId: string; expiresAt: number } | null = null;

function credentials(): { keyId: string; secret: string; projectId: string | null } {
  const keyId = process.env.CLOUDRU_KEY_ID;
  const secret = process.env.CLOUDRU_KEY_SECRET;
  if (!keyId || !secret) {
    throw new CloudRuNotConfigured(
      "CLOUDRU_KEY_ID и CLOUDRU_KEY_SECRET не заданы: раздел «Статистика» читает расходы " +
        "по API контроля затрат, и без ключей ему неоткуда их взять",
    );
  }
  return { keyId, secret, projectId: process.env.CLOUDRU_PROJECT_ID || null };
}

async function authorize(): Promise<{ token: string; projectId: string }> {
  if (cached && cached.expiresAt - REFRESH_MARGIN_MS > Date.now()) return cached;

  const { keyId, secret, projectId } = credentials();
  const res = await fetch(IAM_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keyId, secret }),
    cache: "no-store",
  });
  if (!res.ok) {
    // Тело ответа НЕ пересказываем: в нём бывает эхо запроса вместе с ключом.
    throw new Error(`IAM отказал: ${res.status}`);
  }

  const data = (await res.json()) as {
    access_token?: string;
    expires_in?: number;
    project_id?: string;
  };
  if (!data.access_token) throw new Error("IAM не вернул access_token");

  cached = {
    token: data.access_token,
    projectId: projectId ?? data.project_id ?? "",
    expiresAt: Date.now() + (data.expires_in ?? 3600) * 1000,
  };
  return cached;
}

/**
 * Строки потребления за период, включительно по обеим границам.
 *
 * Страницы вычерпываются до конца: показать первую и промолчать про остальные
 * значило бы занизить расходы тем сильнее, чем длиннее период, — и заметить это
 * можно было бы только сверкой со счётом.
 */
export async function fetchConsumption(from: string, to: string): Promise<ConsumptionItem[]> {
  const { token, projectId } = await authorize();

  const out: ConsumptionItem[] = [];
  let pageToken: string | null = null;

  for (let page = 0; page < MAX_PAGES; page += 1) {
    const url = new URL(CONSUMPTION_URL);
    if (projectId) url.searchParams.set("project_ids", projectId);
    url.searchParams.set("start_date", `${from}T00:00:00Z`);
    // Верхняя граница включительна: провайдер фильтрует по моменту, а человек
    // выбирает день. Без конца суток последний день пропадал бы из отчёта.
    url.searchParams.set("end_date", `${to}T23:59:59Z`);
    url.searchParams.set("page_filter.page_size", String(PAGE_SIZE));
    if (pageToken) url.searchParams.set("page_filter.page_token", pageToken);

    const res: Response = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`API затрат отказал: ${res.status}`);

    const data = (await res.json()) as {
      consumptions?: ConsumptionItem[];
      next_page_token?: string;
    };
    const items = data.consumptions ?? [];
    out.push(...items);

    pageToken = data.next_page_token || null;
    if (!pageToken || items.length === 0) break;
  }

  return out;
}
