import "server-only";

import { AGE_GROUPS, GENDERS, GEOS } from "@/lib/audience";
import { loadSessions } from "@/lib/server/corpus";

/**
 * Охват критериев аудитории grounding-корпусом (задача #9).
 *
 * ─── Зачем это отдельный модуль ────────────────────────────────────────────
 * Приёмка #9 требует пометить гео «иные НП» как слабо заземлённое: в корпусе
 * таких записей нет. Написать это строкой в компоненте было бы на два порядка
 * короче — и неверно по трём причинам:
 *
 * 1. Число перестанет быть правдой. Паспорт корпуса (corpus.meta.json) прямо
 *    описывает процедуру добавления исследования, то есть пополнение — это
 *    ожидаемое событие, а не гипотетическое. Захардкоженное «0 из 165» в этот
 *    день станет ложью, которую никто не заметит: предупреждение продолжит
 *    показываться, а данные уже появятся.
 *
 * 2. «Иные НП» — не единственный незаземлённый критерий. Замерено 04.08.2026:
 *    поля education нет ни у одной из 165 записей. Это сильнее, чем пустое
 *    значение существующего измерения, и persona_grounding этого не увидит —
 *    метрика сверяет только age_group, geo и gender. Считающий охват механизм
 *    ловит оба случая одним правилом; захардкоженная строка — ни одного из них
 *    в будущем.
 *
 * 3. Тонкое заземление — не то же самое, что нулевое, и пользователю нужно
 *    различать. Возрастная группа 14-17 представлена тремя записями, 60+ —
 *    пятью. Это не «нет данных», но и не основание для уверенного прогноза.
 *
 * ─── Что считается «заземлённым» ───────────────────────────────────────────
 * Порог в 10 записей — не статистика, а честная граница читаемости: на выборке
 * меньше десяти человек доля любого ответа скачет на десятки процентов от
 * одного респондента, и «34% зрителей» превращается в число, которое нельзя
 * показывать без оговорки.
 */

/** Ниже этого числа записей сегмент считается слабо заземлённым. */
export const THIN_THRESHOLD = 10;

export type GroundingLevel = "grounded" | "thin" | "absent";

export interface CriterionCoverage {
  value: string;
  records: number;
  level: GroundingLevel;
}

export interface AudienceGrounding {
  totalRecords: number;
  ageGroups: CriterionCoverage[];
  geos: CriterionCoverage[];
  genders: CriterionCoverage[];
  /** Измерение целиком отсутствует в корпусе — не путать с нулевым значением. */
  ungroundedDimensions: string[];
}

function level(records: number): GroundingLevel {
  if (records === 0) return "absent";
  if (records < THIN_THRESHOLD) return "thin";
  return "grounded";
}

function coverage(
  sessions: readonly { socio_demographics?: Record<string, unknown> }[],
  field: string,
  values: readonly string[],
): CriterionCoverage[] {
  const counts = new Map<string, number>();
  for (const s of sessions) {
    const v = s.socio_demographics?.[field];
    if (typeof v === "string") counts.set(v, (counts.get(v) ?? 0) + 1);
  }
  return values.map((value) => {
    const records = counts.get(value) ?? 0;
    return { value, records, level: level(records) };
  });
}

/** Присутствует ли измерение в корпусе хоть у одной записи. */
function dimensionPresent(
  sessions: readonly { socio_demographics?: Record<string, unknown> }[],
  field: string,
): boolean {
  return sessions.some((s) => s.socio_demographics?.[field] !== undefined);
}

export function audienceGrounding(): AudienceGrounding {
  const sessions = loadSessions() as unknown as readonly {
    socio_demographics?: Record<string, unknown>;
  }[];

  const ungrounded: string[] = [];
  if (!dimensionPresent(sessions, "education")) ungrounded.push("education");

  return {
    totalRecords: sessions.length,
    ageGroups: coverage(sessions, "age_group", AGE_GROUPS),
    geos: coverage(sessions, "geo", GEOS),
    genders: coverage(sessions, "gender", GENDERS),
    ungroundedDimensions: ungrounded,
  };
}

/**
 * Предупреждения по конкретному выбору — то, что показывается на шаге.
 *
 * Пустой массив означает «всё выбранное заземлено», и это осмысленный ответ:
 * отсутствие предупреждения — тоже информация, если пользователь знает, что
 * механизм работает.
 */
export function warningsFor(selected: {
  ageGroups: string[];
  geos: string[];
  genders: string[];
  education: string[];
}): string[] {
  const g = audienceGrounding();
  const out: string[] = [];

  const describe = (
    picked: string[],
    rows: CriterionCoverage[],
    what: string,
  ): void => {
    for (const row of rows) {
      if (!picked.includes(row.value)) continue;
      if (row.level === "absent") {
        out.push(
          `${what} «${row.value}»: в корпусе нет ни одной записи из ${g.totalRecords} — ` +
            `персоны этого сегмента не заземлены и остаются догадкой`,
        );
      } else if (row.level === "thin") {
        out.push(
          `${what} «${row.value}»: всего ${row.records} записей из ${g.totalRecords} — ` +
            `заземление слабое, доли по этому сегменту неустойчивы`,
        );
      }
    }
  };

  describe(selected.ageGroups, g.ageGroups, "возрастная группа");
  describe(selected.geos, g.geos, "гео");
  describe(selected.genders, g.genders, "пол");

  if (selected.education.length > 0 && g.ungroundedDimensions.includes("education")) {
    out.push(
      `образование: в корпусе нет такого поля ни у одной из ${g.totalRecords} записей — ` +
        `критерий повлияет на текст персон, но не на заземление, и метрика ` +
        `persona_grounding его не проверяет`,
    );
  }

  return out;
}
