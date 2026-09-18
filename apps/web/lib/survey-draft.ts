import type { SurveyOption, SurveyQuestion, SurveyRow } from "./agora-types";
import { BASE_QUESTIONS } from "./survey-composition.ts";

/**
 * Черновик своего вопроса оператора: варианты, строки и что мешает сохранить.
 *
 * ─── Дыра, которую это закрывает ───────────────────────────────────────────
 * Конструктор предлагал пять типов вопроса, но добавить варианты ответа было
 * нечем: при выборе «Один из списка», «Несколько из списка» или «Матрица»
 * форма показывала только подпись типа и кнопку «Готово». Закрытый вопрос
 * создать было нельзя вообще — а валидатор требует у такого вопроса не меньше
 * двух вариантов, и матрице ещё и строку.
 *
 * Оператор при этом ничего не узнавал: «Готово» была активна, вопрос
 * добавлялся в список, и отказ приходил позже — от сервера, на сохранении всей
 * анкеты, без указания, какой именно вопрос виноват.
 */

/** Сколько вариантов заводится при переходе к закрытому типу. */
const SEEDED_OPTIONS = 2;

/** Границы шкалы по умолчанию — те же, что у базовых критериев. */
const SCALE = {
  min: BASE_QUESTIONS[0].scaleMin,
  max: BASE_QUESTIONS[0].scaleMax,
};

const CLOSED = new Set(["single_choice", "multi_choice", "matrix_single"]);

/** Типы, у которых варианты лежат у самого вопроса, а не у его строк. */
const FLAT_CLOSED = new Set(["single_choice", "multi_choice"]);

/**
 * Свежий идентификатор с заданным префиксом.
 *
 * Уникален по построению, а не по счётчику. Счётчик «максимум плюс один» здесь
 * не работает: функция чистая и видит только УЦЕЛЕВШИЕ варианты. Удалить второй
 * из трёх и добавить новый — и счётчик выдаст `o-3` повторно.
 *
 * Разница не косметическая. Ответ персоны адресует вариант идентификатором,
 * поэтому в анкете, которую уже прогоняли и потом правили, ответы прошлого
 * прогона на удалённый вариант зачлись бы новому — и различить это в отчёте
 * было бы нечем: оба выглядят как законные ответы.
 *
 * Поэтому суффикс случайный. Читаемость страдает (`o-k3x9f2` вместо `o-3`), но
 * читают эти идентификаторы отладчик и разбор ответа, а не человек: на экране
 * у варианта стоит подпись.
 */
function freeId(prefix: string, taken: { id: string }[]): string {
  const used = new Set(taken.map((x) => x.id));
  for (;;) {
    const id = `${prefix}-${Math.random().toString(36).slice(2, 8)}`;
    if (!used.has(id)) return id;
  }
}

/**
 * Готовит черновик к новому типу ответа.
 *
 * Закрытые типы получают два пустых варианта, матрица — ещё и строку: пустая
 * форма, в которой нечего заполнить, не отличается на вид от сломанной.
 * Незначащие для типа поля убираются, а не остаются висеть — иначе у выбора из
 * списка в документе анкеты сохранились бы границы шкалы, и следующий читатель
 * не смог бы понять, что они означают.
 */
export function draftForType(
  question: SurveyQuestion,
  type: SurveyQuestion["type"],
): SurveyQuestion {
  const next: SurveyQuestion = { ...question, type };

  delete next.options;
  delete next.rows;
  delete next.themes;
  delete next.maxChoices;
  delete next.scaleMin;
  delete next.scaleMax;

  if (type === "scale") {
    next.scaleMin = question.scaleMin ?? SCALE.min;
    next.scaleMax = question.scaleMax ?? SCALE.max;
    return next;
  }

  if (!CLOSED.has(type)) return next;

  if (type === "matrix_single") {
    // Матрица заводится темой с вопросом внутри, а не голой строкой. Вопрос без
    // темы в отчёте не с чем группировать: интегральный показатель восприятия
    // считается по темам, и такая строка молча выпала бы из него.
    //
    // Общего списка вариантов у неё нет: он лежит у КАЖДОГО вопроса. Общий был
    // перенесён сюда из частного случая вопроса 9 заказчика, где один список
    // действительно повторяется на сорока трёх подтемах; у своей матрицы
    // оператора вопросы внутри темы разные, и общий склеил бы их в один.
    const themes = question.themes ?? [];
    next.themes = themes.length > 0 ? [...themes] : [{ id: freeId("t", themes), label: "" }];

    const rows = question.rows ?? [];
    next.rows = rows.length > 0 ? rows.map(seedRowOptions) : [];
    return next.rows.length > 0 ? next : addRowTo(next, next.themes[0].id);
  }

  const kept = question.options ?? [];
  const options: SurveyOption[] = [...kept];
  while (options.length < SEEDED_OPTIONS) {
    options.push({ id: freeId("o", options), label: "" });
  }
  next.options = options;

  if (type === "multi_choice") next.maxChoices = question.maxChoices ?? options.length;

  return next;
}

