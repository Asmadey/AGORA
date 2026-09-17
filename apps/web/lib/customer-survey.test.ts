import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import {
  CUSTOMER_BLOCKS,
  MANDATORY_QUESTIONS,
  themesOf,
  withSelectedThemes,
} from "./customer-survey.ts";

/**
 * Обязательная анкета доезжает до конструктора из того же файла, что и до воркера.
 *
 * ─── Почему это отдельная проверка ─────────────────────────────────────────
 * Соблазн понятный: переписать пятнадцать вопросов константой в TSX — «так
 * проще, чем тащить JSON через границу пакетов». Ровно так в этом репозитории
 * появились четыре копии перечня типов вопроса и две копии перечня ценностей,
 * и одна из копий полтора месяца молча отставала от схемы.
 *
 * Здесь проверяется не «константы верные», а «константы те же самые»: состав
 * сверяется с `data/survey/customer_2026.json` прямым чтением файла. Если
 * кто-то добавит четырнадцатую эмоцию в интерфейсе и забудет про данные —
 * тест покраснеет, а не отчёт.
 */

const REPO = new URL("../../../", import.meta.url).pathname;
const RAW = JSON.parse(
  readFileSync(join(REPO, "data/survey/customer_2026.json"), "utf8"),
) as { questions: Record<string, unknown>[]; blocks: { id: string }[] };

test("состав вопросов совпадает с файлом данных", () => {
  assert.equal(MANDATORY_QUESTIONS.length, 15);
  assert.deepEqual(
    MANDATORY_QUESTIONS.map((q) => q.id),
    RAW.questions.map((q) => q.id),
  );
});

test("блоки совпадают с файлом данных", () => {
  assert.deepEqual(
    CUSTOMER_BLOCKS.map((b) => b.id),
    RAW.blocks.map((b) => b.id),
  );
});

test("варианты вопроса об эмоциях не переписаны заново", () => {
  const fromFile = RAW.questions.find((q) => q.number === 7) as {
    options: { id: string; label: string }[];
  };
  const fromLib = MANDATORY_QUESTIONS.find((q) => q.number === 7);
  assert.ok(fromLib?.options);
  assert.deepEqual(
    fromLib.options.map((o) => o.label),
    fromFile.options.map((o) => o.label),
  );
  assert.equal(fromLib.options.length, 15, "13 эмоций плюс два служебных варианта");
});

// ─── Выбор тем ──────────────────────────────────────────────────────────────

test("темы вопроса 9 отдаются списком из десяти", () => {
  const themes = themesOf(9);
  assert.equal(themes.length, 10);
  assert.ok(themes.every((t) => t.id && t.label));
});

test("выбор темы включает все её подтемы и ни одной чужой", () => {
  const survey = withSelectedThemes(["t1", "t3"]);
  const matrix = survey.find((q) => q.number === 9);
  assert.ok(matrix?.rows);
  assert.deepEqual(
    [...new Set(matrix.rows.map((r) => r.themeId))].sort(),
    ["t1", "t3"],
  );
  // Тема 1 — шесть подтем, тема 3 — пять.
  assert.equal(matrix.rows.length, 11);
});

test("вопрос 11 приходит по выбранным темам, а не целиком", () => {
  const survey = withSelectedThemes(["t4"]);
  const impact = survey.find((q) => q.number === 11);
  assert.ok(impact?.rows);
  // У темы 4 в таблице заказчика ДВА подвопроса — это единственная такая тема.
  assert.equal(impact.rows.length, 2);
  assert.ok(impact.rows.every((r) => r.themeId === "t4"));
});

test("без выбранных тем вопросы 9 и 11 из анкеты выпадают", () => {
  const survey = withSelectedThemes([]);
  assert.equal(survey.find((q) => q.number === 9), undefined);
  assert.equal(survey.find((q) => q.number === 11), undefined);
  assert.equal(survey.length, 13, "остальные тринадцать вопросов на месте");
});

test("все десять тем — это 43 подтемы и 11 вопросов воздействия", () => {
  const survey = withSelectedThemes(themesOf(9).map((t) => t.id));
  assert.equal(survey.find((q) => q.number === 9)?.rows?.length, 43);
  assert.equal(survey.find((q) => q.number === 11)?.rows?.length, 11);
});
