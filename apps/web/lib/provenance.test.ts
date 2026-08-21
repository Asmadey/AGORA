import assert from "node:assert/strict";
import { test } from "node:test";

import type { AnswerView } from "./report-view.ts";
import { METRICS, contributions, metricLabel } from "./provenance.ts";

/**
 * Происхождение числа (конструктор связей, вариант 1 — выбор владельца 20.08.2026).
 *
 * Требование к этому модулю одно и оно жёсткое: список, который он отдаёт,
 * обязан ВОСПРОИЗВОДИТЬ показанное число. Раскрытие, где сумма не сходится с
 * шапкой, хуже отсутствия раскрытия: оно превращает проверяемое число в
 * спорное.
 */

function answer(over: Partial<AnswerView> & { personaId: string }): AnswerView {
  return {
    personaName: "Персона",
    initials: "П",
    avatarHue: 0,
    replication: 0,
    segmentLabel: null,
    scores: {
      overall_impression: null,
      plot: null,
      acting: null,
      music: null,
      cinematography: null,
    },
    overall: null,
    retentionIntent: null,
    watchedShare: null,
    nps: null,
    emotions: [],
    verbatim: null,
    groundingRefs: [],
    qaFlags: [],
    surveyAnswers: {},
    verbatims: {},
    ...over,
  } as AnswerView;
}

test("среднее по критерию считается по тем же ответам, что и в шапке", () => {
  const answers = [
    answer({ personaId: "a", scores: { overall_impression: 8, plot: null, acting: null, music: null, cinematography: null } }),
    answer({ personaId: "b", scores: { overall_impression: 6, plot: null, acting: null, music: null, cinematography: null } }),
  ];
  const out = contributions("overall_impression", answers);
  assert.equal(out.computed, 7);
  assert.equal(out.rows.length, 2);
  assert.equal(out.rows[0].value, 8, "строки идут от большего к меньшему");
});

test("забракованные QA в число не входят — как и в агрегате воркера", () => {
  const answers = [
    answer({ personaId: "a", scores: { overall_impression: 10, plot: null, acting: null, music: null, cinematography: null } }),
    answer({
      personaId: "b",
      qaFlags: ["grounding"],
      scores: { overall_impression: 2, plot: null, acting: null, music: null, cinematography: null },
    }),
  ];
  const out = contributions("overall_impression", answers);
  assert.equal(out.computed, 10);
  assert.equal(out.rows.length, 1);
  assert.equal(out.excluded, 1);
});

test("NPS: промоутеры 9–10, критики 1–6, середина не считается ни за кого", () => {
  const answers = [
    answer({ personaId: "a", nps: 10 }),
    answer({ personaId: "b", nps: 8 }),
    answer({ personaId: "c", nps: 5 }),
    answer({ personaId: "d", nps: 6 }),
  ];
  const out = contributions("nps", answers);
  // (1 промоутер − 2 критика) / 4 × 100 = −25
  assert.equal(out.computed, -25);
  assert.deepEqual(
    out.rows.map((r) => r.group),
    ["промоутер", "нейтрал", "критик", "критик"],
  );
});

test("досмотр: затруднившиеся выпадают из знаменателя", () => {
  const answers = [
    answer({ personaId: "a", retentionIntent: "Скорее хотелось досмотреть до конца" }),
    answer({ personaId: "b", retentionIntent: "Скорее хотелось остановить просмотр" }),
    answer({ personaId: "c", retentionIntent: "Затрудняюсь ответить" }),
  ];
  const out = contributions("retention", answers);
  assert.equal(out.computed, 50, "1 из 2 известных, а не 1 из 3");
  assert.equal(out.rows.length, 2);
});

test("доля просмотра: значение вне шкалы 0–100 не втягивается в среднее", () => {
  const answers = [
    answer({ personaId: "a", watchedShare: 80 }),
    answer({ personaId: "b", watchedShare: 60 }),
    answer({ personaId: "c", watchedShare: 1000 }),
  ];
  assert.equal(contributions("watched_share", answers).computed, 70);
});

test("ответ без значения метрики в список не попадает", () => {
  const answers = [answer({ personaId: "a", nps: null }), answer({ personaId: "b", nps: 9 })];
  const out = contributions("nps", answers);
  assert.equal(out.rows.length, 1);
  assert.equal(out.silent, 1);
});

test("пустая выборка не даёт нуля — она даёт «нечего показывать»", () => {
  const out = contributions("nps", []);
  assert.equal(out.computed, null);
  assert.deepEqual(out.rows, []);
});

test("таймкоды персоны едут вместе со строкой — за ними и идут", () => {
  const answers = [
    answer({
      personaId: "a",
      nps: 9,
      groundingRefs: [{ timecode: "20:58", note: "сцена в госпитале" }],
      verbatim: "Атмосфера давит",
    }),
  ];
  const [row] = contributions("nps", answers).rows;
  assert.equal(row.refs.length, 1);
  assert.equal(row.verbatim, "Атмосфера давит");
});

test("у каждой метрики есть подпись — иначе раскрытие безымянное", () => {
  for (const key of METRICS) {
    assert.ok(metricLabel(key).length > 0, key);
  }
});

test("формула названа словами, а не только числом", () => {
  assert.match(contributions("nps", [answer({ personaId: "a", nps: 9 })]).formula, /промоутер/i);
});
