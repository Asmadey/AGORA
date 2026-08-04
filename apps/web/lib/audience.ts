/**
 * Критерии отбора аудитории (задача #9, PRD §10).
 *
 * Контракт между шагом визарда, маршрутом API и генератором персон в воркере —
 * ровно как settings.ts между интерфейсом и config.py. Списки допустимых
 * значений здесь закрытые, и это не формальность: генератор сэмплирует из
 * распределений корпуса, и значение, которого в корпусе нет, даёт не «мало
 * персон», а пустую выборку.
 *
 * ─── Почему пол обязателен наравне с возрастом и гео ───────────────────────
 * До #9 guard шага требовал размер, возраст и гео, а пол в контексте машины
 * отсутствовал вовсе. При этом в корпусе он распределён 110/55 и участвует в
 * калибровке баллов. Поле, которое есть в интерфейсе и ни на что не влияет, —
 * худший из вариантов: пользователь считает, что задал критерий, а он молча
 * теряется по дороге.
 *
 * ─── Образование ──────────────────────────────────────────────────────────
 * Объявлено в cdd задачи, но в корпусе такого поля НЕТ ни у одной из 165
 * записей (замерено 04.08.2026). Поэтому оно есть в контракте, но помечено как
 * незаземлённое: см. audience-grounding.ts, где охват считается по корпусу, а
 * не по этому файлу. Убрать его из контракта нельзя — оно в приёмке; выдать
 * молча за равноправный критерий тоже нельзя — персоны по нему не заземлены, а
 * persona_grounding эту незаземлённость не увидит: метрика смотрит только на
 * age_group, geo и gender.
 */

export const AGE_GROUPS = ["14-17", "18-24", "25-34", "35-44", "45-59", "60+"] as const;
export type AgeGroup = (typeof AGE_GROUPS)[number];

export const GEOS = ["столицы", "центры субъектов", "иные НП"] as const;
export type Geo = (typeof GEOS)[number];

export const GENDERS = ["муж", "жен"] as const;
export type Gender = (typeof GENDERS)[number];

/**
 * Уровни образования. В корпусе не представлены — критерий сквозной, но
 * незаземлённый. Значения взяты по шкале Росстата, чтобы при появлении данных
 * их не пришлось переименовывать.
 */
export const EDUCATION_LEVELS = [
  "среднее",
  "среднее специальное",
  "высшее",
] as const;
export type EducationLevel = (typeof EDUCATION_LEVELS)[number];

/** Дефолт размера — 20 (приёмка #9). */
export const DEFAULT_AUDIENCE_SIZE = 20;
export const AUDIENCE_SIZE_BOUNDS = { min: 1, max: 100 } as const;

export interface AudienceCriteria {
  size: number;
  ageGroups: AgeGroup[];
  geos: Geo[];
  genders: Gender[];
  /** Пустой массив — критерий не задан. Незаземлён, см. шапку файла. */
  education: EducationLevel[];
}

export const DEFAULT_CRITERIA: AudienceCriteria = {
  size: DEFAULT_AUDIENCE_SIZE,
  ageGroups: ["25-34", "35-44", "45-59"],
  geos: ["столицы", "центры субъектов"],
  genders: ["муж", "жен"],
  education: [],
};

/**
 * Что выбрано на шаге: сгенерировать новый набор или взять существующий.
 *
 * Размеченное объединение, а не булев флаг рядом с критериями. При булевом
 * флаге состояние «reuse=true, но набор не выбран» представимо, и обработать
 * его пришлось бы в каждом потребителе — то есть рано или поздно где-то не
 * обработать.
 */
export type AudienceChoice =
  | { kind: "generate"; criteria: AudienceCriteria }
  | { kind: "reuse"; personaSetId: string };

function subset<T extends string>(value: unknown, allowed: readonly T[]): T[] | null {
  if (!Array.isArray(value)) return null;
  const out: T[] = [];
  for (const v of value) {
    if (typeof v !== "string" || !allowed.includes(v as T)) return null;
    if (!out.includes(v as T)) out.push(v as T);
  }
  return out;
}

/**
 * Разбор тела запроса. Возвращает либо выбор, либо перечень претензий — не
 * бросает: маршруту нужно ответить 400 с внятным телом, а не пятисоткой.
 */
export function parseAudienceChoice(
  input: unknown,
): { ok: true; value: AudienceChoice } | { ok: false; errors: string[] } {
  if (typeof input !== "object" || input === null) {
    return { ok: false, errors: ["тело запроса должно быть объектом"] };
  }
  const raw = input as Record<string, unknown>;

  // Существующий набор — отдельная ветка целиком: критерии в ней не нужны и не
  // проверяются, потому что генерации не будет.
  if (typeof raw.personaSetId === "string" && raw.personaSetId.length > 0) {
    return { ok: true, value: { kind: "reuse", personaSetId: raw.personaSetId } };
  }

  const errors: string[] = [];

  const size = raw.size;
  if (
    typeof size !== "number" ||
    !Number.isInteger(size) ||
    size < AUDIENCE_SIZE_BOUNDS.min ||
    size > AUDIENCE_SIZE_BOUNDS.max
  ) {
    errors.push(
      `size: целое в диапазоне ${AUDIENCE_SIZE_BOUNDS.min}–${AUDIENCE_SIZE_BOUNDS.max}`,
    );
  }

  const ageGroups = subset(raw.ageGroups, AGE_GROUPS);
  if (!ageGroups || ageGroups.length === 0) {
    errors.push(`ageGroups: непустой набор из ${AGE_GROUPS.join(" | ")}`);
  }

  const geos = subset(raw.geos, GEOS);
  if (!geos || geos.length === 0) {
    errors.push(`geos: непустой набор из ${GEOS.join(" | ")}`);
  }

  const genders = subset(raw.genders, GENDERS);
  if (!genders || genders.length === 0) {
    errors.push(`genders: непустой набор из ${GENDERS.join(" | ")}`);
  }

  // Образование необязательно: незаземлённый критерий не должен блокировать
  // запуск. Но если задано — значение обязано быть из списка.
  const education = raw.education === undefined ? [] : subset(raw.education, EDUCATION_LEVELS);
  if (!education) {
    errors.push(`education: набор из ${EDUCATION_LEVELS.join(" | ")} либо пусто`);
  }

  if (errors.length > 0) return { ok: false, errors };

  return {
    ok: true,
    value: {
      kind: "generate",
      criteria: {
        size: size as number,
        ageGroups: ageGroups as AgeGroup[],
        geos: geos as Geo[],
        genders: genders as Gender[],
        education: education as EducationLevel[],
      },
    },
  };
}

/**
 * Критерии в поля GenerationConfig воркера.
 *
 * Имена намеренно snake_case: это payload задачи, а не объект интерфейса.
 * Переименование на границе — единственное место, где два языка встречаются, и
 * держать его надо здесь, а не размазывать по вызывающим.
 */
export function toGenerationConfig(
  criteria: AudienceCriteria,
  seed: number,
): Record<string, unknown> {
  return {
    size: criteria.size,
    seed,
    age_groups: criteria.ageGroups,
    geos: criteria.geos,
    genders: criteria.genders,
    education: criteria.education,
  };
}
