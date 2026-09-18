import type { SurveyQuestion, SurveyRow } from "./agora-types";

/**
 * Как показать варианты ответа обязательного вопроса в конструкторе.
 *
 * Оператор не редактирует эти вопросы, но должен видеть, что именно спросят
 * у персоны, — иначе он не может решить, нужны ли ему дополнительные вопросы.
 * До этой правки плашка показывала только счётчик («19 вариантов»), то есть
 * ровно ту информацию, которой для решения не хватает.
 *
 * Решение живёт здесь, а не в компоненте, по той же причине, что и состав
 * анкеты: веб-тесты собирают только `lib/**`, и логика, оставленная в `.tsx`,
 * не покрыта ничем по построению.
 */

/**
 * Сколько вариантов ещё помещается в строку.
 *
 * Шесть — это граница, за которой список перестаёт читаться одним взглядом и
 * начинает вытеснять с экрана саму анкету. У девяти из пятнадцати обязательных
 * вопросов вариантов два-три; прятать их за кликом значило бы заставить
 * оператора открыть девять плашек, чтобы прочитать то, что помещается в
 * строку. У вопросов 7 и 8 вариантов пятнадцать и девятнадцать, а у матриц —
 * сорок три и одиннадцать строк.
 */
export const INLINE_OPTIONS_MAX = 6;

export type OptionsPresentation = "none" | "inline" | "collapsed";

/** Тема матрицы вместе со своими строками. */
export interface ThemeGroup {
  id: string;
  label: string;
  rows: SurveyRow[];
}

/**
 * Как показывать варианты этого вопроса.
 *
 * `none` — вариантов нет (шкала, открытый вопрос).
 * `inline` — список короткий, виден сразу.
 * `collapsed` — список длинный или это матрица: за раскрытием.
 *
 * Матрица сворачивается всегда, независимо от числа вариантов: у неё к
 * вариантам добавляются строки, и даже два варианта на одиннадцать строк
 * занимают больше места, чем весь остальной список вопросов.
 */
export function optionsPresentation(question: SurveyQuestion): OptionsPresentation {
  const options = question.options?.length ?? 0;
  const rows = question.rows?.length ?? 0;

  if (options === 0 && rows === 0) return "none";
  if (rows > 0) return "collapsed";
  return options > INLINE_OPTIONS_MAX ? "collapsed" : "inline";
}

/**
 * Служебный вариант — тот, что выбирается только в одиночку.
 *
 * Разметка бывает двух видов, и обе живые: вопросы 7 и 8 перечисляют такие
 * варианты в `exclusiveOptionIds`, вопрос 10 ставит флаг `service` на самом
 * варианте. Читатель обязан знать оба — иначе «Затрудняюсь ответить»
 * покажется обычным вариантом, и оператор решит, что персона может выбрать
 * его вместе с содержательным.
 */
export function isServiceOption(question: SurveyQuestion, optionId: string): boolean {
  if (question.exclusiveOptionIds?.includes(optionId)) return true;
  return question.options?.find((o) => o.id === optionId)?.service === true;
}

/**
 * Строки матрицы, сгруппированные по темам.
 *
 * Порядок тем — из анкеты, а не из порядка появления строк: оператор выбирает
 * темами, и список должен совпадать с тем, что он выбирал.
 *
 * Строка, чьей темы нет в списке `themes`, не выбрасывается, а собирается в
 * группу по своему `themeId`. Это не запасной путь на всякий случай: у
 * зависимого вопроса 11 строки несут `themeId`, а собственного списка тем у
 * вопроса нет вовсе — наивная группировка «по списку тем» потеряла бы все
 * одиннадцать строк, и на экране вопрос выглядел бы пустым.
 */
export function themeGroups(question: SurveyQuestion): ThemeGroup[] {
  const rows = question.rows ?? [];
  if (rows.length === 0) return [];

  const declared = question.themes ?? [];
  const order: string[] = declared.map((t) => t.id);
  const label = new Map(declared.map((t) => [t.id, t.label]));

  for (const row of rows) {
    const id = row.themeId ?? "";
    if (!order.includes(id)) order.push(id);
  }

  return order
    .map((id) => ({
      id,
      label: label.get(id) ?? "",
      rows: rows.filter((r) => (r.themeId ?? "") === id),
    }))
    .filter((group) => group.rows.length > 0);
}
