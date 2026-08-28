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

export type QuestionType =
  | "scale"
  | "emotions"
  | "retention"
  | "watched_share"
  | "recommendation"
  | "open";

export type BaseCriterionKey =
  | "overall_impression"
  | "plot"
  | "acting"
  | "music"
  | "cinematography";

export interface SurveyQuestion {
  id: string;
  baseKey?: BaseCriterionKey | null;
  label: string;
  type: QuestionType;
  scaleMin: number;
  scaleMax: number;
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
  "emotions",
  "retention",
  "watched_share",
  "recommendation",
  "open",
];

const REQUIRED_BASE_SCALE = { min: 1, max: 10 } as const;

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

    // scaleMin, scaleMax
    const scaleMin = question.scaleMin;
    const scaleMax = question.scaleMax;
    if (typeof scaleMin !== "number" || !Number.isInteger(scaleMin)) {
      errors.push(`${prefix}.scaleMin: целое число`);
    }
    if (typeof scaleMax !== "number" || !Number.isInteger(scaleMax)) {
      errors.push(`${prefix}.scaleMax: целое число`);
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
        if (scaleMin !== REQUIRED_BASE_SCALE.min || scaleMax !== REQUIRED_BASE_SCALE.max) {
          errors.push(
            `${prefix}: базовый критерий «${baseKey}» должен иметь шкалу 1–10, получено ${scaleMin}–${scaleMax}`,
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
  // Путь считается от этого модуля, а не от `process.cwd()`.
  //
  // От cwd он работал ровно при запуске из корня монорепо. У функции не было
  // ни одного вызова — она экспортировалась «для CDD-тестов», которых не
  // написали, — поэтому промах никогда не проявлялся. Первый же вызов из
  // теста (cwd = apps/web) и из Next (cwd тоже apps/web) даёт ENOENT.
  const path = resolve(
    new URL("../..", import.meta.url).pathname,
    "..",
    "..",
    "packages/shared/schemas/survey.schema.json",
  );
  cachedSchema = JSON.parse(readFileSync(path, "utf-8"));
  return cachedSchema;
}