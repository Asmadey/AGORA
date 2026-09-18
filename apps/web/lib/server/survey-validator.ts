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

/**
 * Шкала базовых критериев. Ровно эти границы, и никакие другие.
 *
 * Это не настройка оформления, а контракт с расчётом: `analytics/survey_stats`
 * читает баллы абсолютными порогами заказчика (доля 8–10, промоутеры 9–10,
 * детракторы 0–6). Сменить здесь границы и не сменить там — значит получить
 * индекс 0.0 на правдоподобно выглядящем отчёте.
 *
 * Питонова сторона держит те же числа и сверяется с этим файлом тестом
 * `test_base_scale_agrees.py`.
 */
export const BASE_SCALE_MIN = 0;
export const BASE_SCALE_MAX = 10;

export const ALLOWED_QUESTION_TYPES: QuestionType[] = [
  "scale",
  "single_choice",
  "multi_choice",
  "matrix_single",
  "open",
];

/** Типы, ответ на которые обязан быть одним из объявленных вариантов. */
const CLOSED_TYPES: QuestionType[] = ["single_choice", "multi_choice", "matrix_single"];

/**
 * Варианты одного списка: объект, непустой идентификатор, уникальность, подпись.
 *
 * Список бывает у вопроса и у строки матрицы, и правила у них одни. Отдельная
 * копия проверки на строку разошлась бы с копией на вопрос — в этом
 * репозитории так уже расходились четыре читателя ответа персоны.
 */
function checkOptions(options: unknown[], prefix: string, errors: string[]): void {
  const seen = new Set<string>();
  for (let j = 0; j < options.length; j++) {
    const option = options[j] as Record<string, unknown> | null;
    if (typeof option !== "object" || option === null) {
      errors.push(`${prefix}[${j}]: должен быть объектом`);
      continue;
    }
    // Идентификатор, а не подпись: подпись правят, идентификатор — нет.
    if (typeof option.id !== "string" || option.id.trim().length === 0) {
      errors.push(`${prefix}[${j}].id: обязательная непустая строка`);
    } else if (seen.has(option.id)) {
      errors.push(`${prefix}[${j}].id: дубликат «${option.id}»`);
    } else {
      seen.add(option.id);
    }
    if (typeof option.label !== "string" || option.label.trim().length === 0) {
      errors.push(`${prefix}[${j}].label: обязательная непустая строка`);
    }
  }
}

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
    //
    // У матрицы список лежит либо у вопроса (вопрос 9 заказчика: один на сорок
    // три подтемы), либо у каждой строки (своя матрица оператора: у вопросов
    // внутри темы они разные). Требовать оба — значит отвергнуть одну из двух
    // живых форм; не требовать ни одного — пропустить матрицу без вариантов.
    const sharedOptions = question.options;
    const hasShared = Array.isArray(sharedOptions) && sharedOptions.length >= 2;

    if (typeof type === "string" && CLOSED_TYPES.includes(type as QuestionType)) {
      if (type === "matrix_single") {
        if (Array.isArray(sharedOptions)) checkOptions(sharedOptions, `${prefix}.options`, errors);
      } else if (!hasShared) {
        errors.push(`${prefix}.options: закрытому вопросу нужно не меньше двух вариантов`);
      } else {
        checkOptions(sharedOptions as unknown[], `${prefix}.options`, errors);
      }
    }

    // Матрица обязана нести строки: отвечают по строкам, а не по вопросу.
    // Сорок три подтемы вопроса 9 — это сорок три поля, и покрытие анкеты
    // считается по ним.
    if (type === "matrix_single") {
      const rows = question.rows;
      if (!Array.isArray(rows) || rows.length < 1) {
        errors.push(`${prefix}.rows: матрице нужна хотя бы одна строка`);
      } else {
        for (let j = 0; j < rows.length; j++) {
          const row = rows[j] as Record<string, unknown> | null;
          const rowPrefix = `${prefix}.rows[${j}]`;
          if (typeof row !== "object" || row === null) {
            errors.push(`${rowPrefix}: должен быть объектом`);
            continue;
          }

          const own = row.options;
          const hasOwn = Array.isArray(own) && own.length > 0;
          if (hasOwn) {
            if ((own as unknown[]).length < 2) {
              errors.push(
                `${rowPrefix}.options: закрытому вопросу нужно не меньше двух вариантов`,
              );
            }
            checkOptions(own as unknown[], `${rowPrefix}.options`, errors);
          } else if (!hasShared) {
            errors.push(
              `${rowPrefix}.options: у строки нет своих вариантов, а общих у вопроса нет`,
            );
          }

          // Потолок выбора строки — это обещание персоне. Больше, чем
          // вариантов, анкета не выполнит, а в отчёте это не будет видно:
          // доли сойдутся по тем, что есть, и будут выглядеть так же уверенно.
          const cap = row.maxChoices;
          if (cap !== undefined && cap !== null) {
            const total = hasOwn
              ? (own as unknown[]).length
              : (Array.isArray(sharedOptions) ? sharedOptions.length : 0);
            if (typeof cap !== "number" || !Number.isInteger(cap) || cap < 1) {
              errors.push(`${rowPrefix}.maxChoices: целое число не меньше единицы`);
            } else if (cap > total) {
              errors.push(
                `${rowPrefix}.maxChoices: разрешено ${cap} ответов, а вариантов ${total}`,
              );
            }
          }
        }
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
  // ─── Шкала базового критерия: ровно 0–10 ─────────────────────────────
  //
  // Правило переписывалось дважды за один день, и обе прежние редакции были
  // недостаточны — это стоит записать, чтобы не переписать третий раз.
  //
  // Стояло «ровно 1–10». Анкета заказчика пришла на 0–10 и отвергалась целиком.
  //
  // Стало «любая шкала, лишь бы у всех критериев одна». Дыра открылась сразу:
  // расчёты Приложения 2 читают баллы АБСОЛЮТНЫМИ порогами — доля 8–10,
  // промоутеры 9–10, детракторы 0–6. Пороги заданы заказчиком и осмысленны
  // ровно на 0–10. Анкета на 1–5 проходила бы валидатор, а интегральный индекс
  // удовлетворённости выходил бы 0.0 и NPS −1.0 — молча, числами правильного
  // вида. Проверка, которая пропускает такое, защищает хуже, чем её отсутствие:
  // она создаёт уверенность.
  //
  // Решение владельца 17.09.2026: базовым критериям запрещена любая шкала кроме
  // 0–10. Ключ `baseKey` — это контракт с расчётом, а не имя колонки. Своя
  // шкала остаётся доступной вопросу БЕЗ `baseKey`: он не попадёт ни в индекс,
  // ни в сравнение с корпусом, и никакой порог его не прочтёт.
  for (let i = 0; i < questions.length; i++) {
    const q = questions[i];
    if (typeof q !== "object" || q === null) continue;
    const question = q as Record<string, unknown>;
    if (!question.baseKey) continue;
    if (question.scaleMin !== BASE_SCALE_MIN || question.scaleMax !== BASE_SCALE_MAX) {
      errors.push(
        `questions[${i}]: базовый критерий «${String(question.baseKey)}» должен быть на ` +
          `шкале ${BASE_SCALE_MIN}–${BASE_SCALE_MAX}, получено ` +
          `${String(question.scaleMin)}–${String(question.scaleMax)}`,
      );
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