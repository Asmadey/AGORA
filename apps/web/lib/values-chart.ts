/**
 * Распределение ценностей аудитории — для плитки «Ценности ВЦИОМ».
 *
 * ─── Что это показывает, а что нет ────────────────────────────────────────
 * Сколько персон ЭТОЙ аудитории несут каждую из семнадцати ценностей. Не то,
 * что ответили реальные респонденты: подпись называет ПЕРЕЧЕНЬ, из которого
 * сделан выбор, а числа принадлежат синтетической аудитории.
 *
 * Разница существенна. В опросе ВЦИОМ «Крепкая семья» набрала 72 из 100; здесь
 * она наберёт столько, сколько выпало при генерации. Спутать одно с другим
 * значит выдать сгенерированное за измеренное — ровно та ошибка, против
 * которой построен весь продукт.
 *
 * ─── Почему все семнадцать, включая нули ──────────────────────────────────
 * Отсутствующая ценность — факт об аудитории, а не пустое место. По списку из
 * двенадцати строк нельзя понять, двенадцать их всего или пять не выпали.
 *
 * ─── Почему копия перечня, а не чтение файла ──────────────────────────────
 * Справочник живёт в `data/values/traditional_values.json` и читается воркером.
 * Браузер файлов не читает, а тащить его через серверный слой ради семнадцати
 * строк дороже, чем держать копию. Расхождение копии со справочником — молчаливый
 * дефект, поэтому его сверяет тест `values-chart.test.ts`.
 */

import rawValuesSource from "../../../data/values/values_by_age_vciom.json" with { type: "json" };

/** Семнадцать традиционных ценностей. Порядок - как в справочнике. */
export const TRADITIONAL_VALUES = [
  "Жизнь",
  "Достоинство",
  "Права и свободы человека",
  "Патриотизм",
  "Гражданственность",
  "Служение Отечеству и ответственность за его судьбу",
  "Высокие нравственные идеалы",
  "Крепкая семья",
  "Созидательный труд",
  "Приоритет духовного над материальным",
  "Гуманизм",
  "Милосердие",
  "Справедливость",
  "Коллективизм",
  "Взаимопомощь и взаимоуважение",
  "Историческая память и преемственность поколений",
  "Единство народов России",
] as const;

export interface ValuesByAgeSource {
  source: string;
  respondents: number;
  groups: readonly string[];
  shares_percent: Record<string, Record<string, number>>;
}

/** Данные ВЦИОМ передаются компоненту явно, чтобы источник был виден в DOM-узле. */
export const VCIOM_VALUES_SOURCE = rawValuesSource as ValuesByAgeSource;

/** Порог отчёта для долей по малому числу персон. На самом пороге график ещё скрывает доли. */
export const VALUES_MIN_SAMPLE_SIZE = 5;

export interface PersonaValuesInput {
  dna?: unknown;
}

export interface ValueComparisonRow {
  value: string;
  audienceCount: number;
  audiencePercent: number;
  sourcePercent: number;
}

export interface ValueComparison {
  sampleSize: number;
  smallSample: boolean;
  sampleMessage: string | null;
  sourceBasis: string;
  rows: ValueComparisonRow[];
  outsideListCount: number;
}

