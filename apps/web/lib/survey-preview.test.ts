import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { MANDATORY_QUESTIONS } from "./customer-survey.ts";
import {
  INLINE_OPTIONS_MAX,
  isServiceOption,
  optionsPresentation,
  themeGroups,
} from "./survey-preview.ts";

/**
 * Как конструктор показывает варианты ответа обязательного вопроса.
 *
 * ─── Почему решение живёт здесь, а не в компоненте ─────────────────────────
 * Веб-тесты собирают только `lib/**`. Всё, что оставлено в `.tsx`, не покрыто
 * ничем по построению — так уже разошлась проверка заземления, и так же
 * уцелела третья точка засева анкеты, которую нашли глазами на боевом.
 *
 * ─── Почему порог, а не «раскрывать всё» ───────────────────────────────────
 * У девяти из пятнадцати вопросов вариантов два-три: прятать их за кликом
 * значит заставить оператора открывать девять плашек, чтобы узнать то, что
 * помещается в строку. У вопросов 7 и 8 вариантов пятнадцать и девятнадцать,
 * а у матриц — сорок три и одиннадцать строк: показанные сразу, они вытеснят
 * с экрана саму анкету.
 */

const ROOT = join(import.meta.dirname, "..");
const BUILDER = readFileSync(join(ROOT, "components", "agora", "SurveyBuilder.tsx"), "utf8");

const q = (number: number) => {
  const found = MANDATORY_QUESTIONS.find((x) => x.number === number);
  assert.ok(found, `в обязательной анкете нет вопроса ${number}`);
  return found;
};

test("длинные списки и матрицы раскрываются, короткие видны сразу", () => {
  assert.equal(optionsPresentation(q(7)), "collapsed", "15 эмоций — свернуть");
  assert.equal(optionsPresentation(q(8)), "collapsed", "19 ценностей — свернуть");
  assert.equal(optionsPresentation(q(9)), "collapsed", "матрица на 43 строки — свернуть");
  assert.equal(optionsPresentation(q(11)), "collapsed", "матрица на 11 строк — свернуть");

  assert.equal(optionsPresentation(q(10)), "inline", "три варианта помещаются в строку");
  assert.equal(optionsPresentation(q(12)), "inline", "шесть вариантов помещаются в строку");
  assert.equal(optionsPresentation(q(13)), "inline");
  assert.equal(optionsPresentation(q(14)), "inline");

  assert.equal(optionsPresentation(q(1)), "none", "у шкалы вариантов нет");
  assert.equal(optionsPresentation(q(15)), "none");
});

test("порог применяется по числу вариантов, а не по номеру вопроса", () => {
  const short = { ...q(12), options: q(12).options?.slice(0, INLINE_OPTIONS_MAX) };
  const long = {
    ...q(12),
    options: [...(q(7).options ?? [])].slice(0, INLINE_OPTIONS_MAX + 1),
  };

  assert.equal(optionsPresentation(short), "inline");
  assert.equal(optionsPresentation(long), "collapsed");
});

test("служебный вариант виден обоими способами, какими он бывает размечен", () => {
  // Вопросы 7 и 8 помечают служебные через exclusiveOptionIds…
  assert.equal(isServiceOption(q(7), "e-s1"), true);
  assert.equal(isServiceOption(q(7), "e-1"), false);

  // …а вопрос 10 — флагом на самом варианте. Читатель обязан знать оба:
  // иначе «Затрудняюсь ответить» покажется обычным вариантом, и оператор
  // решит, что персона может выбрать его вместе с содержательным.
  assert.equal(isServiceOption(q(10), "i-s1"), true);
  assert.equal(isServiceOption(q(10), "i-1"), false);
});

test("строки матрицы сгруппированы по темам в порядке анкеты", () => {
  const groups = themeGroups(q(9));

  assert.equal(groups.length, 10, "десять тем вопроса 9");
  assert.deepEqual(
    groups.map((g) => g.id),
    (q(9).themes ?? []).map((t) => t.id),
    "порядок тем разошёлся с анкетой",
  );
  assert.equal(
    groups.reduce((n, g) => n + g.rows.length, 0),
    q(9).rows?.length,
    "при группировке потерялись строки",
  );
  assert.ok(groups[0].rows.every((r) => r.themeId === groups[0].id));
});

test("строки без объявленных тем не теряются", () => {
  // У вопроса 11 строки несут themeId, но своего списка тем у вопроса нет.
  // Наивная группировка «по списку тем» выбросила бы все одиннадцать строк.
  const groups = themeGroups(q(11));

  assert.equal(
    groups.reduce((n, g) => n + g.rows.length, 0),
    q(11).rows?.length,
    "строки зависимого вопроса потерялись при группировке",
  );
});

test("ключи базовых критериев не показываются оператору", () => {
  assert.ok(
    !/font-mono/.test(BUILDER),
    "в конструкторе остался моноширинный текст — это идентификаторы " +
      "(baseKey), они внутренние и оператору не нужны",
  );
  assert.ok(
    !/\{q\.baseKey\}/.test(BUILDER),
    "конструктор всё ещё печатает baseKey на экране",
  );
});
