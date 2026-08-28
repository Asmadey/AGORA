import assert from "node:assert/strict";
import { test } from "node:test";

import type { SurveyQuestion } from "./agora-types.ts";
import {
  DRAFT_SURVEY_ID,
  draftSurveyName,
  missingBaseKeys,
  questionsDiffer,
  questionsOf,
} from "./survey-sync.ts";

const q = (over: Partial<SurveyQuestion> = {}): SurveyQuestion => ({
  id: "q1",
  label: "Общее впечатление",
  type: "scale",
  scaleMin: 1,
  scaleMax: 10,
  ...over,
});

const BASE: SurveyQuestion[] = [
  q({ id: "b1", label: "Общее впечатление", baseKey: "overall_impression" }),
  q({ id: "b2", label: "Сюжет", baseKey: "plot" }),
];

test("вопросы выбранной анкеты", async (t) => {
  const surveys = [
    { id: "s1", name: "Короткая", questions: [q({ id: "x", label: "Свой вопрос" })] },
  ];

  await t.test("выбрана существующая — берутся её вопросы", () => {
    assert.deepEqual(
      questionsOf(surveys, "s1", BASE).map((x) => x.label),
      ["Свой вопрос"],
    );
  });

  await t.test("черновик — берётся запасной набор", () => {
    assert.deepEqual(
      questionsOf(surveys, DRAFT_SURVEY_ID, BASE).map((x) => x.label),
      ["Общее впечатление", "Сюжет"],
    );
  });

  await t.test("ничего не выбрано — запасной набор", () => {
    assert.equal(questionsOf(surveys, null, BASE).length, 2);
  });

  await t.test("выбрана исчезнувшая анкета — запасной набор, а не пустота", () => {
    // Анкету могли удалить в другой вкладке. Пустой шаг «Опрос» выглядел бы
    // как поломка визарда, а не как отсутствие анкеты.
    assert.equal(questionsOf(surveys, "нет-такой", BASE).length, 2);
  });

  await t.test("возвращается копия — правка не портит исходник", () => {
    const got = questionsOf(surveys, "s1", BASE);
    got[0].label = "Изменено";
    assert.equal(
      surveys[0].questions[0].label,
      "Свой вопрос",
      "правка на экране изменила вопрос в списке анкет — отменять станет нечем",
    );
  });
});

test("несохранённые правки", async (t) => {
  await t.test("одинаковые наборы — правок нет", () => {
    assert.equal(questionsDiffer(BASE, BASE.map((x) => ({ ...x }))), false);
  });

  await t.test("разные id при том же содержании — правок нет", () => {
    // Конструктор выдаёт новым вопросам q-<время>. Сравнение по id давало бы
    // вечное «есть несохранённые правки» сразу после открытия анкеты.
    const renamed = BASE.map((x, i) => ({ ...x, id: `q-${i}-${Date.now()}` }));
    assert.equal(questionsDiffer(BASE, renamed), false);
  });

  await t.test("изменённая формулировка — правка есть", () => {
    const edited = BASE.map((x) => ({ ...x }));
    edited[1].label = "Сюжет и темп";
    assert.equal(questionsDiffer(BASE, edited), true);
  });

  await t.test("изменённый тип — правка есть", () => {
    const edited = BASE.map((x) => ({ ...x }));
    edited[0].type = "open";
    assert.equal(questionsDiffer(BASE, edited), true);
  });

  await t.test("изменённая шкала — правка есть", () => {
    const edited = BASE.map((x) => ({ ...x }));
    edited[0].scaleMax = 5;
    assert.equal(questionsDiffer(BASE, edited), true);
  });

  await t.test("добавленный и удалённый вопрос — правка есть", () => {
    assert.equal(questionsDiffer(BASE, [...BASE, q({ id: "n" })]), true);
    assert.equal(questionsDiffer(BASE, BASE.slice(0, 1)), true);
  });

  await t.test("лишние пробелы правкой не считаются", () => {
    const padded = BASE.map((x) => ({ ...x, label: `  ${x.label}  ` }));
    assert.equal(questionsDiffer(BASE, padded), false);
  });
});

test("название анкеты, создаваемой из визарда", async (t) => {
  await t.test("берётся от названия исследования", () => {
    assert.equal(draftSurveyName("Константинополь, 1 серия"), "Анкета: Константинополь, 1 серия");
  });

  await t.test("пустое название — запасное имя", () => {
    assert.equal(draftSurveyName(null), "Анкета исследования");
    assert.equal(draftSurveyName("   "), "Анкета исследования");
  });

  await t.test("длинное название обрезается под колонку", () => {
    // Колонка принимает 200 символов. Отказ по длине пришёл бы после нажатия
    // «Запустить», то есть после загрузки ролика.
    const name = draftSurveyName("я".repeat(500));
    assert.ok(name.length <= 200, `имя длиной ${name.length} не влезет в колонку`);
  });
});

test("недостающие базовые критерии называются, но не запрещают", () => {
  const onlyCustom = [q({ id: "c1", label: "Свой", baseKey: undefined })];
  assert.deepEqual(missingBaseKeys(onlyCustom, BASE), ["Общее впечатление", "Сюжет"]);
  assert.deepEqual(missingBaseKeys(BASE, BASE), []);
});
