import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

/**
 * Номер сцены под кадром.
 *
 * ─── Зачем ────────────────────────────────────────────────────────────────
 * Ячейка подписана таймкодом, и по таймкоду её находят в ролике. Но ссылаются
 * на сцену в разговоре не временем, а номером: «посмотри сцену 47» короче и
 * устойчивее, чем «посмотри 12:03–12:19». В отчёте и в ответах персон сцены уже
 * нумерованы, а на экране номера не было — сопоставить их было нечем.
 *
 * ─── Что нумеруется ───────────────────────────────────────────────────────
 * Только сцены. Первая ячейка таймлайна может быть репликами ДО первой сцены
 * (`scene === null`, подпись «до первой сцены») — это не сцена, и номера у неё
 * нет. Нумерация подряд по ячейкам дала бы сдвиг на единицу против отчёта,
 * причём молча.
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

const src = code(read("components/agora/Timeline.tsx"));

test("ячейка получает номер сцены отдельным props", () => {
  assert.ok(
    /sceneNumber/.test(src),
    "номер приезжает в ячейку явно, а не вычисляется из индекса внутри неё",
  );

  const cellProps = /<Cell[\s\S]*?\/>/.exec(src)?.[0] ?? "";
  assert.ok(
    /sceneNumber=\{/.test(cellProps),
    `номер передаётся ячейке: ${cellProps.replace(/\s+/g, " ").slice(0, 200)}`,
  );
});

test("номер допускает отсутствие: реплики до первой сцены сценой не считаются", () => {
  assert.ok(
    /sceneNumber:\s*number\s*\|\s*null/.test(src),
    "тип номера — number | null: у ячейки «до первой сцены» номера нет",
  );
  assert.ok(
    /cell\.scene\s*(!==|===)\s*null|cell\.scene\s*\?/.test(src),
    "нумеруются только ячейки со сценой, иначе номера разойдутся с отчётом",
  );
});

/**
 * Обёртка кадра: её классы, и всё, что до закрывающего тега.
 *
 * Ищется по СВОЙСТВУ («span с flex-col, внутри которого кадр»), а не по
 * порядку слов в className. Первая редакция требовала подряд `flex flex-col`
 * и покраснела на верном коде, где между ними стоит `shrink-0`. Это третий
 * такой случай за две сессии: тест выбирает маркер вместо свойства, и маркер
 * оказывается не тем.
 */
function imageColumn(): { classes: string; body: string } {
  for (const m of src.matchAll(/<span className="([^"]*)"\s*>/g)) {
    const classes = m[1];
    if (!/\bflex\b/.test(classes) || !/\bflex-col\b/.test(classes)) continue;
    const body = src.slice(m.index ?? 0, (m.index ?? 0) + 1400);
    if (/<img/.test(body)) return { classes, body };
  }
  return { classes: "", body: "" };
}

test("номер стоит под кадром, а не рядом с таймкодом", () => {
  const { body: column } = imageColumn();
  assert.ok(column, "кадр обёрнут в колонку (span с flex-col)");
  assert.ok(/<img/.test(column), "в колонке лежит кадр");
  assert.ok(
    /sceneNumber/.test(column),
    "номер лежит в той же колонке, что и кадр — то есть под ним",
  );

  const img = column.indexOf("<img");
  const num = column.indexOf("sceneNumber");
  assert.ok(img < num, "номер идёт ПОСЛЕ кадра в разметке, то есть ниже него");
});

test("защита кадра от сжатия не потеряна при переносе в колонку", () => {
  // `shrink-0` держал кадр от сжатия в узкой колонке. Переехав с img на
  // обёртку, он обязан остаться: без него 80 пикселей превью схлопываются.
  const { classes } = imageColumn();
  assert.ok(classes, "обёртка кадра найдена");
  assert.ok(
    /\bshrink-0\b/.test(classes),
    `обёртка кадра не сжимается, объявлено: ${classes}`,
  );
});
