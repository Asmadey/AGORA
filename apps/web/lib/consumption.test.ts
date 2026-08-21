import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MODEL_LABELS,
  aggregateByDay,
  formatDateRu,
  presetRange,
  totalsOf,
  type ConsumptionItem,
} from "./consumption.ts";

/**
 * Раздел «Статистика»: потребление и расходы (задача владельца 21.08.2026).
 *
 * ─── Что считаем ────────────────────────────────────────────────────────────
 * API контроля затрат cloud.ru отдаёт плоский список строк потребления: дата,
 * название SKU, объём и две суммы — с НДС и без. Продукт использует две модели,
 * и вопрос владельца — сколько потрачено на каждую и сколько всего.
 *
 * ─── Почему модель определяется по названию SKU ─────────────────────────────
 * Другого признака у строки нет: идентификаторы SKU у провайдера непрозрачны и
 * меняются при смене тарифа, а название — то, что видно в его же кабинете.
 * Незнакомая строка не выбрасывается: её видно отдельной величиной, иначе
 * подключение третьей модели молча пропало бы из отчёта о расходах.
 */

const ITEMS: ConsumptionItem[] = [
  { usedate: "2026-08-12T00:00:00Z", servname: "Qwen3 VL 30B (Vision)", usefact: 0.1896, amount: 8.35, amount_nds: 10.02 },
  { usedate: "2026-08-12T10:00:00Z", servname: "Qwen3.6-35B-A3B", usefact: 3.1884, amount: 632.54, amount_nds: 759.05 },
  { usedate: "2026-08-13T00:00:00Z", servname: "Qwen3.6-35B-A3B", usefact: 0.0378, amount: 7.31, amount_nds: 8.77 },
];

test("строки сворачиваются по дню и по модели", () => {
  const rows = aggregateByDay(ITEMS);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].date, "2026-08-12");
  assert.equal(rows[0].vision.tokens, 0.1896);
  assert.equal(rows[0].vision.rub, 10.02);
  assert.equal(rows[0].text.tokens, 3.1884);
  assert.equal(rows[0].text.rub, 759.05);
});

test("«Итого» за день — сумма обеих моделей", () => {
  const [first] = aggregateByDay(ITEMS);
  assert.equal(first.totalRub, 769.07);
});

test("дни идут по возрастанию, даже если пришли вперемешку", () => {
  const shuffled = [ITEMS[2], ITEMS[0], ITEMS[1]];
  assert.deepEqual(aggregateByDay(shuffled).map((r) => r.date), ["2026-08-12", "2026-08-13"]);
});

test("несколько строк одного дня и одной модели складываются", () => {
  const rows = aggregateByDay([ITEMS[1], ITEMS[1]]);
  assert.equal(rows[0].text.tokens, 6.3768);
  assert.equal(rows[0].text.rub, 1518.1);
});

test("итоги по колонкам считаются по тем же строкам, что показаны", () => {
  const t = totalsOf(aggregateByDay(ITEMS));
  assert.equal(t.vision.tokens, 0.1896);
  assert.equal(t.text.tokens, 3.2262);
  assert.equal(t.totalRub, 777.84);
  assert.equal(t.totalRubNoVat, 648.2);
});

test("незнакомая модель не теряется молча", () => {
  // Иначе подключение третьей модели уменьшило бы «Итого» без объяснения.
  const rows = aggregateByDay([
    ...ITEMS,
    { usedate: "2026-08-12T00:00:00Z", servname: "Что-то новое", usefact: 1, amount: 100, amount_nds: 120 },
  ]);
  assert.equal(rows[0].other.rub, 120);
  assert.equal(rows[0].totalRub, 889.07, "«Итого» обязано включать неизвестное");
});

test("дата показывается по-русски", () => {
  assert.equal(formatDateRu("2026-08-12"), "12.08.2026");
  assert.equal(formatDateRu("2026-12-01T10:00:00Z"), "01.12.2026");
});

test("пресет «7 дней» включает сегодня и шесть предыдущих", () => {
  const r = presetRange("7d", new Date("2026-08-21T12:00:00Z"));
  assert.equal(r.from, "2026-08-15");
  assert.equal(r.to, "2026-08-21");
});

test("пресет «текущий месяц» начинается с первого числа", () => {
  const r = presetRange("month", new Date("2026-08-21T12:00:00Z"));
  assert.equal(r.from, "2026-08-01");
  assert.equal(r.to, "2026-08-21");
});

test("у обеих моделей есть человеческая подпись", () => {
  assert.ok(MODEL_LABELS.vision.length > 0);
  assert.ok(MODEL_LABELS.text.length > 0);
});

test("пустой период даёт нули, а не пустоту", () => {
  const t = totalsOf([]);
  assert.equal(t.totalRub, 0);
  assert.equal(t.vision.tokens, 0);
});
