import { AGE_GROUPS, GENDERS, GEOS } from "./audience.ts";

/**
 * Заземление набора персон: насколько он повторяет доли датасета.
 *
 * ─── Зачем это в интерфейсе ────────────────────────────────────────────────
 * Метрика `persona_grounding` считается в `evals/check.py` и живёт в отчёте
 * гейта — то есть там, куда владелец продукта не заходит. Между тем вопрос
 * «похожа ли собранная аудитория на датасет» задают ровно в тот момент, когда
 * смотрят на набор, и отвечать на него приходилось на слово.
 *
 * ─── Почему считается здесь, а не гоняется eval ────────────────────────────
 * Гонять eval из веба нельзя: он читает артефакты прогона с диска. Но считать
 * тут нечего сложного — это доли по трём измерениям и модуль разности. Данные
 * для обеих сторон уже лежат в базе: доли датасета берутся из СЛЕПКА, по
 * которому набор собран (`corpus_snapshots.records`), а не из датасета на
 * сегодня. Датасет правят, и сравнение с его текущей версией отвечало бы на
 * другой вопрос — «похож ли старый набор на новые данные».
 *
 * ─── Порог ─────────────────────────────────────────────────────────────────
 * Тот же, что в `evals/check.py` (GROUNDING_PROP_TOL). Два числа в двух языках
 * разъезжаются молча, поэтому равенство закреплено тестом, который читает
 * check.py и сверяет.
 */

/** Допустимое расхождение доли. Совпадает с GROUNDING_PROP_TOL в evals/check.py. */
export const GROUNDING_PROP_TOL = 0.1;

export interface GroundingRow {
  dimension: string;
  bucket: string;
  real: number;
  generated: number;
  delta: number;
  ok: boolean;
}

export interface GroundingReport {
  rows: GroundingRow[];
  /** Расхождения выше порога. Пусто — набор заземлён. */
  deviations: GroundingRow[];
  /** Сравнивать было не с чем: пустой слепок или пустой набор. */
  comparable: boolean;
}

const DIMENSIONS: [string, string, readonly string[]][] = [
  ["age_group", "Возраст", AGE_GROUPS],
  ["geo", "Тип населённого пункта", GEOS],
  ["gender", "Пол", GENDERS],
];

/**
 * Доли по перечню корзин.
 *
 * Знаменатель — число записей, ПОПАВШИХ в перечень, а не всего. Значение вне
 * перечня (опечатка в датасете, новая категория) иначе размывало бы все доли
 * сразу, и расхождение выглядело бы равномерным сдвигом вместо одной кривой
 * записи.
 */
function proportions(
  values: readonly (string | undefined)[],
  buckets: readonly string[],
): Record<string, number> {
  const known = values.filter((v): v is string => !!v && buckets.includes(v));
  const out: Record<string, number> = {};
  for (const b of buckets) out[b] = 0;
  if (known.length === 0) return out;
  for (const v of known) out[v] += 1 / known.length;
  return out;
}

function socioOf(record: Record<string, unknown>): Record<string, unknown> {
  const socio = record.socio_demographics;
  return socio && typeof socio === "object" ? (socio as Record<string, unknown>) : {};
}

function demographicsOf(dna: unknown): Record<string, unknown> {
  if (!dna || typeof dna !== "object") return {};
  const demo = (dna as Record<string, unknown>).demographics;
  return demo && typeof demo === "object" ? (demo as Record<string, unknown>) : {};
}

export function groundingReport(
  // Структурный тип, а не импорт `Persona`: считать здесь нужно ровно две
  // величины из `dna`, и требовать целую доменную модель значило бы тащить в
  // чистую функцию половину серверного слоя вместе с базой.
  personas: readonly { dna?: unknown }[],
  snapshotRecords: readonly Record<string, unknown>[],
): GroundingReport {
  if (personas.length === 0 || snapshotRecords.length === 0) {
    return { rows: [], deviations: [], comparable: false };
  }

  const rows: GroundingRow[] = [];
  for (const [field, label, buckets] of DIMENSIONS) {
    const real = proportions(
      snapshotRecords.map((r) => socioOf(r)[field] as string | undefined),
      buckets,
    );
    const generated = proportions(
      personas.map((p) => demographicsOf(p.dna)[field] as string | undefined),
      buckets,
    );
    for (const bucket of buckets) {
      const delta = Math.abs(generated[bucket] - real[bucket]);
      rows.push({
        dimension: label,
        bucket,
        real: real[bucket],
        generated: generated[bucket],
        delta,
        // Строгое сравнение: ровно на пороге считается допустимым, как в
        // check.py (`if d > GROUNDING_PROP_TOL`).
        ok: delta <= GROUNDING_PROP_TOL,
      });
    }
  }

  return { rows, deviations: rows.filter((r) => !r.ok), comparable: true };
}
