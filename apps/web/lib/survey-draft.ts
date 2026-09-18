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
  delete next.maxChoices;
  delete next.scaleMin;
  delete next.scaleMax;

  if (type === "scale") {
    next.scaleMin = question.scaleMin ?? SCALE.min;
    next.scaleMax = question.scaleMax ?? SCALE.max;
    return next;
  }

  if (!CLOSED.has(type)) return next;

  const kept = question.options ?? [];
  const options: SurveyOption[] = [...kept];
  while (options.length < SEEDED_OPTIONS) {
    options.push({ id: freeId("o", options), label: "" });
  }
  next.options = options;

  if (type === "multi_choice") next.maxChoices = question.maxChoices ?? options.length;

  if (type === "matrix_single") {
    const rows = question.rows ?? [];
    next.rows = rows.length > 0 ? [...rows] : [{ id: freeId("r", rows), label: "" }];
  }

  return next;
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
  rows.push({ id: freeId("r", rows), label: "" });
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

  if (CLOSED.has(question.type)) {
    const options = question.options ?? [];
    if (options.length < 2) issues.push("закрытому вопросу нужно не меньше двух вариантов");
    if (options.some((o) => o.label.trim().length === 0)) {
      issues.push("у каждого варианта должна быть подпись");
    }
  }

  if (question.type === "matrix_single" && (question.rows?.length ?? 0) < 1) {
    issues.push("матрице нужна хотя бы одна строка");
  }

  if (question.type === "matrix_single" && (question.rows ?? []).some((r) => !r.label.trim())) {
    issues.push("у каждой строки должна быть подпись");
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
