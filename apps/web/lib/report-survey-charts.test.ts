import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { parseReport, type SurveyQuestionView, type SurveyStats, type SurveyView } from "./report-view.ts";
import { surveyQuestion } from "./report-survey.ts";
import { buildSurveyQuestionChart } from "./report-survey-charts.ts";

const WEB = new URL("..", import.meta.url).pathname;
const FIXTURE = JSON.parse(
  readFileSync(join(WEB, "lib/fixtures/survey-tally.json"), "utf8"),
) as { counted: Record<string, unknown>; below_threshold: Record<string, unknown> };
const SURVEY = JSON.parse(
  readFileSync(join(WEB, "../../data/survey/customer_2026.json"), "utf8"),
) as {
  questions: {
    id: string;
    number: number;
    label: string;
    type: string;
    block: string;
    options?: { id: string; label: string }[];
  }[];
};

function view(tally: Record<string, unknown>): SurveyView {
  const parsed = parseReport({ aggregate: { survey: tally } }).survey;
  assert.ok(parsed, "поле survey разобрано");
  return parsed;
}

function question(viewValue: SurveyView, number: number): SurveyQuestionView {
  const result = surveyQuestion(viewValue, number);
  assert.ok(result, `вопрос ${number} есть в фикстуре`);
  return result;
}

function stats(overrides: Partial<SurveyStats>): SurveyStats {
  return {
    n: 0,
    base: null,
    belowThreshold: false,
    mean: null,
    topBox: null,
    groups: null,
    options: null,
    errors: null,
    texts: null,
    rows: null,
    ...overrides,
  };
}

function emotionsQuestion(): SurveyQuestionView {
  const definition = SURVEY.questions.find((candidate) => candidate.number === 7);
  assert.ok(definition?.options, "в анкете есть варианты вопроса 7");
  return {
    id: definition.id,
    number: definition.number,
    type: definition.type,
    block: definition.block,
    label: definition.label,
    total: stats({
      n: 3,
      base: 3,
      options: definition.options.map((option, index) => ({
        id: option.id,
        share: index === 0 ? 0.3333 : 0,
        count: index === 0 ? 1 : 0,
      })),
    }),
    target: stats({ n: 2, base: 2, belowThreshold: true }),
  };
}

test("выбор диаграммы и ряды закрытых вопросов собираются в lib", () => {
  const counted = view(FIXTURE.counted);

  const emotions = buildSurveyQuestionChart(emotionsQuestion());
  assert.equal(emotions.kind, "bar");
  if (emotions.kind !== "bar") return;
  assert.equal(emotions.rows.length, 15, "все эмоции, включая два служебных варианта");
  assert.equal(emotions.rows.filter((row) => row.service).length, 2);
  assert.equal(emotions.rows[0]?.count, 1, "у столбика остаётся счёт ответов");
  assert.ok(emotions.target.rows.every((row) => row.share === null), "подавленный срез не стал нулём");

  const values = buildSurveyQuestionChart(question(counted, 8));
  assert.equal(values.kind, "bar");
  if (values.kind !== "bar") return;
  assert.equal(values.rows.length, 19, "все ценности, включая два служебных варианта");
  assert.equal(values.rows.find((row) => row.id === "v-s2")?.service, true);
  assert.equal(values.rows.find((row) => row.id === "v-2")?.share, 0, "измеренный ноль не пропал");
  assert.equal(values.target.rows.find((row) => row.id === "v-8")?.share, 1);

  const matrix = buildSurveyQuestionChart(question(counted, 9));
  assert.equal(matrix.kind, "matrix");
  if (matrix.kind !== "matrix") return;
  assert.equal(matrix.groups.length, 1, "строки сгруппированы по теме");
  assert.equal(matrix.groups[0]?.rows.length, 2);
  assert.deepEqual(matrix.groups[0]?.rows[0]?.parts.map((part) => part.id), ["m-1", "m-2", "m-3"]);
  assert.equal(matrix.groups[0]?.rows[0]?.target.share, 1);

  const single = buildSurveyQuestionChart(question(counted, 10));
  assert.equal(single.kind, "stacked");
  if (single.kind !== "stacked") return;
  assert.equal(single.parts.length, 3);
  assert.equal(single.parts.find((part) => part.id === "i-s1")?.service, true);
  assert.equal(single.parts.reduce((sum, part) => sum + (part.share ?? 0), 0), 1);

  const scale = buildSurveyQuestionChart(question(counted, 1));
  assert.equal(scale.kind, "scale");
  if (scale.kind !== "scale") return;
  assert.equal(scale.mean, 6.33);
  assert.equal(scale.topBox, 0.3333);
  assert.deepEqual(scale.groups.map((group) => group.id), ["9-10", "7-8", "0-6"]);
  assert.equal(scale.target.mean, 8);
});

test("шкала рекомендации сохраняет NPS, среднее и долю верхних баллов", () => {
  const chart = buildSurveyQuestionChart(question(view(FIXTURE.counted), 15));
  assert.equal(chart.kind, "nps");
  if (chart.kind !== "nps") return;
  assert.equal(chart.mean, 6.67);
  assert.equal(chart.values.promoters, 1 / 3);
  assert.equal(chart.values.neutral, 1 / 3);
  assert.equal(chart.values.detractors, 1 / 3);
  assert.equal(chart.topBox, 0.3333);

  const suppressed = buildSurveyQuestionChart(question(view(FIXTURE.below_threshold), 15));
  assert.equal(suppressed.kind, "nps");
  if (suppressed.kind !== "nps") return;
  assert.equal(suppressed.target.mean, null);
  assert.equal(suppressed.target.values.promoters, null);
  assert.equal(suppressed.target.n, 2, "размер среза остаётся рядом с null");
});

test("открытый вопрос возвращается текстовым блоком без диаграммы", () => {
  const chart = buildSurveyQuestionChart(question(view(FIXTURE.counted), 16));
  assert.equal(chart.kind, "open");
  if (chart.kind !== "open") return;
  assert.deepEqual(chart.texts, ["финал", "музыка"]);
  assert.equal(chart.sample.answered, 2);
});
