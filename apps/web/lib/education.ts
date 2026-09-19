/** Правила критерия образования и его объяснение на шаге «Аудитория». */

export const EDUCATION_OPTIONS = ["есть высшее", "нет высшего"] as const;
export type EducationCriterion = (typeof EDUCATION_OPTIONS)[number];

export const EDUCATION_TOOLTIP = {
  single:
    "При выборе одного варианта его доля будет 100 %, а возрастной состав аудитории изменится: у групп, где высшее невозможно или редко, вес упадёт.",
  both:
    "При выборе обоих вариантов доли берутся из таблицы по возрасту: 18-24 — 5 %, 25-34 — 41 %, 35-44 — 36 %, 45-59 — 27 %, 60+ — 19 %.",
  source:
    "Источник: Микроперепись населения России 2015 г. (Росстат/ВШЭ), агрегация автором по бинам графика.",
  caveat:
    "По корпусу AGORA образование не спрашивали, поэтому доли внешние, а цифра 18-24 оценочная.",
} as const;

const AGE_GROUP_ORDER = ["14-17", "18-24", "25-34", "35-44", "45-59", "60+"] as const;

// Состав возрастных групп корпуса нужен только для предварительного показа
// следствия. Доли образования ниже не из корпуса, а из паспорта
// data/demography/education_by_age.json.
const CORPUS_AGE_COUNTS: Record<(typeof AGE_GROUP_ORDER)[number], number> = {
  "14-17": 3,
  "18-24": 18,
  "25-34": 43,
  "35-44": 68,
  "45-59": 28,
  "60+": 5,
};

const HIGHER_SHARES: Record<(typeof AGE_GROUP_ORDER)[number], number> = {
  "14-17": 0,
  "18-24": 0.05,
  "25-34": 0.41,
  "35-44": 0.36,
  "45-59": 0.27,
  "60+": 0.19,
};

function higherWeight(group: string, selected: EducationCriterion): number {
  const share = HIGHER_SHARES[group as keyof typeof HIGHER_SHARES] ?? 0;
  if (selected === "есть высшее") {
    const eligible = group === "18-24" ? 3 / 7 : group === "14-17" ? 0 : 1;
    return share === 0 ? 0 : share / eligible;
  }
  return 1 - share;
}

export function educationIntersectionError(
  ageGroups: readonly string[],
  education: readonly string[],
): string | null {
  if (education.length !== 1 || education[0] !== "есть высшее") return null;
  const groups = ageGroups.length > 0 ? ageGroups : [...AGE_GROUP_ORDER];
  if (groups.some((group) => higherWeight(group, "есть высшее") > 0)) return null;
  return `образование: выбранные значения (есть высшее) не пересекаются с возрастными группами (${groups.join(", ")}) — генерация невозможна`;
}

/** Показывает перевзвешенный возрастной состав до оплаты генерации. */
export function educationAgePreview(
  ageGroups: readonly string[],
  education: readonly string[],
): string | null {
  if (education.length !== 1 || !EDUCATION_OPTIONS.includes(education[0] as EducationCriterion)) {
    return null;
  }
  const selected = education[0] as EducationCriterion;
  const groups = ageGroups.length > 0 ? ageGroups : [...AGE_GROUP_ORDER];
  const weighted = groups.map((group) => ({
    group,
    weight:
      (CORPUS_AGE_COUNTS[group as keyof typeof CORPUS_AGE_COUNTS] ?? 0) *
      higherWeight(group, selected),
  }));
  const total = weighted.reduce((sum, row) => sum + row.weight, 0);
  if (total === 0) return `выбрано «${selected}»: пересечение с возрастом пусто`;
  const parts = weighted.map(({ group, weight }) => `${group} → ${Math.round((weight / total) * 100)} %`);
  return `выбрано «${selected}»: ${parts.join(", ")}`;
}
