import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { BLOCKED_SETS_QUERY, blockedReason, toBlocked } from "./audience-delete.ts";

/**
 * Набор, который СЕЙЧАС генерируется, удалять нельзя.
 *
 * 18.09.2026 его удалили посреди генерации. Задача воркера продолжала звать
 * модель двадцать семь минут, писала прогресс в несуществующую строку и держала
 * очередь: прогон 0093, стоявший следующим, не начинался и выглядел зависшим.
 *
 * Отказ удаления закрывал только наборы, на которых стоит прогон
 * (`JOIN tasks`). «Сейчас генерируется» не было защищено ничем — притом что
 * именно в этом состоянии удаление и вредно: у готового набора терять нечего,
 * кроме него самого, а у генерирующегося — ещё и оплаченную работу.
 */

test("генерирующийся набор попадает в отказ", () => {
  const blocked = toBlocked([
    { id: "a", name: "Сто персон", runs: "0", status: "generating" },
  ]);
  assert.equal(blocked.length, 1);
  assert.equal(blocked[0].reason, "generating");
  assert.equal(blocked[0].runs, 0);
});

test("набор с прогонами попадает в отказ по прежней причине", () => {
  const blocked = toBlocked([
    { id: "b", name: "Двадцать персон", runs: "3", status: "ready" },
  ]);
  assert.equal(blocked[0].reason, "runs");
  assert.equal(blocked[0].runs, 3);
});

test("прогоны важнее генерации: их потеря необратима", () => {
  const blocked = toBlocked([
    { id: "c", name: "Оба", runs: "2", status: "generating" },
  ]);
  assert.equal(blocked[0].reason, "runs");
});

test("у каждой причины свой текст — «на них считались прогоны» про генерацию неправда", () => {
  const runs = blockedReason({ id: "b", name: "n", runs: 3, reason: "runs" });
  const gen = blockedReason({ id: "a", name: "n", runs: 0, reason: "generating" });
  assert.notEqual(runs, gen);
  // Суть требования не в слове, а в том, чего в тексте быть НЕ должно:
  // отправить человека искать прогоны, которых нет, — и есть тот дефект,
  // ради которого причина стала различаться.
  assert.ok(!/прогон/i.test(gen), `текст про генерацию не упоминает прогоны: ${gen}`);
  assert.match(runs, /прогон/i);
});

test("запрос отбирает и прогоны, и генерацию", () => {
  assert.match(BLOCKED_SETS_QUERY, /LEFT JOIN tasks/);
  assert.match(BLOCKED_SETS_QUERY, /status = 'generating'/);
});

test("deletePersonaSets ходит именно за этим запросом, а не за своей копией", () => {
  const lib = readFileSync(
    join(process.cwd(), "lib/server/personas.ts"),
    "utf8",
  );
  const fn = lib.slice(lib.indexOf("export async function deletePersonaSets"));
  assert.ok(
    fn.includes("BLOCKED_SETS_QUERY"),
    "удаление обязано спрашивать общий запрос: своя копия разойдётся с тестом молча",
  );
});
