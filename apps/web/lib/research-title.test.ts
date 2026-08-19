import assert from "node:assert/strict";
import { test } from "node:test";

import { normalizeTitle, researchTitle } from "./research-title.ts";

/**
 * Заголовок исследования: что показывать и в каком порядке.
 *
 * Три источника, и они не равноценны. Название, данное человеком, — это то,
 * ЗАЧЕМ делалось исследование. Имя файла — факт о загрузке. Ключ S3 — вообще
 * внутренность, которая попала на экран по недосмотру и которую владелец
 * увидел в списке как заголовок:
 *
 *     tenants/de15d1e3-…/uploads/f77c2e53-….mp4
 */

test("название человека важнее имени файла", () => {
  assert.equal(
    researchTitle({ title: "Ролик для ВК, апрель", sourceName: "15 min.mp4", videoRef: "k" }),
    "Ролик для ВК, апрель",
  );
});

test("без названия показывается имя файла", () => {
  assert.equal(
    researchTitle({ title: null, sourceName: "15 min.mp4", videoRef: "tenants/x/uploads/y.mp4" }),
    "15 min.mp4",
  );
});

test("пустое название не считается названием", () => {
  // Строка из пробелов доедет из формы, если её не отсечь, и заголовок
  // исчезнет с экрана совсем — выглядит это как потеря прогона.
  assert.equal(
    researchTitle({ title: "   ", sourceName: "15 min.mp4", videoRef: "k" }),
    "15 min.mp4",
  );
});

test("без имени файла — ключ хранилища, но только как последнее средство", () => {
  assert.equal(
    researchTitle({ title: null, sourceName: null, videoRef: "tenants/x/uploads/y.mp4" }),
    "tenants/x/uploads/y.mp4",
  );
});

test("когда нет ничего, заголовок всё равно есть", () => {
  // Пустой заголовок делает строку списка некликабельной на вид: не за что
  // зацепиться глазом, и прогон выглядит битым.
  assert.equal(researchTitle({ title: null, sourceName: null, videoRef: null }), "Прогон без материала");
});

test("normalizeTitle обрезает пробелы и отвергает пустое", () => {
  assert.equal(normalizeTitle("  Апрельский ролик  "), "Апрельский ролик");
  assert.equal(normalizeTitle("   "), null);
  assert.equal(normalizeTitle(undefined), null);
});

test("normalizeTitle отвергает слишком длинное, а не режет молча", () => {
  // Обрезка по длине — это правка чужого текста без ведома автора: человек
  // видит одно, сохраняется другое.
  assert.throws(() => normalizeTitle("я".repeat(201)), /200/);
});
