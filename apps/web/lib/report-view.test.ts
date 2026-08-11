import { test } from "node:test";
import assert from "node:assert/strict";

import { avatarHue, initials, parseAnswer, parseReport, segmentLabel } from "./report-view.ts";

/**
 * Тесты разбора отчёта.
 *
 * Раннер — встроенный `node:test`, TypeScript Node исполняет сам. Ни одной новой
 * зависимости: в `apps/web` запрещены нативные модули (§6 CLAUDE.md), а тянуть
 * ради одного файла vitest с его цепочкой пакетов — плата, несоразмерная задаче.
 *
 * Проверяется здесь ровно одно свойство, но по всем полям: **отсутствие данных
 * не превращается в число**. Это не педантизм. Отчёт читают, чтобы принять
 * решение, и «NPS 0» вместо прочерка означает «аудитория разделилась поровну»,
 * тогда как на самом деле NPS не считался. Различить это по экрану нельзя, а
 * разбор — единственное место, где решается, что увидит пользователь.
 *
 * Запуск: `npm run test -w apps/web`.
 */

test("пустой отчёт не превращается в нули", () => {
  const view = parseReport({});

  assert.equal(view.nps, null);
  assert.equal(view.retentionRate, null);
  assert.equal(view.watchedShare, null);
  assert.equal(view.emotionalIndex, null);
  assert.equal(view.scores.overall_impression, null);
  assert.equal(view.disclaimer, null);
});

test("счётчики выборки — нули, и это правда", () => {
  // Отличие от метрик: «ответов ноль» — измеримый факт, а не отсутствие
  // измерения. Прочерк здесь врал бы в другую сторону.
  const view = parseReport({});
  assert.equal(view.sampleSize, 0);
  assert.equal(view.excludedByQa, 0);
  assert.equal(view.replicationCount, 1);
});

test("настоящий ноль отличается от отсутствия", () => {
  const view = parseReport({ aggregate: { nps: 0, watched_share_mean: 0 } });
  assert.equal(view.nps, 0);
  assert.equal(view.watchedShare, 0);
});

test("NaN и Infinity — не числа", () => {
  // JSON их не переносит, но отчёт приходит из Mongo через драйвер, а не через
  // JSON.parse. Число, которое не число, дало бы на экране «NaN».
  const view = parseReport({ aggregate: { nps: Number.NaN, emotional_index: Infinity } });
  assert.equal(view.nps, null);
  assert.equal(view.emotionalIndex, null);
});

test("разрез не считали — это не пустой разрез", () => {
  assert.equal(parseReport({ aggregate: {} }).hasSegments, false);
  assert.equal(parseReport({ aggregate: { segment_breakdown: {} } }).hasSegments, true);
});

test("сегменты разбираются по измерениям, скрытые сохраняются", () => {
  const view = parseReport({
    aggregate: {
      segment_breakdown: {
        age_group: {
          "18-24": { core_scores_mean: { overall_impression: 8.1 }, nps: 40, personas: 7 },
        },
        suppressed: [{ dimension: "geo", value: "иные НП", personas: 3 }],
        min_personas: 5,
      },
    },
  });

  const age = view.segments.find((s) => s.key === "age_group");
  assert.equal(age?.rows[0].overall, 8.1);
  assert.equal(age?.rows[0].personas, 7);
  assert.deepEqual(view.suppressedSegments, [
    { dimension: "geo", value: "иные НП", personas: 3 },
  ]);
  assert.equal(view.minSegmentPersonas, 5);
});

test("разброс берётся только полным", () => {
  // Полоса на шкале рисуется по четырём числам. Три из четырёх дали бы полосу,
  // построенную на подставленном значении, — а выглядит она как измеренная.
  const view = parseReport({
    aggregate: {
      replication_bounds: {
        overall_impression: { mean: 7, min: 5.5, max: 8.5, stdev: 1.2 },
        plot: { mean: 7, min: 5.5 },
      },
    },
  });
  assert.deepEqual(view.spread.overall_impression, { mean: 7, min: 5.5, max: 8.5, stdev: 1.2 });
  assert.equal(view.spread.plot, undefined);
});

test("тема без заголовка отбрасывается, а не рисуется пустой", () => {
  const view = parseReport({
    themes: [{ title: "Финал", agreement: "раскол" }, { summary: "без заголовка" }],
  });
  assert.equal(view.themes.length, 1);
  assert.equal(view.themes[0].title, "Финал");
  assert.equal(view.themes[0].summary, "");
});

test("мусор вместо структуры не роняет разбор", () => {
  // Отчёт приходит из базы, а не из типизированного вызова: строка вместо
  // объекта возможна после ручной правки документа или частичной записи.
  const view = parseReport({ aggregate: "сломано", themes: "не массив", narrative: 42 });
  assert.equal(view.sampleSize, 0);
  assert.deepEqual(view.themes, []);
  assert.deepEqual(view.narrative, []);
});

test("таймкод отделяется от подписи", () => {
  const answer = parseAnswer({
    personaId: "p1",
    personaName: "Галина Петрова",
    replication: 0,
    segment: { age_group: "60+", geo: "столицы", gender: "жен" },
    answer: {
      scores: { overall_impression: 7 },
      perception: { retention_intent: "скорее выключить", watched_share_pct: 40 },
      verbatims: { why_impression: "не смогла смотреть" },
      grounding_refs: ["34:20 сцена на кухне", "мусор без таймкода"],
    },
    qaFlags: [],
  });

  assert.deepEqual(answer.groundingRefs, [{ timecode: "34:20", note: "сцена на кухне" }]);
  assert.equal(answer.watchedShare, 40);
  assert.equal(answer.segmentLabel, "60+ · столицы · жен");
});

test("карточка без имени показывает идентификатор, а не пустоту", () => {
  const answer = parseAnswer({
    personaId: "p7",
    personaName: null,
    replication: 0,
    segment: {},
    answer: {},
    qaFlags: [],
  });
  assert.equal(answer.personaName, "p7");
  assert.equal(answer.segmentLabel, null);
  assert.equal(answer.overall, null);
  assert.equal(answer.verbatim, null);
});

test("обоснование берётся любое непустое, если основного нет", () => {
  const answer = parseAnswer({
    personaId: "p1",
    personaName: "Тест",
    replication: 0,
    segment: {},
    answer: { verbatims: { why_impression: "   ", memorable_elements: "посуда" } },
    qaFlags: [],
  });
  assert.equal(answer.verbatim, "посуда");
});

test("оттенок аватара устойчив и в пределах круга", () => {
  // Одна персона обязана выглядеть одинаково на всех экранах, иначе аватар
  // перестаёт помогать её узнавать.
  assert.equal(avatarHue("persona-42"), avatarHue("persona-42"));
  for (const id of ["a", "persona-42", "", "длинный-идентификатор-персоны"]) {
    const h = avatarHue(id);
    assert.ok(h >= 0 && h < 360, `${id} → ${h}`);
  }
});

test("инициалы не бывают пустыми", () => {
  assert.equal(initials("Галина Петрова"), "ГП");
  assert.equal(initials("Галина"), "Г");
  assert.equal(initials("   "), "?");
});

test("подпись сегмента идёт в фиксированном порядке", () => {
  // Порядок ключей объекта не гарантирован источником, а подпись читают глазами:
  // «жен · 60+ · столицы» и «60+ · столицы · жен» выглядят как разные срезы.
  assert.equal(
    segmentLabel({ gender: "жен", geo: "столицы", age_group: "60+" }),
    "60+ · столицы · жен",
  );
});
