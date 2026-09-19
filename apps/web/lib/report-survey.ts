import { CUSTOMER_BLOCKS, MANDATORY_QUESTIONS } from "./customer-survey.ts";
import type { SurveyQuestion } from "./agora-types.ts";
import type { SurveyQuestionView, SurveyStats, SurveyView } from "./report-view.ts";

/**
 * Подписи к посчитанной анкете.
 *
 * ─── Зачем отдельный слой ──────────────────────────────────────────────────
 * `survey_tally` считает доли по ИДЕНТИФИКАТОРАМ вариантов: `v-8`, `m-1`,
 * `t1-2`. Подписей в его выводе нет и быть не должно — идентификатор вечен, а
 * формулировку правят, и хранить её рядом с числами значило бы завести вторую
 * копию анкеты, которая разойдётся с первой при первой же правке.
 *
 * Поэтому подписи берутся из того же файла, из которого их берёт воркер, —
 * `data/survey/customer_2026.json` через `customer-survey.ts`. Второго перечня
 * в интерфейсе нет намеренно: в этом репозитории так уже появились четыре
 * копии перечня типов вопроса и две копии перечня ценностей, и одна из копий
 * полтора месяца молча отставала от схемы.
 *
 * ─── Почему незнакомое показывается, а не выбрасывается ────────────────────
 * Оператор дополняет анкету своими вопросами, и подписей их вариантов в анкете
 * заказчика нет. Доля при этом посчитана. Выбросить такую строку значило бы
 * спрятать посчитанное число, поэтому строка остаётся, подписью становится
 * идентификатор, а `known: false` позволяет экрану сказать об этом вслух.
 */

export interface SurveyOptionRow {
  id: string;
  /** Подпись из анкеты; при отсутствии — сам идентификатор. */
  label: string;
  /** Нашлась ли подпись. `false` — на экране стоит идентификатор. */
  known: boolean;
  /** Служебный вариант («Затрудняюсь ответить»): в знаменателе, но не мнение. */
  service: boolean;
  share: number | null;
  count: number | null;
}

export interface SurveyMatrixRow {
  id: string;
  label: string;
  known: boolean;
  themeId: string | null;
  /** Подпись темы, если она нашлась в анкете. */
  themeLabel: string | null;
  stats: SurveyStats;
}

export interface SurveyBlockView {
  id: string;
  label: string;
  questions: SurveyQuestionView[];
}

/** Блок для вопросов, которых нет ни в одном блоке заказчика. */
const LOOSE_BLOCK = { id: "", label: "Вопросы вне блоков" };

const BY_ID = new Map(MANDATORY_QUESTIONS.map((q) => [q.id, q]));
const BY_NUMBER = new Map(
  MANDATORY_QUESTIONS.flatMap((q) => (q.number ? [[q.number, q] as const] : [])),
);

/**
 * Вопрос анкеты, по которому ищутся подписи.
 *
 * Сперва по идентификатору, потом по номеру: идентификатор — контракт, номер —
 * запасной путь для прогонов, где вопрос назвали иначе.
 */
function spec(question: SurveyQuestionView): SurveyQuestion | undefined {
  return BY_ID.get(question.id)
    ?? (question.number !== null ? BY_NUMBER.get(question.number) : undefined);
}

/** Вопрос по номеру анкеты заказчика. `null` — такого в прогоне не было. */
export function surveyQuestion(
  view: SurveyView,
  number: number,
): SurveyQuestionView | null {
  return view.questions.find((q) => q.number === number) ?? null;
}

/**
 * Вопросы, разложенные по блокам заказчика.
 *
 * Пустые блоки не рисуются: оператор выбирает темы, и вопрос-матрица целиком
 * выпадает из анкеты, если не выбрано ни одной. Заголовок блока без вопросов
 * читался бы как «спросили и ничего не получили».
 */
export function surveyBlocks(view: SurveyView): SurveyBlockView[] {
  const known = new Set(CUSTOMER_BLOCKS.map((b) => b.id));
  return [...CUSTOMER_BLOCKS, LOOSE_BLOCK].flatMap((block) => {
    const questions = view.questions.filter((q) =>
      block.id ? q.block === block.id : !q.block || !known.has(q.block),
    );
    return questions.length ? [{ id: block.id, label: block.label, questions }] : [];
  });
}

/**
 * Доли по вариантам с подписями. Пустой список — долей нет: либо вопрос не
 * закрытый, либо срез подавлен порогом.
 */
export function optionRows(
  question: SurveyQuestionView,
  stats: SurveyStats,
): SurveyOptionRow[] {
  if (stats.belowThreshold) return [];
  const byId = new Map((spec(question)?.options ?? []).map((o) => [o.id, o]));
  const actual = new Map((stats.options ?? []).map((row) => [row.id, row]));
  const ids = [...new Set([
    ...((spec(question)?.options ?? []).map((option) => option.id)),
    ...(stats.options ?? []).map((row) => row.id),
  ])];
  return ids.map((id) => {
    const row = actual.get(id) ?? { id, share: 0, count: 0 };
    const option = byId.get(row.id);
    return {
      id: row.id,
      label: option?.label ?? row.id,
      known: Boolean(option),
      service: option?.service === true,
      share: row.share,
      count: row.count,
    };
  });
}

