/**
 * Потребление и расходы по дням — раздел «Статистика».
 *
 * ─── Что за данные ────────────────────────────────────────────────────────
 * API контроля затрат cloud.ru отдаёт плоский список строк потребления: дата
 * (`usedate`), название SKU (`servname`), объём (`usefact`) и две суммы —
 * `amount` без НДС и `amount_nds` с ним. Здесь этот список сворачивается в
 * таблицу по дням.
 *
 * ─── Почему модель определяется по названию SKU ───────────────────────────
 * Другого признака у строки нет: идентификаторы SKU у провайдера непрозрачны и
 * меняются при смене тарифа, а название — то, что видно в его же кабинете.
 *
 * ─── Почему незнакомая строка не выбрасывается ────────────────────────────
 * Она попадает в отдельную величину `other` и в «Итого». Молчаливое отбрасывание
 * означало бы, что подключение третьей модели уменьшает показанные расходы, — и
 * расхождение со счётом провайдера пришлось бы искать вручную.
 *
 * ─── Про единицу объёма ───────────────────────────────────────────────────
 * `usefact` приходит уже в МИЛЛИОНАХ токенов: у SKU такая тарифная единица.
 * Поэтому число не делится и не сокращается — показывается как есть, с четырьмя
 * знаками, как в кабинете провайдера.
 */

export interface ConsumptionItem {
  usedate: string;
  servname: string;
  /** Объём в тарифных единицах SKU — для этих моделей это миллионы токенов. */
  usefact: number;
  /** Сумма без НДС. */
  amount: number;
  /** Сумма с НДС. */
  amount_nds: number;
}

export type ModelKey = "vision" | "text" | "other";

/**
 * По каким подстрокам названия SKU узнаются модели продукта.
 *
 * Списком, а не одной строкой: провайдер добавляет к названию суффиксы вида
 * «(Vision)» и меняет их между тарифами.
 */
const MATCHERS: { key: Exclude<ModelKey, "other">; needles: string[] }[] = [
  { key: "vision", needles: ["Qwen3 VL", "qwen3-vl"] },
  { key: "text", needles: ["Qwen3.6-35B", "qwen3.6-35b"] },
];

export const MODEL_LABELS: Record<ModelKey, string> = {
  vision: "Vision Model (Qwen3 VL 30B)",
  text: "LLM text (Qwen3.6-35B-A3B)",
  other: "Прочее",
};

export interface Bucket {
  /** Миллионы токенов. */
  tokens: number;
  /** Рубли с НДС. */
  rub: number;
  /** Рубли без НДС. */
  rubNoVat: number;
}

export interface DayRow {
  /** ISO-дата, YYYY-MM-DD. Показывается через formatDateRu. */
  date: string;
  vision: Bucket;
  text: Bucket;
  other: Bucket;
  totalRub: number;
  totalRubNoVat: number;
}

/** Копейки. Деньги складываются в рублях, поэтому округляем на каждом шаге. */
const money = (v: number) => Math.round(v * 100) / 100;
/** Объём показывается с четырьмя знаками — как в кабинете провайдера. */
const volume = (v: number) => Math.round(v * 10000) / 10000;

const empty = (): Bucket => ({ tokens: 0, rub: 0, rubNoVat: 0 });

function keyOf(servname: string): ModelKey {
  const name = servname ?? "";
  for (const { key, needles } of MATCHERS) {
    if (needles.some((n) => name.includes(n))) return key;
  }
  return "other";
}

function add(bucket: Bucket, item: ConsumptionItem): Bucket {
  return {
    tokens: volume(bucket.tokens + (item.usefact || 0)),
    rub: money(bucket.rub + (item.amount_nds || 0)),
    rubNoVat: money(bucket.rubNoVat + (item.amount || 0)),
  };
}

export function aggregateByDay(items: ConsumptionItem[]): DayRow[] {
  const byDate = new Map<string, DayRow>();

  for (const item of items ?? []) {
    const date = String(item.usedate ?? "").slice(0, 10);
    if (!date) continue;

    const row =
      byDate.get(date) ??
      { date, vision: empty(), text: empty(), other: empty(), totalRub: 0, totalRubNoVat: 0 };

    const key = keyOf(item.servname);
    row[key] = add(row[key], item);
    byDate.set(date, row);
  }

  const rows = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  for (const row of rows) {
    row.totalRub = money(row.vision.rub + row.text.rub + row.other.rub);
    row.totalRubNoVat = money(row.vision.rubNoVat + row.text.rubNoVat + row.other.rubNoVat);
  }
  return rows;
}

export interface Totals {
  vision: Bucket;
  text: Bucket;
  other: Bucket;
  totalRub: number;
  totalRubNoVat: number;
  days: number;
}

/**
 * Суммы по каждой колонке.
 *
 * Считаются по ТЕМ ЖЕ строкам, что показаны на экране, а не отдельным запросом:
 * иначе фильтр по модели или по датам менял бы таблицу и не менял итог, и
 * который из них правдив — было бы не понять.
 */
export function totalsOf(rows: DayRow[]): Totals {
  const acc: Totals = {
    vision: empty(),
    text: empty(),
    other: empty(),
    totalRub: 0,
    totalRubNoVat: 0,
    days: rows.length,
  };
  for (const row of rows) {
    for (const key of ["vision", "text", "other"] as const) {
      acc[key] = {
        tokens: volume(acc[key].tokens + row[key].tokens),
        rub: money(acc[key].rub + row[key].rub),
        rubNoVat: money(acc[key].rubNoVat + row[key].rubNoVat),
      };
    }
    acc.totalRub = money(acc.totalRub + row.totalRub);
    acc.totalRubNoVat = money(acc.totalRubNoVat + row.totalRubNoVat);
  }
  return acc;
}

/** `2026-08-12` → `12.08.2026`. Формат просил владелец. */
export function formatDateRu(iso: string): string {
  const [y, m, d] = String(iso ?? "").slice(0, 10).split("-");
  return y && m && d ? `${d}.${m}.${y}` : String(iso ?? "");
}

export type Preset = "7d" | "month";

/**
 * Границы периода для пресета. Обе включительно, в ISO-датах.
 *
 * «7 дней» — сегодня и шесть предыдущих, а не «неделя назад»: человек, который
 * смотрит расход за неделю, ждёт увидеть в нём сегодняшний день.
 */
export function presetRange(preset: Preset, today: Date = new Date()): { from: string; to: string } {
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const to = iso(today);
  if (preset === "month") {
    return { from: `${to.slice(0, 7)}-01`, to };
  }
  const from = new Date(today.getTime() - 6 * 24 * 3600 * 1000);
  return { from: iso(from), to };
}
