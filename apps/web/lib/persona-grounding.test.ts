import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { GROUNDING_PROP_TOL, groundingReport } from "./persona-grounding.ts";

/**
 * Заземление набора персон, показанное человеку.
 *
 * Метрика `persona_grounding` считалась только в `evals/check.py` — то есть в
 * отчёте гейта, куда владелец продукта не заходит. Вопрос «похожа ли собранная
 * аудитория на датасет» при этом задают, глядя на набор, и отвечать на него
 * приходилось на слово.
 */

const RECORDS = [
  ...Array.from({ length: 5 }, () => ({ socio_demographics: { age_group: "25-34", geo: "Москва", gender: "муж" } })),
  ...Array.from({ length: 5 }, () => ({ socio_demographics: { age_group: "35-44", geo: "Москва", gender: "жен" } })),
];

function persona(age: string, gender: string) {
  return { dna: { demographics: { age_group: age, geo: "Москва", gender } } };
}

test("совпадающие доли расхождений не дают", () => {
  const report = groundingReport(
    [persona("25-34", "муж"), persona("35-44", "жен")],
    RECORDS,
  );

  assert.ok(report.comparable);
  assert.deepEqual(report.deviations, [], "у совпадающих долей не должно быть отклонений");
});

test("перекос выше порога назван поимённо", () => {
  // Все персоны из одной возрастной группы против половины в датасете:
  // расхождение 0.5 при пороге 0.1.
  const report = groundingReport(
    Array.from({ length: 4 }, () => persona("25-34", "муж")),
    RECORDS,
  );

  const ages = report.deviations.filter((d) => d.bucket === "25-34");
  assert.equal(ages.length, 1, "перекос по возрасту обязан быть назван");
  assert.ok(ages[0].delta > GROUNDING_PROP_TOL);
});

test("сравнивать не с чем — так и сказано, а не «всё хорошо»", () => {
  // Пустой слепок раньше дал бы нулевые доли с обеих сторон и зелёный вердикт:
  // «заземлено» там, где не проверено. Это худший вид зелёного.
  const empty = groundingReport([persona("25-34", "муж")], []);

  assert.equal(empty.comparable, false);
  assert.deepEqual(empty.deviations, []);
});

test("порог совпадает с evals/check.py", () => {
  // Два числа в двух языках разъезжаются молча: гейт покажет «заземлено», а
  // экран — «перекос», и спорить будет не с чем.
  const src = readFileSync(new URL("../../../evals/check.py", import.meta.url), "utf-8");
  const match = /GROUNDING_PROP_TOL\s*=\s*([\d.]+)/.exec(src);

  assert.ok(match, "в evals/check.py не найден GROUNDING_PROP_TOL");
  assert.equal(Number(match[1]), GROUNDING_PROP_TOL);
});
