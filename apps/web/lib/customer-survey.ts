import raw from "../../../data/survey/customer_2026.json" with { type: "json" };

import type { SurveyQuestion, SurveyTheme } from "./agora-types";

/**
 * Обязательная анкета заказчика для конструктора.
 *
 * ─── Почему импорт, а не константы ─────────────────────────────────────────
 * Пятнадцать вопросов, тринадцать эмоций, семнадцать ценностей, десять тем с
 * сорока тремя подтемами и одиннадцать вопросов воздействия — это внешний
 * документ с происхождением и версией. Он уже лежит данными в
 * `data/survey/customer_2026.json`, откуда его читает воркер.
 *
 * Путь относительный, а не через псевдоним `@agora/*`: у `packages/shared`
 * нет своего package.json, псевдоним живёт только в tsconfig, и модуль с ним
 * нельзя загрузить `node --test` — то есть нельзя проверить.
 *
 * Переписать этот состав константой в TSX было бы проще ровно один раз. В этом
 * репозитории так появились четыре копии перечня типов вопроса и две копии
 * перечня ценностей, и одна из копий полтора месяца молча отставала от схемы —
 * в сгенерированном `survey.ts` не было типа `watched_share`, потому что
 * анкеты не было в `npm run codegen`.
 *
 * ─── Что здесь есть, кроме чтения ──────────────────────────────────────────
 * Одно правило: выбор оператора идёт ТЕМАМИ, а не строками. Тема включается
 * целиком со всеми подтемами, и вопрос 11 приходит теми подвопросами, которые
 * к выбранным темам относятся. Иначе интегральный показатель восприятия
 * считался бы по разному числу строк и стал бы несравним между прогонами.
 */

interface CustomerSurveyFile {
  source: string;
  version: string;
  blocks: { id: string; label: string }[];
  questions: SurveyQuestion[];
}

const FILE = raw as unknown as CustomerSurveyFile;

/** Происхождение и версия анкеты — их показывает отчёт и выгрузка. */
export const CUSTOMER_SURVEY_SOURCE = FILE.source;
export const CUSTOMER_SURVEY_VERSION = FILE.version;

/** Шесть блоков верхнего уровня: верхняя строка двухуровневой шапки выгрузки. */
export const CUSTOMER_BLOCKS = FILE.blocks;

/**
 * Пятнадцать обязательных вопросов.
 *
 * Ни один не выключается (решение владельца 17.09.2026): гибкость оператора —
 * в выборе тем вопроса 9 и в дополнительных вопросах. У заказчика они названы
 * «перечнем обязательных вопросов», и снятый вопрос сделал бы отчёт неполным
 * незаметно для читателя.
 */
export const MANDATORY_QUESTIONS: SurveyQuestion[] = FILE.questions;

function question(number: number): SurveyQuestion | undefined {
  return MANDATORY_QUESTIONS.find((q) => q.number === number);
}

/** Темы вопроса-матрицы. Единица выбора оператора. */
export function themesOf(number: number): SurveyTheme[] {
  return question(number)?.themes ?? [];
}

/**
 * Анкета под выбранные темы.
 *
 * Матрица оставляет строки только выбранных тем; зависимый вопрос (11) — свои
 * подвопросы по тем же темам. Если не выбрано ничего, оба вопроса из анкеты
 * выпадают целиком: матрица без строк — это вопрос, на который нечего
 * отвечать, и в анкете ему делать нечего.
 */
export function withSelectedThemes(themeIds: string[]): SurveyQuestion[] {
  const selected = new Set(themeIds);
  const out: SurveyQuestion[] = [];

  for (const q of MANDATORY_QUESTIONS) {
    if (!q.rows) {
      out.push(q);
      continue;
    }
    const rows = q.rows.filter((r) => r.themeId && selected.has(r.themeId));
    if (rows.length === 0) continue;
    out.push({
      ...q,
      rows,
      ...(q.themes ? { themes: q.themes.filter((t) => selected.has(t.id)) } : {}),
    });
  }
  return out;
}