/** Пустой вопрос матрицы, в котором нечего заполнить, не отличается от сломанного. */
function seedRowOptions(row: SurveyRow): SurveyRow {
  const options: SurveyOption[] = [...(row.options ?? [])];
  while (options.length < SEEDED_OPTIONS) {
    options.push({ id: freeId("o", options), label: "" });
  }
  return { ...row, options, maxChoices: row.maxChoices ?? 1 };
}

export function addOption(question: SurveyQuestion): SurveyQuestion {
  const options = [...(question.options ?? [])];
  options.push({ id: freeId("o", options), label: "" });
  return { ...question, options };
}

export function removeOption(question: SurveyQuestion, id: string): SurveyQuestion {
  return { ...question, options: (question.options ?? []).filter((o) => o.id !== id) };
}

export function setOptionLabel(
  question: SurveyQuestion,
  id: string,
  label: string,
): SurveyQuestion {
  return {
    ...question,
    options: (question.options ?? []).map((o) => (o.id === id ? { ...o, label } : o)),
  };
}

export function addRow(question: SurveyQuestion): SurveyQuestion {
  const rows: SurveyRow[] = [...(question.rows ?? [])];
  rows.push(seedRowOptions({ id: freeId("r", rows), label: "" }));
  return { ...question, rows };
}

export function removeRow(question: SurveyQuestion, id: string): SurveyQuestion {
  return { ...question, rows: (question.rows ?? []).filter((r) => r.id !== id) };
}

export function setRowLabel(
  question: SurveyQuestion,
  id: string,
  label: string,
): SurveyQuestion {
  return {
    ...question,
    rows: (question.rows ?? []).map((r) => (r.id === id ? { ...r, label } : r)),
  };
}

/**
 * Что мешает сохранить вопрос — по строке на причину.
 *
 * Список, а не булево: «Готово» неактивна, и без причины оператору нечего
 * исправлять. Формулировки повторяют требования валидатора намеренно — это тот
 * же контракт, только сказанный до отправки, а не после. Отдельная проверка
 * скармливает собранный здесь вопрос настоящему `validateSurvey`, чтобы два
 * текста не разошлись молча.
 */
export function draftIssues(question: SurveyQuestion): string[] {
  const issues: string[] = [];

  if (question.label.trim().length === 0) issues.push("не заполнена формулировка вопроса");

  if (question.type === "scale") {
    const { scaleMin, scaleMax } = question;
    if (scaleMin === undefined || scaleMax === undefined || scaleMin >= scaleMax) {
      issues.push("нижняя граница шкалы должна быть меньше верхней");
    }
  }

  if (FLAT_CLOSED.has(question.type)) {
    const options = question.options ?? [];
    if (options.length < 2) issues.push("закрытому вопросу нужно не меньше двух вариантов");
    if (options.some((o) => o.label.trim().length === 0)) {
      issues.push("у каждого варианта должна быть подпись");
    }
  }

  if (question.type === "matrix_single") {
    const rows = question.rows ?? [];
    if (rows.length < 1) issues.push("матрице нужна хотя бы одна строка");
    if (rows.some((r) => !r.label.trim())) {
      issues.push("у каждого вопроса матрицы должна быть подпись");
    }
    if (rows.some((r) => rowOptions(question, r).length < 2)) {
      issues.push("закрытому вопросу нужно не меньше двух вариантов");
    }
    if (rows.some((r) => rowOptions(question, r).some((o) => !o.label.trim()))) {
      issues.push("у каждого варианта должна быть подпись");
    }
    const overCap = rows.filter((r) => (r.maxChoices ?? 1) > rowOptions(question, r).length);
    if (overCap.length > 0) {
      issues.push(
        `у вопроса «${overCap[0].label || "без подписи"}» разрешено ` +
          `${overCap[0].maxChoices} ответов, а вариантов ` +
          `${rowOptions(question, overCap[0]).length}`,
      );
    }
  }

  if (question.type === "matrix_single") {
    const themes = question.themes ?? [];
    if (themes.some((t) => !t.label.trim())) issues.push("у каждой темы должна быть подпись");

    const empty = themes.filter((t) => rowsOfTheme(question, t.id).length === 0);
    if (empty.length > 0) {
      issues.push(
        empty.length === 1
          ? "в теме нет ни одного вопроса"
          : `тем без вопросов: ${empty.length} — каждая даст в отчёте пустую группу`,
      );
    }
  }

  if (question.type === "multi_choice") {
    const cap = question.maxChoices;
    const options = question.options?.length ?? 0;
    if (cap !== undefined && (!Number.isInteger(cap) || cap < 1)) {
      issues.push("потолок выбора — целое число не меньше единицы");
    } else if (cap !== undefined && cap > options) {
      issues.push(`потолок выбора (${cap}) больше числа вариантов (${options})`);
    }
  }

  return issues;
}

