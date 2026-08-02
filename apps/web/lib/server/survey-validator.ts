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

export type QuestionType = "scale" | "emotions" | "retention" | "recommendation" | "open";

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
 * 2. questions — массив, ≥ 5 элементов
 * 3. Каждый вопрос: id, label, type, scaleMin, scaleMax
 * 4. type — один из ALLOWED_QUESTION_TYPES
 * 5. Ровно 5 базовых критериев с уникальными baseKey из BASE_CRITERIA
 * 6. Базовые критерии — type=scale, scaleMin=1, scaleMax=10
 * 7. При type=scale: scaleMax > scaleMin
 * 8. baseKey — один из BASE_CRITERIA (если задан)
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
  if (questions.length < 5) {
    errors.push(`questions: минимум 5 элементов, получено ${questions.length}`);
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

  // 5. Все 5 базовых критериев присутствуют
  for (const required of BASE_CRITERIA) {
    if (!baseKeysFound.has(required)) {
      errors.push(`questions: отсутствует базовый критерий «${required}»`);
    }
  }

  return { valid: errors.length === 0, errors };
}

// ─── Загрузка сырой схемы (для CDD-тестов и introspection) ──────────────

let cachedSchema: unknown | null = null;

export function getSurveySchema(): unknown {
  if (cachedSchema) return cachedSchema;
  const path = resolve(process.cwd(), "packages/shared/schemas/survey.schema.json");
  cachedSchema = JSON.parse(readFileSync(path, "utf-8"));
  return cachedSchema;
}