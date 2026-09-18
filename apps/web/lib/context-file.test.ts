import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CONTEXT_ACCEPT,
  CONTEXT_LIMIT_CHARS,
  contextConflictWarning,
  contextGroundingNote,
  contextFileError,
  detectContextConflicts,
  isTextContextFile,
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

test("текстовые и бинарные форматы принимаются, docx и старый xls — нет", () => {
  assert.equal(contextFileError("аудитория.txt", "текст"), null);
  assert.equal(contextFileError("аудитория.md", "# текст"), null);
  assert.equal(contextFileError("аудитория.pdf"), null);
  assert.equal(contextFileError("аудитория.xlsx"), null);
  assert.match(contextFileError("аудитория.docx", "текст") ?? "", /txt|md/i);

  // `.xls` — это BIFF, а разбор таблиц в воркере делает openpyxl, читающий
  // только OOXML. Принять файл и упасть при разборе значило бы узнать о его
  // непригодности после запуска, за который уже заплачено.
  const legacy = contextFileError("аудитория.xls", undefined, 1024);
  assert.ok(legacy, "формат, который воркер не прочитает, нельзя принимать молча");
  assert.match(legacy, /\.xlsx/, "человеку нужно сказать, во что пересохранить");
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
  assert.match(CONTEXT_ACCEPT, /\.pdf/);
  assert.match(CONTEXT_ACCEPT, /\.xls/);
  assert.match(CONTEXT_ACCEPT, /\.xlsx/);
  assert.doesNotMatch(CONTEXT_ACCEPT, /docx/);
});

test("конкретные доли и оценки получают предупреждение", () => {
  const text = "70 % женщин, возраст 18-24, средний балл 8,5.";
  assert.deepEqual(
    detectContextConflicts(text).map((item) => item.kind),
    ["demographics", "scores"],
  );
  assert.match(contextConflictWarning(text) ?? "", /Предупреждение/);
  assert.match(contextConflictWarning(text) ?? "", /корпус/);
});

test("описание ниши и города без чисел не предупреждает о конфликте", () => {
  assert.equal(
    contextConflictWarning("Наша аудитория живёт в крупных городах и любит разбирать сюжеты."),
    null,
  );
});

test("бинарные форматы проходят без притворной проверки текста", () => {
  assert.equal(isTextContextFile("brief.pdf"), false);
  assert.equal(isTextContextFile("brief.md"), true);
  assert.match(contextGroundingNote(), /корпус/);
});