// ─── Матрица как дерево: тема → вопросы → общие варианты ──────────────────

export function addTheme(question: SurveyQuestion): SurveyQuestion {
  const themes = [...(question.themes ?? [])];
  const theme = { id: freeId("t", themes), label: "" };
  themes.push(theme);
  return addRowTo({ ...question, themes }, theme.id);
}

export function setThemeLabel(
  question: SurveyQuestion,
  id: string,
  label: string,
): SurveyQuestion {
  return {
    ...question,
    themes: (question.themes ?? []).map((t) => (t.id === id ? { ...t, label } : t)),
  };
}

/**
 * Удаление темы уносит её вопросы.
 *
 * Оставить их значило бы завести строки, не принадлежащие ни одной теме. В
 * отчёте такие не попадут ни в одну группу и молча выпадут из интегрального
 * показателя восприятия — он считается как максимум по подтемам внутри темы,
 * усреднённый по темам. Потеря выглядела бы не потерей, а другим числом.
 */
export function removeTheme(question: SurveyQuestion, id: string): SurveyQuestion {
  return {
    ...question,
    themes: (question.themes ?? []).filter((t) => t.id !== id),
    rows: (question.rows ?? []).filter((r) => r.themeId !== id),
  };
}

/** Вопрос внутрь конкретной темы. */
export function addRowTo(question: SurveyQuestion, themeId: string): SurveyQuestion {
  const rows: SurveyRow[] = [...(question.rows ?? [])];
  rows.push(seedRowOptions({ id: freeId("r", rows), label: "", themeId }));
  return { ...question, rows };
}

/** Вопросы одной темы, в порядке добавления. */
export function rowsOfTheme(question: SurveyQuestion, themeId: string): SurveyRow[] {
  return (question.rows ?? []).filter((r) => r.themeId === themeId);
}

/**
 * Варианты ответа одного вопроса матрицы.
 *
 * Свои, а без своих — общие у вопроса. Второе оставляет вопрос 9 заказчика
 * ровно таким, каким он был: один список на сорок три подтемы. То же правило
 * записано у воркера (`survey.py:row_options`), и сходство не случайно —
 * промпт, схема ответа, расчёт долей и выгрузка обязаны видеть один и тот же
 * список, иначе персоне предложат одно, а посчитают другое.
 */
export function rowOptions(question: SurveyQuestion, row: SurveyRow): SurveyOption[] {
  return row.options && row.options.length > 0 ? row.options : (question.options ?? []);
}

function patchRow(
  question: SurveyQuestion,
  rowId: string,
  patch: (row: SurveyRow) => SurveyRow,
): SurveyQuestion {
  return {
    ...question,
    rows: (question.rows ?? []).map((r) => (r.id === rowId ? patch(r) : r)),
  };
}

/** Прижимает потолок выбора к тому, что есть: обещать больше нечем. */
function cappedTo(row: SurveyRow): SurveyRow {
  const total = row.options?.length ?? 0;
  const cap = Math.min(Math.max(1, Math.floor(row.maxChoices ?? 1)), Math.max(1, total));
  return { ...row, maxChoices: cap };
}

export function addRowOption(question: SurveyQuestion, rowId: string): SurveyQuestion {
  return patchRow(question, rowId, (row) => {
    const options = [...(row.options ?? [])];
    options.push({ id: freeId("o", options), label: "" });
    return { ...row, options };
  });
}

/**
 * Удаление варианта опускает потолок следом за ним.
 *
 * Иначе потолок пережил бы вариант, на который был рассчитан: «до трёх» при
 * двух оставшихся — это обещание, которого анкета не выполнит, собранное в два
 * шага вместо одного.
 */
export function removeRowOption(
  question: SurveyQuestion,
  rowId: string,
  optionId: string,
): SurveyQuestion {
  return patchRow(question, rowId, (row) =>
    cappedTo({ ...row, options: (row.options ?? []).filter((o) => o.id !== optionId) }),
  );
}

export function setRowOptionLabel(
  question: SurveyQuestion,
  rowId: string,
  optionId: string,
  label: string,
): SurveyQuestion {
  return patchRow(question, rowId, (row) => ({
    ...row,
    options: (row.options ?? []).map((o) => (o.id === optionId ? { ...o, label } : o)),
  }));
}

/**
 * Сколько вариантов персона выбирает в этом вопросе.
 *
 * Больше, чем добавлено вариантов, задать нельзя: «до трёх» при двух вариантах
 * анкета не выполнит, а в отчёте это не будет видно — доли сойдутся по тем
 * двум, что есть, и будут выглядеть так же уверенно.
 */
export function setRowMaxChoices(
  question: SurveyQuestion,
  rowId: string,
  count: number,
): SurveyQuestion {
  return patchRow(question, rowId, (row) =>
    cappedTo({ ...row, maxChoices: Number.isFinite(count) ? Math.floor(count) : 1 }),
  );
}
