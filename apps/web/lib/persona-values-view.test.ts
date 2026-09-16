import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { fieldLabel } from "./persona-dna-labels.ts";

/**
 * Карточка персоны: где стоят ценности и как они выглядят.
 *
 * ─── Что меняется и почему ────────────────────────────────────────────────
 * Ценностей стало пять вместо трёх (16.09.2026), и блок из второстепенного
 * стал тем, ради чего карточку открывают: именно ценности объясняют, почему
 * персона отреагировала на материал так, а не иначе.
 *
 * Отсюда три требования: подпись «ВЦИОМ» вместо «Важные ценности», блок сразу
 * после «Описания», и пять плашек столбцом, а не в строку.
 *
 * ─── Почему порядок — список приоритетов, а не whitelist ──────────────────
 * Карточка обходит ФАКТИЧЕСКИЙ объект DNA, и это требование cdd #6: «ни одно
 * поле не потеряно при рендере». Перечисленный вручную список блоков это
 * требование сломал бы — новое поле в схеме перестало бы показываться, и
 * заметить это было бы можно только глазами.
 *
 * Поэтому порядок задаётся приоритетом ИЗВЕСТНЫХ блоков, а всё незнакомое
 * идёт следом в исходном порядке. Тест держит обе половины.
 */

const WEB = new URL("..", import.meta.url).pathname;

function read(rel: string): string {
  const p = join(WEB, rel);
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}

/** Без комментариев: разбор идёт по коду, а не по его объяснению. */
function code(text: string): string {
  return text
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

const view = code(read("components/agora/PersonaDnaView.tsx"));

// ─── Подпись ────────────────────────────────────────────────────────────────

test("подпись списка ценностей — ВЦИОМ", () => {
  assert.equal(fieldLabel("important_values"), "ВЦИОМ");
});

test("остальные подписи блока не тронуты", () => {
  assert.equal(fieldLabel("worldview"), "Мировоззрение");
  assert.equal(fieldLabel("religious_attitude"), "Отношение к религии");
  assert.equal(fieldLabel("political_orientation"), "Политическая ориентация");
});

// ─── Порядок блоков ─────────────────────────────────────────────────────────

test("ценности идут первым блоком — сразу после Описания", async () => {
  const { orderCategories } = await import("./persona-dna-labels.ts");
  const order = orderCategories([
    "demographics",
    "big_five",
    "values_and_beliefs",
    "viewer_behavior",
  ]);
  assert.equal(order[0], "values_and_beliefs");
});

test("незнакомый блок не теряется", () => {
  // cdd #6: ни одно поле DNA не потеряно при рендере. Порядок задаётся
  // приоритетом, а не белым списком, — иначе новое поле схемы исчезло бы молча.
  return import("./persona-dna-labels.ts").then(({ orderCategories }) => {
    const input = ["demographics", "нечто_новое", "values_and_beliefs"];
    const order = orderCategories(input);
    assert.equal(order.length, input.length);
    assert.ok(order.includes("нечто_новое"));
    assert.equal(order[0], "values_and_beliefs");
  });
});

test("карточка использует порядок, а не сырой Object.entries", () => {
  assert.ok(
    /orderCategories/.test(view),
    "порядок блоков задаётся явно, а не порядком ключей в JSON",
  );
});

// ─── Пять плашек столбцом ───────────────────────────────────────────────────

test("ценности рисуются столбцом, а не строкой", () => {
  // Пять длинных названий («Служение Отечеству и ответственность за его судьбу»)
  // в строку не помещаются и рвутся посреди слова.
  assert.ok(
    /flex-col/.test(view),
    "список ценностей выкладывается в колонку",
  );
  assert.ok(
    /items-start|self-start|w-fit/.test(view),
    "плашка обтягивает текст, а не растягивается на всю ширину колонки",
  );
});

test("значение с длинным списком уходит на свою строку под подписью", () => {
  // Подпись и пять плашек в одной строке `flex` прижали бы плашки к правому
  // краю и оставили бы им треть ширины.
  assert.ok(
    /basis-full|w-full|block/.test(view),
    "длинный список занимает всю ширину под подписью",
  );
});
