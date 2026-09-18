import assert from "node:assert/strict";
import { test } from "node:test";

import { parseInline, parseMarkdown, type MdBlock, type MdInline } from "./markdown.ts";

/**
 * Разбор markdown, который пишет модель в чате (#28).
 *
 * ─── Откуда взят синтаксис ────────────────────────────────────────────────
 * Не из спецификации CommonMark, а из настоящего ответа на боевом. Прогон
 * 0092, вопрос «как именно определили ценность "крепкая семья"?», ответ
 * аналитика — вот его первые строки ровно так, как они лежат в базе:
 *
 *     …она была выявлена как **эмоциональный триггер**, вызывающий…
 *
 *     Вот как это сработало в данных:
 *
 *     1.  **Ключевой триггер:** Фраза героя о возвращении к маме…
 *         *   Персона 2 отметила: «…это святое» (цитата из вербатима).
 *         *   Персона 5 написала: «…близка мне как женщине…».
 *
 *     2.  **Эмоциональный отклик:** Эта ценность вызвала доминирование…
 *
 * Отсюда набор, который обязан разбираться: жирный текст, нумерованный
 * список, вложенный в него ненумерованный, пустая строка как граница абзаца.
 * Два пробела после «1.» и три после «*» — не опечатка, модель пишет так.
 *
 * ─── Почему разбор в `lib/`, а не в компоненте ────────────────────────────
 * `npm test` собирает только `lib/**`. Логика, оставленная в `.tsx`, тестами
 * не покрывается вовсе — а разбор чужого текста ошибается именно на краях,
 * которые глазами не перебрать.
 *
 * ─── Почему узлы, а не строка HTML ────────────────────────────────────────
 * Текст приходит от модели. Строка HTML рано или поздно доедет до
 * `dangerouslySetInnerHTML`, и тогда `<img onerror=…>` в ответе модели станет
 * исполняемым. Разбор возвращает данные; в разметку их превращает React,
 * который экранирует текст сам и по-другому не умеет.
 */

/** Собрать текст блока без учёта разметки — для проверок «что написано». */
function plain(spans: MdInline[]): string {
  return spans.map((s) => s.text).join("");
}

function blockText(b: MdBlock): string {
  if (b.type === "list") return b.items.map((i) => plain(i.spans)).join("|");
  return plain(b.spans);
}

// ─── Инлайн ─────────────────────────────────────────────────────────────────

test("**жирный** становится узлом strong, а звёздочки исчезают", () => {
  const spans = parseInline("она была выявлена как **эмоциональный триггер**, вызывающий отклик");
  assert.deepEqual(
    spans.map((s) => s.type),
    ["text", "strong", "text"],
  );
  assert.equal(spans[1].text, "эмоциональный триггер");
  assert.ok(
    !plain(spans).includes("*"),
    "звёздочки — разметка, а не текст: в выводе их быть не должно",
  );
});

test("*курсив* и _курсив_ разбираются, но жирный имеет приоритет", () => {
  assert.deepEqual(
    parseInline("это *важно* и _тоже важно_").map((s) => [s.type, s.text]),
    [
      ["text", "это "],
      ["em", "важно"],
      ["text", " и "],
      ["em", "тоже важно"],
    ],
  );
  // `**x**` — это не два пустых курсива вокруг `x`.
  assert.deepEqual(
    parseInline("**x**").map((s) => s.type),
    ["strong"],
  );
});

test("`код` разбирается и внутри него разметка не работает", () => {
  const spans = parseInline("поле `**raw**` остаётся как есть");
  assert.deepEqual(
    spans.map((s) => s.type),
    ["text", "code", "text"],
  );
  assert.equal(spans[1].text, "**raw**");
});

test("одинокая звёздочка остаётся текстом, а не съедает остаток строки", () => {
  const spans = parseInline("5 * 3 = 15");
  assert.equal(plain(spans), "5 * 3 = 15");
  assert.ok(
    spans.every((s) => s.type === "text"),
    "незакрытая разметка — это текст. Иначе ответ модели молча теряет хвост",
  );
});

test("подчёркивание внутри слова не курсив", () => {
  // `snake_case_name` встречается в ответах про поля пакета.
  assert.equal(plain(parseInline("snake_case_name")), "snake_case_name");
  assert.ok(parseInline("snake_case_name").every((s) => s.type === "text"));
});

// ─── Блоки ──────────────────────────────────────────────────────────────────

test("пустая строка делит абзацы, перенос внутри абзаца сохраняется", () => {
  const blocks = parseMarkdown("первый абзац\nвторая строка\n\nвторой абзац");
  assert.equal(blocks.length, 2);
  assert.equal(blocks[0].type, "paragraph");
  assert.equal(blockText(blocks[0]), "первый абзац\nвторая строка");
  assert.equal(blockText(blocks[1]), "второй абзац");
});

