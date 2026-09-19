import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { validateSurvey } from "./server/survey-validator.ts";

const REPO = new URL("../../../", import.meta.url).pathname;
const CUSTOMER_SURVEY = JSON.parse(
  readFileSync(join(REPO, "data/survey/customer_2026.json"), "utf8"),
) as {
  questions: Array<{
    number: number;
    type: string;
    options?: Array<{ id: string }>;
    reporting?: {
      chart: string;
      groups?: Record<string, string[]>;
    };
    keyOptionIds?: string[];
  }>;
};

const EXPECTED_CHARTS: Record<number, string> = {
  1: "scale",
  2: "scale",
  3: "scale",
  4: "scale",
  5: "scale",
  6: "scale_top_box",
  7: "bars",
  8: "bars",
  9: "matrix_stacked",
  10: "donut",
  11: "matrix_stacked",
  12: "donut",
  13: "donut",
  14: "donut",
  15: "nps",
};

const EXPECTED_GROUPS: Record<number, Record<string, string[]>> = {
  7: {
    positive: ["e-1", "e-2", "e-3", "e-4", "e-5", "e-6", "e-7"],
    negative: ["e-8", "e-9", "e-10", "e-11", "e-12", "e-13"],
    unknown: ["e-s1", "e-s2"],
  },
  9: { positive: ["m-1"], negative: ["m-2"], unknown: ["m-3"] },
  10: { positive: ["i-1"], negative: ["i-2"], unknown: ["i-s1"] },
  11: { positive: ["y-1"], negative: ["y-2"] },
  12: {
    positive: ["j-1", "j-2"],
    negative: ["j-4", "j-5"],
    neutral: ["j-3"],
    unknown: ["j-s1"],
  },
  13: { positive: ["w-1"], negative: ["w-2"], unknown: ["w-s1"] },
  14: { positive: ["p-1"], negative: ["p-2"], unknown: ["p-s1"] },
};

test("анкета заказчика хранит тип диаграммы для каждого вопроса", () => {
  for (const question of CUSTOMER_SURVEY.questions) {
    assert.equal(
      question.reporting?.chart,
      EXPECTED_CHARTS[question.number],
      `у вопроса ${question.number} нет ожидаемого reporting.chart`,
    );
  }
});

test("классификация покрывает каждый вариант ровно одной группой", () => {
  // Вопрос 8 намеренно не входит сюда: для ценностей референс задает
  // отдельный keyOptionIds, а не смысловые positive/negative группы.
  for (const [number, expectedGroups] of Object.entries(EXPECTED_GROUPS)) {
    const question = CUSTOMER_SURVEY.questions.find((item) => item.number === Number(number));
    assert.ok(question, `вопрос ${number} отсутствует`);
    const groups = question.reporting?.groups;
    assert.ok(groups && Object.keys(groups).length > 0, `у вопроса ${number} groups пуст`);
    assert.deepEqual(groups, expectedGroups, `группы вопроса ${number} не совпадают с референсом`);

    const optionIds = (question.options ?? []).map((option) => option.id);
    const groupedIds = Object.values(groups).flat();
    assert.ok(groupedIds.length > 0, `у вопроса ${number} groups пуст`);
    assert.equal(
      new Set(groupedIds).size,
      groupedIds.length,
      `вариант вопроса ${number} лежит в нескольких группах`,
    );
    assert.deepEqual(
      [...groupedIds].sort(),
      [...optionIds].sort(),
      `groups вопроса ${number} не покрывают ровно его options`,
    );
  }
});

test("вопрос 8 явно хранит отсутствие ключевых ценностей", () => {
  const question = CUSTOMER_SURVEY.questions.find((item) => item.number === 8);
  assert.ok(question, "вопрос 8 отсутствует");
  assert.deepEqual(question.keyOptionIds, []);
});

test("полная анкета заказчика с reporting проходит ручной валидатор", () => {
  const result = validateSurvey({ name: "Анкета заказчика", questions: CUSTOMER_SURVEY.questions });
  assert.equal(result.valid, true, result.errors.join("; "));
});

test("валидатор отклоняет неизвестный вариант в reporting.groups", () => {
  const result = validateSurvey({
    name: "Анкета",
    questions: [
      {
        id: "q1",
        label: "Вопрос",
        type: "single_choice",
        options: [
          { id: "yes", label: "Да" },
          { id: "no", label: "Нет" },
        ],
        reporting: {
          chart: "donut",
          groups: { positive: ["missing"] },
        },
      },
    ],
  });

  assert.equal(result.valid, false);
  assert.match(result.errors.join("; "), /reporting.*missing/);
});

test("валидатор отклоняет вариант в двух reporting.groups", () => {
  const result = validateSurvey({
    name: "Анкета",
    questions: [
      {
        id: "q1",
        label: "Вопрос",
        type: "single_choice",
        options: [
          { id: "yes", label: "Да" },
          { id: "no", label: "Нет" },
        ],
        reporting: {
          chart: "donut",
          groups: {
            positive: ["yes"],
            negative: ["yes", "no"],
          },
        },
      },
    ],
  });

  assert.equal(result.valid, false);
  assert.match(result.errors.join("; "), /двух группах|нескольких группах/);
});

test("старые анкеты без reporting и keyOptionIds продолжают приниматься", () => {
  const result = validateSurvey({
    name: "Старая анкета",
    questions: [
      {
        id: "q1",
        label: "Вопрос",
        type: "scale",
        scaleMin: 0,
        scaleMax: 10,
      },
    ],
  });

  assert.equal(result.valid, true, result.errors.join("; "));
});
