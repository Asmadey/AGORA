import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  checkTemplateContract,
  describeViolation,
  placeholderNames,
} from "./prompt-contract.ts";

/** Дефолт отчёта — то, что подставляет стадия аналитики. */
const REPORT_DEFAULT = [
  "Агрегат: {{aggregate}}",
  "Точки риска: {{retention_risk_points}}",
  "Ответы: {{all_persona_answers}}",
  "Анкета: {{survey}}",
  "Материал: {{content_title}}",
  "Флаги: {{qa_flags}}",
].join("\n");

test("заглушка «test {{content}}» больше не сохраняется", () => {
  const v = checkTemplateContract("test {{content}}", REPORT_DEFAULT);
  assert.ok(v, "шаблон принят, хотя стадия не даёт ни одной его переменной");
  assert.deepEqual(v.unknown, ["content"]);
  assert.equal(v.missing.length, 6);
});

test("переменная, которой стадия не даёт, названа поимённо", () => {
  const v = checkTemplateContract(REPORT_DEFAULT + "\n{{video_url}}", REPORT_DEFAULT);
  assert.deepEqual(v?.unknown, ["video_url"]);
  assert.deepEqual(v?.missing, []);
  assert.match(describeViolation("analytics.report", v!), /video_url/);
});

test("выброшенная переменная стадии названа поимённо", () => {
  const without = REPORT_DEFAULT.replace("Ответы: {{all_persona_answers}}\n", "");
  const v = checkTemplateContract(without, REPORT_DEFAULT);
  assert.deepEqual(v?.missing, ["all_persona_answers"]);
  assert.match(describeViolation("analytics.report", v!), /all_persona_answers/);
});

test("переписанный текст с теми же переменными проходит", () => {
  const rewritten =
    "Ты аналитик. Дано: {{aggregate}}, {{retention_risk_points}}, " +
    "{{all_persona_answers}}, {{survey}}, {{content_title}}, {{qa_flags}}. Ответь JSON.";
  assert.equal(checkTemplateContract(rewritten, REPORT_DEFAULT), null);
});

test("порядок и повторы переменных не важны", () => {
  const shuffled =
    "{{qa_flags}} {{survey}} {{aggregate}} {{aggregate}} {{content_title}} " +
    "{{all_persona_answers}} {{retention_risk_points}}";
  assert.equal(checkTemplateContract(shuffled, REPORT_DEFAULT), null);
});

test("дефолта без переменных достаточно, чтобы проверка не мешала", () => {
  assert.equal(checkTemplateContract("что угодно", ""), null);
  assert.equal(checkTemplateContract("что угодно", null), null);
});

test("пробелы внутри скобок — та же переменная", () => {
  assert.deepEqual(placeholderNames("{{ aggregate }} и {{aggregate}}"), ["aggregate"]);
});

/**
 * ─── Шов ────────────────────────────────────────────────────────────────────
 *
 * Механизм, который никто не зовёт, — это ровно тот дефект, из-за которого
 * заглушка и доехала до боевого прогона: `validateVariables` был импортирован в
 * маршруте и не вызван. Поэтому проверка идёт по исходнику маршрута.
 */
const ROUTE = await readFile(
  new URL("../app/api/prompts/route.ts", import.meta.url),
  "utf8",
);

test("маршрут сохранения промпта зовёт сверку с контрактом", () => {
  assert.match(ROUTE, /checkTemplateContract\(/);
});

test("отказ по контракту — это 400, а не тихая запись", () => {
  const call = ROUTE.slice(ROUTE.indexOf("checkTemplateContract("));
  assert.match(call, /status:\s*400/);
});

test("тавтологическая проверка не вернулась", () => {
  assert.doesNotMatch(ROUTE, /^\s*validateVariables\(/m);
});