function objectOf(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function personaAgeGroup(persona: PersonaValuesInput): string | null {
  const demographics = objectOf(objectOf(persona.dna).demographics);
  const value = demographics.age_group;
  return typeof value === "string" && value.length > 0 ? value : null;
}

function personaValues(persona: PersonaValuesInput): string[] {
  const values = objectOf(objectOf(persona.dna).values_and_beliefs).important_values;
  if (!Array.isArray(values)) return [];
  return [...new Set(values.filter((value): value is string => typeof value === "string"))];
}

function weightedSourceShares(
  source: ValuesByAgeSource,
  ageGroups: Record<string, number>,
): { shares: Record<string, number>; basis: string } {
  const knownGroups = source.groups.filter((group) => (ageGroups[group] ?? 0) > 0);
  const knownCount = knownGroups.reduce((sum, group) => sum + ageGroups[group], 0);

  if (knownCount === 0) {
    return {
      shares: Object.fromEntries(
        TRADITIONAL_VALUES.map((value) => [value, source.shares_percent[value]?.всего ?? 0]),
      ),
      basis: "всего",
    };
  }

  const shares = Object.fromEntries(
    TRADITIONAL_VALUES.map((value) => [
      value,
      knownGroups.reduce(
        (sum, group) =>
          sum +
          (ageGroups[group] / knownCount) * (source.shares_percent[value]?.[group] ?? 0),
        0,
      ),
    ]),
  );

  return {
    shares,
    basis: knownGroups.join(", "),
  };
}

/**
 * Сравнивает доли ценностей набора с ВЦИОМ.
 *
 * Счётчик аудитории идёт по персонам, а не по назначениям: если у персоны пять
 * ценностей, она добавляет по одному к пяти строкам и один раз в знаменатель.
 * Источник сначала сворачивается по возрастному составу этого же набора.
 */
export function valueComparison(
  personas: readonly PersonaValuesInput[],
  source: ValuesByAgeSource = VCIOM_VALUES_SOURCE,
  minSampleSize = VALUES_MIN_SAMPLE_SIZE,
): ValueComparison {
  const counts: Record<string, number> = {};
  for (const value of TRADITIONAL_VALUES) counts[value] = 0;
  const ageGroups: Record<string, number> = {};
  let outside = 0;

  for (const persona of personas) {
    const ageGroup = personaAgeGroup(persona);
    if (ageGroup) ageGroups[ageGroup] = (ageGroups[ageGroup] ?? 0) + 1;
    for (const value of personaValues(persona)) {
      if (value in counts) counts[value] += 1;
      else outside += 1;
    }
  }

  const weighted = weightedSourceShares(source, ageGroups);
  const sampleSize = personas.length;
  const smallSample = sampleSize <= minSampleSize;

  return {
    sampleSize,
    smallSample,
    sampleMessage:
      sampleSize === 0
        ? "Сравнивать не с чем: в наборе пока нет персон."
        : smallSample
          ? `Малая выборка: ${sampleSize} персон. Доли могут заметно отличаться от источника случайно, это ожидаемый шум, а не дефект набора.`
          : null,
    sourceBasis: weighted.basis,
    outsideListCount: outside,
    rows: TRADITIONAL_VALUES.map((value) => ({
      value,
      audienceCount: counts[value],
      audiencePercent: sampleSize > 0 ? (counts[value] / sampleSize) * 100 : 0,
      sourcePercent: weighted.shares[value],
    })),
  };
}

export interface ValueChartRow {
  value: string;
  /** Сколько персон аудитории несут эту ценность. */
  count: number;
  /** Длина столбика: доля от САМОЙ ЧАСТОЙ, не от суммы. */
  share: number;
}

/**
 * Строки графика: все семнадцать, по убыванию частоты.
 *
 * Доля считается от максимума, а не от суммы. Каждая персона несёт пять
 * ценностей, поэтому сумма долей дала бы пятьсот процентов — столбики, которые
 * ничего не значат.
 *
 * При равном счёте порядок берётся из перечня: без этого две отрисовки одних и
 * тех же данных давали бы разный график, и читатель решил бы, что данные
 * изменились.
 */
export function valueChartRows(counts: Record<string, number>): ValueChartRow[] {
  const rank = new Map(TRADITIONAL_VALUES.map((v, i) => [v as string, i]));
  const rows = TRADITIONAL_VALUES.map((value) => ({
    value: value as string,
    count: counts[value] ?? 0,
    share: 0,
  }));

  const max = Math.max(0, ...rows.map((r) => r.count));
  for (const row of rows) {
    // Ноль в знаменателе — пустая аудитория: столбиков нет, а не NaN.
    row.share = max > 0 ? row.count / max : 0;
  }

  return rows.sort(
    (a, b) => b.count - a.count || (rank.get(a.value) ?? 0) - (rank.get(b.value) ?? 0),
  );
}

/**
 * Сколько назначений пришлось на значения ВНЕ перечня.
 *
 * У персон, созданных до 16.09.2026, встречаются «Неравенство, разделение людей
 * в соответствии с их способностями» и служебные ответы анкеты вроде
 * «Затрудняюсь ответить»: прежняя выборка брала топ-15 корпуса, а не канон.
 *
 * Отбросить их молча нельзя — читатель не узнал бы, что часть аудитории описана
 * не тем словарём. Число выносится подписью под графиком.
 */
export function outsideListCount(counts: Record<string, number>): number {
  const known = new Set<string>(TRADITIONAL_VALUES);
  return Object.entries(counts)
    .filter(([value]) => !known.has(value))
    .reduce((sum, [, n]) => sum + n, 0);
}