test("ненумерованный список: -, * и + одинаково", () => {
  for (const marker of ["-", "*", "+"]) {
    const blocks = parseMarkdown(`${marker} первый\n${marker} второй`);
    assert.equal(blocks.length, 1, `маркер ${marker}`);
    const list = blocks[0];
    assert.equal(list.type, "list");
    if (list.type !== "list") return;
    assert.equal(list.ordered, false);
    assert.deepEqual(
      list.items.map((i) => plain(i.spans)),
      ["первый", "второй"],
    );
  }
});

test("нумерованный список сохраняет номер первого пункта", () => {
  const blocks = parseMarkdown("3. третий\n4. четвёртый");
  const list = blocks[0];
  assert.equal(list.type, "list");
  if (list.type !== "list") return;
  assert.equal(list.ordered, true);
  assert.equal(list.start, 3, "список, начатый с 3, не должен показывать 1");
});

test("вложенный список остаётся внутри своего пункта", () => {
  // Ровно та форма, что пришла с боевого: два пробела после «1.», отступ в
  // четыре пробела, маркер «*» и три пробела за ним.
  const src = [
    "1.  **Ключевой триггер:** Фраза героя о возвращении к маме.",
    "    *   Персона 2 отметила: «это святое».",
    "    *   Персона 5 написала: «близка мне».",
    "",
    "2.  **Эмоциональный отклик:** Эта ценность вызвала доминирование эмоций.",
  ].join("\n");

  const blocks = parseMarkdown(src);
  assert.equal(blocks.length, 1, "оба пункта — один список, а не два");
  const list = blocks[0];
  assert.equal(list.type, "list");
  if (list.type !== "list") return;

  assert.equal(list.ordered, true);
  assert.equal(list.items.length, 2);

  const first = list.items[0];
  assert.equal(first.spans[0].type, "strong");
  assert.equal(first.spans[0].text, "Ключевой триггер:");

  assert.equal(first.children.length, 1, "вложенный список — ребёнок пункта");
  const nested = first.children[0];
  assert.equal(nested.type, "list");
  if (nested.type !== "list") return;
  assert.equal(nested.ordered, false);
  assert.equal(nested.items.length, 2);
  assert.ok(plain(nested.items[0].spans).includes("Персона 2"));

  assert.equal(list.items[1].children.length, 0);
});

test("заголовки ## разбираются по уровню", () => {
  const blocks = parseMarkdown("## Что показало исследование\n\nтекст");
  assert.equal(blocks[0].type, "heading");
  if (blocks[0].type !== "heading") return;
  assert.equal(blocks[0].level, 2);
  assert.equal(plain(blocks[0].spans), "Что показало исследование");
});

test("решётка внутри строки заголовком не становится", () => {
  const blocks = parseMarkdown("рост #1 по выборке");
  assert.equal(blocks[0].type, "paragraph");
});

test("пустой и пробельный вход дают пустой список блоков", () => {
  assert.deepEqual(parseMarkdown(""), []);
  assert.deepEqual(parseMarkdown("   \n\n  "), []);
});

// ─── Безопасность ───────────────────────────────────────────────────────────

test("HTML из ответа модели остаётся текстом", () => {
  // Разбор не обязан ничего экранировать — он и не должен: экранирует React.
  // Обязан он другое: не выдавать за разметку то, что разметкой не является.
  const blocks = parseMarkdown('<img src=x onerror="alert(1)"> и <b>жирный</b>');
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].type, "paragraph");
  assert.equal(
    blockText(blocks[0]),
    '<img src=x onerror="alert(1)"> и <b>жирный</b>',
    "теги проезжают как обычные символы, а не как узлы",
  );
});

test("разбор возвращает данные, а не строку разметки", () => {
  const blocks = parseMarkdown("**жирный**");
  assert.ok(Array.isArray(blocks));
  assert.equal(typeof blocks[0], "object");
  const asText = JSON.stringify(blocks);
  assert.ok(
    !asText.includes("<strong"),
    "в выводе не должно быть HTML: иначе он доедет до dangerouslySetInnerHTML",
  );
});

test("длинный ответ разбирается за разумное время", () => {
  // Ответ аналитика на боевом — около 1.5 КБ; берём с запасом в сто раз,
  // чтобы поймать разбор с квадратичной сложностью, а не измерять машину.
  const src = "1.  **Пункт:** текст со *вставкой* и `кодом`.\n".repeat(2000);
  const t0 = Date.now();
  const blocks = parseMarkdown(src);
  assert.ok(Date.now() - t0 < 2000, "разбор не должен быть квадратичным");
  const list = blocks[0];
  assert.equal(list.type, "list");
  if (list.type !== "list") return;
  assert.equal(list.items.length, 2000);
});
