import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CONTEXT_ACCEPT,
  CONTEXT_LIMIT_CHARS,
  contextFileError,
  normalizeContext,
} from "./context-file.ts";

/**
 * Файл дополнительного контекста для персон (#31).
 *
 * ─── Что было ───────────────────────────────────────────────────────────────
 * Зона выбора файла существовала и запоминала ИМЯ И РАЗМЕР. Содержимое не
 * читалось, никуда не отправлялось и ни во что не попадало. Подпись при этом
 * обещала «pdf, docx, md, xlsx» — четыре формата, ни один из которых не
 * обрабатывался.
 *
 * Со стороны это работающая функция: файл прикладывается, плашка появляется, в
 * резюме видно имя. Узнать, что персоны его не видели, можно было только по
 * ответам — то есть никак.
 */

test("текстовые форматы принимаются, остальные — нет", () => {
  assert.equal(contextFileError("аудитория.txt", "текст"), null);
  assert.equal(contextFileError("аудитория.md", "# текст"), null);
  assert.match(contextFileError("аудитория.pdf", "текст") ?? "", /txt.*md|md.*txt/i);
  assert.match(contextFileError("аудитория.docx", "текст") ?? "", /txt|md/i);
});

test("регистр расширения значения не имеет", () => {
  assert.equal(contextFileError("A.TXT", "текст"), null);
  assert.equal(contextFileError("A.Md", "текст"), null);
});

test("файл длиннее лимита отвергается с числом", () => {
  const long = "я".repeat(CONTEXT_LIMIT_CHARS + 1);
  const err = contextFileError("a.txt", long) ?? "";
  assert.match(err, new RegExp(String(CONTEXT_LIMIT_CHARS)));
  assert.match(err, /\d/, "человеку нужно знать, насколько он превысил");
});

test("ровно лимит — ещё можно", () => {
  assert.equal(contextFileError("a.txt", "я".repeat(CONTEXT_LIMIT_CHARS)), null);
});

test("пустой файл — это ошибка, а не пустой контекст", () => {
  // Молча принятый пустой файл выглядит как приложенный контекст, которого нет.
  assert.match(contextFileError("a.txt", "   \n\n ") ?? "", /пуст/i);
});

test("нормализация схлопывает пустые строки и режет края", () => {
  assert.equal(normalizeContext("  a\n\n\n\nb  \n"), "a\n\nb");
});

test("лимит считается по НОРМАЛИЗОВАННОМУ тексту", () => {
  // Иначе файл, состоящий из переводов строк, отвергался бы за объём, которого
  // в модель не поедет.
  const padded = "я".repeat(CONTEXT_LIMIT_CHARS) + "\n".repeat(500);
  assert.equal(contextFileError("a.txt", padded), null);
});

test("список принимаемых расширений — тот же, что показан в интерфейсе", () => {
  assert.match(CONTEXT_ACCEPT, /\.txt/);
  assert.match(CONTEXT_ACCEPT, /\.md/);
  assert.doesNotMatch(CONTEXT_ACCEPT, /pdf|docx|xlsx/);
});
