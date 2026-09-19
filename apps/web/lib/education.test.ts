import assert from "node:assert/strict";
import { test } from "node:test";

import {
  EDUCATION_OPTIONS,
  EDUCATION_TOOLTIP,
  educationAgePreview,
} from "./education.ts";
import { parseAudienceChoice } from "./audience.ts";

test("критерий образования имеет два бинарных варианта", () => {
  assert.deepEqual(EDUCATION_OPTIONS, ["есть высшее", "нет высшего"]);
});

test("подсказка содержит доли, источник и обе оговорки", () => {
  const text = Object.values(EDUCATION_TOOLTIP).join(" ");
  assert.match(text, /18-24 .*5 %/);
  assert.match(text, /Микроперепись населения России 2015 г\. \(Росстат\/ВШЭ\), агрегация автором по бинам графика/);
  assert.match(text, /По корпусу AGORA образование не спрашивали/);
  assert.match(text, /цифра 18-24 оценочная/);
  assert.match(text, /100 %/);
  assert.match(text, /возрастной состав аудитории изменится/);
});

test("выбор высшего показывает нулевой подростковый вес", () => {
  const preview = educationAgePreview(
    ["14-17", "18-24", "25-34", "35-44", "45-59", "60+"],
    ["есть высшее"],
  );
  assert.match(preview ?? "", /14-17 → 0 %/);
  assert.match(preview ?? "", /18-24 →/);
});

test("невозможное пересечение видно до генерации", () => {
  assert.match(educationAgePreview(["14-17"], ["есть высшее"]) ?? "", /пусто/);
});

test("API-контракт отклоняет подростков только с высшим", () => {
  const result = parseAudienceChoice({
    size: 100,
    ageGroups: ["14-17"],
    geos: ["столицы"],
    genders: ["муж", "жен"],
    education: ["есть высшее"],
  });
  assert.equal(result.ok, false);
  assert.match(result.ok ? "" : result.errors.join("; "), /образование/);
});

test("оба варианта образования включены по умолчанию в API-контракте", () => {
  const result = parseAudienceChoice({
    size: 100,
    ageGroups: ["25-34"],
    geos: ["столицы"],
    genders: ["муж", "жен"],
  });
  assert.equal(result.ok, true);
  if (result.ok && result.value.kind === "generate") {
    assert.deepEqual(result.value.criteria.education, EDUCATION_OPTIONS);
  }
});
