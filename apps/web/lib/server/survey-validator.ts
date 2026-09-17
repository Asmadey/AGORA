import "server-only";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Валидация анкеты по JSON Schema (задача #10).
 *
 * ─── Почему без ajv ────────────────────────────────────────────────────
 * ajv — отличная библиотека, но тянет за собой fast-json-stringify,
 * uri-js и ещё несколько пакетов. Схема анкеты линейная: пять базовых
 * критериев с фиксированными ключами + массив пользовательских вопросов
 * с пятью типами. Написать валидатор для этого вручную — 80 строк, и он
 * точнее совпадает с доменной логикой (например, «scaleMax > scaleMin»
 * при type=scale — ajv требует JSON Schema draft-2020 if/then, что
 * поддерживается только ajv/2020, а не дефолтным ajv).
 *
 * Когда схема станет сложнее (вложенные условия, conditional required),
 * имеет смысл перейти на ajv. Пока — ручная проверка, синхронная и без
 * зависимостей.
 */

// ─── Типы ────────────────────────────────────────────────────────────────
//
// Берутся из типов, СГЕНЕРИРОВАННЫХ по той же схеме, против которой валидатор
// и проверяет. Здесь стояли свои объявления, и это была четвёртая копия одного
// перечня: JSON Schema, `packages/shared/types/survey.ts`, `lib/agora-types.ts`
// и эта. Четыре копии расходятся молча — так и вышло: в сгенерированном файле
// не хватало типа `watched_share`, потому что анкеты не было в `npm run
// codegen`, а докстрока при этом утверждала «только этих пяти форм».
//
// Копий осталось две, и обе теперь производные от схемы.

export type { BaseCriterionKey, QuestionType } from "@agora/shared/types/survey";

import type { BaseCriterionKey, QuestionType } from "@agora/shared/types/survey";

export interface SurveyQuestion {
  id: string;
  baseKey?: BaseCriterionKey | null;
  label: string;
  type: QuestionType;
  /** Обязательны только при type === "scale". */
  scaleMin?: number;
  scaleMax?: number;
  hint?: string;
}

export interface SurveyDocument {
  id?: string;
  name: string;
  questions: SurveyQuestion[];
  created_at?: string;
}

// ─── Константы ───────────────────────────────────────────────────────────

export const BASE_CRITERIA: BaseCriterionKey[] = [
  "overall_impression",
  "plot",
  "acting",
  "music",
  "cinematography",
];

export const ALLOWED_QUESTION_TYPES: QuestionType[] = [
  "scale",
  "single_choice",
  "multi_choice",
  "matrix_single",
  "open",
];

/** Типы, ответ на которые обязан быть одним из объявленных вариантов. */
const CLOSED_TYPES: QuestionType[] = ["single_choice", "multi_choice", "matrix_single"];

// ─── Результат валидации ────────────────────────────────────────────────

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

// ─── Валидатор ───────────────────────────────────────────────────────────

/**
 * Валидирует анкету против схемы survey.schema.json.
 *
 * Проверки:
 * 1. name — непустая строка ≤ 200 символов
 * 2. questions — массив, ≥ 1 элемента
 * 3. Каждый вопрос: id, label, type, scaleMin, scaleMax
 * 4. type — один из ALLOWED_QUESTION_TYPES
 * 5. baseKey не повторяется (сами базовые критерии — необязательны)
 * 6. Базовый критерий, ЕСЛИ присутствует, — type=scale, scaleMin=1, scaleMax=10
 * 7. При type=scale: scaleMax > scaleMin
 * 8. baseKey — один из BASE_CRITERIA (если задан)
 *
 * ─── Почему базовые критерии перестали быть обязательными ──────────────
 * Требование всех пяти делало непринимаемой анкету, в которой владелец снял
 * «Музыку» — то есть запрещало спрашивать своё. Решение владельца: снимать
 * можно любое их число, вплоть до всех.
 *
 * Терять при этом нечего, кроме сравнения с корпусом по снятому критерию, и
 * это уже показано в конструкторе плашкой. Агрегатор к отсутствию готов:
 * `_core_means` возвращает `None`, отчёт рисует «—». Ноль там не появится —
 * а именно ноль был бы опасен, потому что попал бы в средние.
 */
export function validateSurvey(doc: unknown): ValidationResult {
  const errors: string[] = [];

  if (typeof doc !== "object" || doc === null) {
    return { valid: false, errors: ["Анкета должна быть объектом"] };
  }

  const survey = doc as Record<string, unknown>;

  // 1. name
  if (typeof survey.name !== "string" || survey.name.trim().length === 0) {
    errors.push("name: обязательная непустая строка");
  } else if (survey.name.length > 200) {
    errors.push("name: не длиннее 200 символов");
  }

  // 2. questions
  if (!Array.isArray(survey.questions)) {
    errors.push("questions: должен быть массивом");
    return { valid: false, errors };
  }

  const questions = survey.questions;
  // Минимум — один вопрос, а не пять. Пятёрка стояла здесь потому, что пять
  // базовых критериев считались обязательными; они больше не обязательны.
  // Ноль остаётся отказом: анкета без вопросов означает прогон, в котором
  // персону не о чем спрашивать, а стоит он столько же.
  if (questions.length < 1) {
    errors.push("questions: нужен хотя бы один вопрос");
  }

  // 3+4. Каждый вопрос
  const seenIds = new Set<string>();
  const baseKeysFound = new Set<BaseCriterionKey>();

  for (let i = 0; i < questions.length; i++) {
    const q = questions[i];
    const prefix = `questions[${i}]`;

    if (typeof q !== "object" || q === null) {
      errors.push(`${prefix}: должен быть объектом`);
      continue;
    }

    const question = q as Record<string, unknown>;

    // id
    if (typeof question.id !== "string" || question.id.trim().length === 0) {
      errors.push(`${prefix}.id: обязательная непустая строка`);
    } else if (seenIds.has(question.id)) {
      errors.push(`${prefix}.id: дубликат id «${question.id}»`);
    } else {
      seenIds.add(question.id);
    }

    // label
    if (typeof question.label !== "string" || question.label.trim().length === 0) {
      errors.push(`${prefix}.label: обязательная непустая строка`);
    } else if (question.label.length > 500) {
      errors.push(`${prefix}.label: не длиннее 500 символов`);
    }

    // type
    const type = question.type;
    if (typeof type !== "string" || !ALLOWED_QUESTION_TYPES.includes(type as QuestionType)) {
      errors.push(
        `${prefix}.type: должен быть одним из ${ALLOWED_QUESTION_TYPES.join(", ")}`,
      );
    }

    // scaleMin, scaleMax — только у шкалы
    //
    // Требовать их у выбора из списка значило бы заставлять конструктор писать
    // числа, которых у вопроса нет, и хранить их в базе как настоящие границы.
    // Анкета заказчика на этом и спотыкалась: девять вопросов из пятнадцати —
    // выбор, и ни у одного шкалы нет.
    const scaleMin = question.scaleMin;
    const scaleMax = question.scaleMax;
    if (type === "scale") {
      if (typeof scaleMin !== "number" || !Number.isInteger(scaleMin)) {
        errors.push(`${prefix}.scaleMin: целое число`);
      }
      if (typeof scaleMax !== "number" || !Number.isInteger(scaleMax)) {
        errors.push(`${prefix}.scaleMax: целое число`);
      }
    }

    // Закрытый вопрос обязан нести свои варианты.
    //
    // Закрытый вопрос БЕЗ вариантов — это открытый вопрос: персона ответит
    // своими словами, ответ разберётся, отчёт соберётся — и не сойдётся с
    // закрытым списком заказчика.
    if (typeof type === "string" && CLOSED_TYPES.includes(type as QuestionType)) {
      const options = question.options;
      if (!Array.isArray(options) || options.length < 2) {
        errors.push(`${prefix}.options: закрытому вопросу нужно не меньше двух вариантов`);
      } else {
        const seenOptionIds = new Set<string>();
        for (let j = 0; j < options.length; j++) {
          const option = options[j] as Record<string, unknown> | null;
          if (typeof option !== "object" || option === null) {
            errors.push(`${prefix}.options[${j}]: должен быть объектом`);
            continue;
          }
          // Идентификатор, а не подпись: подпись правят, идентификатор — нет.
          if (typeof option.id !== "string" || option.id.trim().length === 0) {
            errors.push(`${prefix}.options[${j}].id: обязательная непустая строка`);
          } else if (seenOptionIds.has(option.id)) {
            errors.push(`${prefix}.options[${j}].id: дубликат «${option.id}»`);
          } else {
            seenOptionIds.add(option.id);
          }
          if (typeof option.label !== "string" || option.label.trim().length === 0) {
            errors.push(`${prefix}.options[${j}].label: обязательная непустая строка`);
          }
        }
      }
    }

    // Матрица обязана нести строки: отвечают по строкам, а не по вопросу.
    // Сорок три подтемы вопроса 9 — это сорок три поля, и покрытие анкеты
    // считается по ним.
    if (type === "matrix_single") {
      const rows = question.rows;
      if (!Array.isArray(rows) || rows.length < 1) {
        errors.push(`${prefix}.rows: матрице нужна хотя бы одна строка`);
      }
    }

    // Потолок выбора. Без него модель выберет столько вариантов, сколько
    // захочет, и доли перестанут быть сравнимыми с полевыми волнами заказчика.
    if (question.maxChoices !== undefined && question.maxChoices !== null) {
      const cap = question.maxChoices;
      if (typeof cap !== "number" || !Number.isInteger(cap) || cap < 1) {
        errors.push(`${prefix}.maxChoices: целое число не меньше единицы`);
      }
    }

    // 7. При type=scale: scaleMax > scaleMin
    if (
      type === "scale" &&
      typeof scaleMin === "number" &&
      typeof scaleMax === "number" &&
      scaleMin >= scaleMax
    ) {
      errors.push(`${prefix}: scaleMax (${scaleMax}) должен быть больше scaleMin (${scaleMin})`);
    }

    // 8. baseKey
    const baseKey = question.baseKey;
    if (baseKey !== undefined && baseKey !== null) {
      if (typeof baseKey !== "string" || !BASE_CRITERIA.includes(baseKey as BaseCriterionKey)) {
        errors.push(
          `${prefix}.baseKey: должен быть одним из ${BASE_CRITERIA.join(", ")}`,
        );
      } else {
        if (baseKeysFound.has(baseKey as BaseCriterionKey)) {
          errors.push(`${prefix}.baseKey: дубликат «${baseKey}»`);
        } else {
          baseKeysFound.add(baseKey as BaseCriterionKey);
        }

        // 6. Базовый критерий — type=scale, scaleMin=1, scaleMax=10
        if (type !== "scale") {
          errors.push(`${prefix}: базовый критерий «${baseKey}» должен быть type=scale`);
        }
        // Границы больше не прибиты к 1–10.
        //
        // Анкета заказчика пришла на шкале 0–10 (17.09.2026), и прежнее
        // требование отвергало её целиком. Ключ критерия при этом остаётся
        // контрактом с данными: именно по этим пяти ключам посчитаны средние
        // 165 респондентов корпуса. Меняется шкала, не ключ.
        if (
          typeof scaleMin !== "number" ||
          typeof scaleMax !== "number" ||
          scaleMin >= scaleMax
        ) {
          errors.push(
            `${prefix}: у базового критерия «${baseKey}» должна быть шкала, получено ${scaleMin}–${scaleMax}`,
          );
        }
      }
    }

    // hint (необязательный)
    if (question.hint !== undefined && question.hint !== null) {
      if (typeof question.hint !== "string") {
        errors.push(`${prefix}.hint: строка или отсутствует`);
      } else if (question.hint.length > 1000) {
        errors.push(`${prefix}.hint: не длиннее 1000 символов`);
      }
    }
  }

  // Базовые критерии одной анкеты — на ОДНОЙ шкале.
  //
  // ─── Что здесь было и почему изменилось ──────────────────────────────
  // Стояло требование ровно 1–10. Анкета заказчика пришла на 0–10
  // (17.09.2026), и требование её отвергало.
  //
  // Опасность, ради которой оно писалось, никуда не делась: «1–5 вместо 1–10
  // сдвинуло бы среднее вдвое, и заметить это было бы нечем». Интегральный
  // индекс удовлетворённости заказчика — среднее долей по ПЯТИ критериям, и
  // считать его по разным шкалам нельзя.
  //
  // Поэтому проверяется то, что валидатор в состоянии проверить, глядя на одну
  // анкету: все базовые критерии в ней на одной шкале. Совпадение шкал МЕЖДУ
  // прогонами отсюда не видно — это вопрос сравнения отчётов, и его решает
  // подпись шкалы в самом отчёте.
  const baseScales = new Set<string>();
  for (const q of questions) {
    if (typeof q !== "object" || q === null) continue;
    const question = q as Record<string, unknown>;
    if (!question.baseKey) continue;
    if (typeof question.scaleMin === "number" && typeof question.scaleMax === "number") {
      baseScales.add(`${question.scaleMin}–${question.scaleMax}`);
    }
  }
  if (baseScales.size > 1) {
    errors.push(
      `базовые критерии должны быть на одной шкале, найдены разные: ${[...baseScales].join(", ")}`,
    );
  }

  // 5. Базовые критерии НЕОБЯЗАТЕЛЬНЫ — см. заголовок функции.
  //
  // Здесь стояло требование всех пяти, и оно делало анкету без «Музыки»
  // непринимаемой базой. Требование снято по решению владельца: пользователь
  // вправе спрашивать своё и не обязан спрашивать чужое.
  //
  // Что осталось от правила: базовый критерий, если он ЕСТЬ, обязан быть
  // шкалой 1–10 и не может повторяться (проверки 6 и 8 выше). Иначе ключ
  // `overall_impression` со шкалой 1–5 попал бы в те же средние, по которым
  // считается сравнение с корпусом, и сдвинул бы их вдвое — молча.
  //
  // Цену снятия называет интерфейс, а не валидатор: конструктор показывает,
  // сколько критериев снято и что сравнение с корпусом по ним отключено.
  // Подпись — не запрет, и разница здесь существенная.

  return { valid: errors.length === 0, errors };
}

// ─── Загрузка сырой схемы (для CDD-тестов и introspection) ──────────────

let cachedSchema: unknown | null = null;

export function getSurveySchema(): unknown {
  if (cachedSchema) return cachedSchema;

  // Схема лежит в корне монорепо, а `process.cwd()` бывает и корнем, и
  // `apps/web` — зависит от того, чем запущено. Прежняя редакция знала только
  // первый случай и падала во втором; вызовов у функции не было ни одного, и
  // промах не проявлялся.
  //
  // Проверяются оба варианта, а не собирается путь от `import.meta.url`:
  // webpack разбирает `new URL(…, import.meta.url)` как запрос модуля и
  // валит сборку с «Can't resolve '../..'».
  const RELATIVE = "packages/shared/schemas/survey.schema.json";
  const candidates = [resolve(process.cwd(), RELATIVE), resolve(process.cwd(), "..", "..", RELATIVE)];

  for (const path of candidates) {
    try {
      cachedSchema = JSON.parse(readFileSync(path, "utf-8"));
      return cachedSchema;
    } catch {
      // Следующий кандидат. Молчим только про ненайденный файл — разобрать
      // найденный и битый нельзя, и об этом узнает последний throw.
    }
  }
  throw new Error(`survey.schema.json не найден: искали ${candidates.join(", ")}`);
}