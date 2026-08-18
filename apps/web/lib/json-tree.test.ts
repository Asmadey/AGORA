import assert from "node:assert/strict";
import { test } from "node:test";

import { buildTree } from "./json-tree.ts";

test("ветки и листья различаются, путь уникален", () => {
  const tree = buildTree({ aggregate: { nps: -33 }, narrative: ["раз", "два"] });

  const agg = tree.children.find((c) => c.label === "aggregate");
  assert.equal(agg?.kind, "object");
  assert.equal(agg?.preview, "1 поле");
  assert.equal(agg?.children[0].path, "отчёт.aggregate.nps");
  assert.equal(agg?.children[0].preview, "-33");

  const narrative = tree.children.find((c) => c.label === "narrative");
  assert.equal(narrative?.preview, "2 элемента");
});

test("null не превращается в пустоту", () => {
  // Отсутствие значения и пустая строка — разные факты: в отчёте первое значит
  // «не посчитано», второе «посчитано и пусто».
  const tree = buildTree({ nps: null, note: "" });

  assert.equal(tree.children[0].kind, "null");
  assert.equal(tree.children[0].preview, "null");
  assert.equal(tree.children[1].kind, "string");
  assert.equal(tree.children[1].preview, "");
});

test("глубина ограничена, и ветка на пределе честно показывает сводку", () => {
  // Отчёт с пятьюстами ответами разворачивается в десятки тысяч узлов, и
  // браузер встаёт на попытке отрисовать их разом.
  const deep = { a: { b: { c: { d: { e: 1 } } } } };
  const tree = buildTree(deep as never, "корень", "", 2);

  const b = tree.children[0].children[0];
  assert.equal(b.kind, "object");
  assert.deepEqual(b.children, [], "за пределом глубины детей быть не должно");
  assert.equal(b.preview, "1 поле", "сводка обязана остаться — иначе узел выглядит пустым");
});

test("склонение считает по-русски", () => {
  const counts = [1, 2, 5, 11, 21, 22, 25];
  const expected = ["1 поле", "2 поля", "5 полей", "11 полей", "21 поле", "22 поля", "25 полей"];
  counts.forEach((n, i) => {
    const obj = Object.fromEntries(Array.from({ length: n }, (_, k) => [`k${k}`, k]));
    assert.equal(buildTree(obj).preview, expected[i]);
  });
});