/**
 * Строка показа: подпись варианта и два числа — по всей аудитории и по срезу.
 *
 * ─── Почему сведение пар живёт здесь, а не в разметке ──────────────────────
 * Колонка среза заполняется ТОЛЬКО из среза. Правило звучит очевидно ровно до
 * того момента, когда срез подавлен порогом: у подавленного среза вариантов
 * нет вовсе, и написанное в разметке `target ?? total` подставило бы в колонку
 * «14–35» числа всей аудитории. На экране это выглядит как посчитанный срез,
 * который просто совпал с общим итогом, — то есть выдуманное число, неотличимое
 * от настоящего.
 *
 * Разметка такую подстановку не сторожит ничем: тесты собирают `lib/**`, а
 * `.tsx` проверяется только чтением глазами. Поэтому сведение — функция.
 */
export interface SurveyPairRow {
  id: string;
  label: string;
  known: boolean;
  service: boolean;
  total: number | null;
  totalCount: number | null;
  /** `null` — в срезе этого варианта нет: он подавлен порогом или не спрошен. */
  target: number | null;
  targetCount: number | null;
}

/**
 * Две эксклюзивные доли вопроса 7.
 *
 * Значения приходят готовыми из `survey_tally`. Функция только даёт им подписи
 * и добавляет колонку среза, сохраняя `null`: подавленный срез нельзя выдавать
 * за измеренный ноль или подменять значением всей аудитории.
 */
export function polarityPairs(
  _question: SurveyQuestionView,
  total: SurveyStats,
  target: SurveyStats,
): SurveyPairRow[] {
  if (total.onlyPositive === null && total.onlyNegative === null) return [];
  return [
    {
      id: "only_positive",
      label: "Респонденты, испытавшие только положительные эмоции",
      known: true,
      service: false,
      total: total.onlyPositive,
      target: target.onlyPositive,
    },
    {
      id: "only_negative",
      label: "Респонденты, испытавшие только отрицательные эмоции",
      known: true,
      service: false,
      total: total.onlyNegative,
      target: target.onlyNegative,
    },
  ];
}

export interface SurveyMatrixPair {
  id: string;
  label: string;
  known: boolean;
  themeId: string | null;
  themeLabel: string | null;
  options: SurveyPairRow[];
}

/**
 * Пустой показатель для строки, которой в срезе нет.
 *
 * Именно пустой, а не строка всей аудитории: подстановка второй стороны — это
 * тот самый промах, ради которого заведён `optionPairs`.
 */
const EMPTY_STATS: SurveyStats = {
  n: 0,
  base: null,
  belowThreshold: true,
  mean: null,
  topBox: null,
  groups: null,
  options: null,
  onlyPositive: null,
  onlyNegative: null,
  errors: null,
  texts: null,
  rows: null,
};

/** Доли по вариантам: строки всей аудитории с приставленной колонкой среза. */
export function optionPairs(
  question: SurveyQuestionView,
  total: SurveyStats,
  target: SurveyStats,
): SurveyPairRow[] {
  const inTarget = new Map(optionRows(question, target).map((o) => [o.id, o]));
  return optionRows(question, total).map((o) => ({
    id: o.id,
    label: o.label,
    known: o.known,
    service: o.service,
    total: o.share,
    totalCount: o.count,
    target: inTarget.has(o.id) ? (inTarget.get(o.id)?.share ?? null) : null,
    targetCount: inTarget.has(o.id) ? (inTarget.get(o.id)?.count ?? null) : null,
  }));
}

/** То же для матрицы: строка подтемы и доли по её вариантам в двух охватах. */
export function matrixPairs(
  question: SurveyQuestionView,
  total: SurveyStats,
  target: SurveyStats,
): SurveyMatrixPair[] {
  const inTarget = new Map(matrixRows(question, target).map((r) => [r.id, r.stats]));
  return matrixRows(question, total).map((row) => ({
    id: row.id,
    label: row.label,
    known: row.known,
    themeId: row.themeId,
    themeLabel: row.themeLabel,
    options: optionPairs(question, row.stats, inTarget.get(row.id) ?? EMPTY_STATS),
  }));
}

/** Строки матрицы с подписями подтем и тем. */
export function matrixRows(
  question: SurveyQuestionView,
  stats: SurveyStats,
): SurveyMatrixRow[] {
  const definition = spec(question);
  const byId = new Map((definition?.rows ?? []).map((r) => [r.id, r]));
  const themes = new Map((definition?.themes ?? []).map((t) => [t.id, t.label]));
  return (stats.rows ?? []).map((row) => {
    const known = byId.get(row.id);
    const themeId = row.themeId ?? known?.themeId ?? null;
    return {
      id: row.id,
      label: known?.label ?? row.id,
      known: Boolean(known),
      themeId,
      themeLabel: themeId ? (themes.get(themeId) ?? null) : null,
      stats: row.stats,
    };
  });
}
