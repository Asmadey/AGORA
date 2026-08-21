import assert from "node:assert/strict";
import { test } from "node:test";

import { rerunPrefill, type SourceRun } from "./rerun.ts";

/**
 * Перезапуск исследования с теми же персонами (#30).
 *
 * ─── Что было ───────────────────────────────────────────────────────────────
 * Кнопка «Перезапустить» вела на `/studies/new?rerun=<id>`, а параметр `rerun`
 * не разбирался НИГДЕ: визард открывался пустым. Человек, нажавший её, заново
 * загружал тот же файл и заново набирал аудиторию — то есть получал не
 * перезапуск, а новое исследование, и сравнить их было не с чем.
 *
 * ─── Что должен дать перезапуск ─────────────────────────────────────────────
 * Тот же материал и та же аудитория, новые вопросы. Именно в этом его смысл:
 * разница в ответах тогда объясняется вопросами, а не другим набором персон и
 * не другой расшифровкой.
 */

const SOURCE: SourceRun = {
  id: "533887d6-73b7-4323-a2f2-5e441d48b196",
  mode: "long",
  videoRef: "tenants/x/uploads/film.mp4",
  sourceName: "Константинополь _ 1 серия.mp4",
  personaSetId: "765c1dc9-fc08-4ea3-a26a-c05780fe0cd6",
  projectId: "11111111-1111-1111-1111-111111111111",
  replicationCount: 3,
  whisperModel: "gigaam-v3-e2e-rnnt",
  title: "Пилот",
};

test("материал и аудитория переносятся, файл заново не грузится", () => {
  const p = rerunPrefill(SOURCE);
  assert.equal(p.videoRef, SOURCE.videoRef);
  assert.equal(p.sourceName, SOURCE.sourceName);
  assert.equal(p.personaSetId, SOURCE.personaSetId);
  assert.equal(p.mode, "long");
});

test("настройки прогона переносятся тоже", () => {
  const p = rerunPrefill(SOURCE);
  assert.equal(p.replicationCount, 3);
  assert.equal(p.whisperModel, "gigaam-v3-e2e-rnnt");
  assert.equal(p.projectId, SOURCE.projectId);
});

test("анкета НЕ переносится — ради неё перезапуск и делают", () => {
  const p = rerunPrefill(SOURCE);
  assert.deepEqual(p.surveyQuestions, []);
});

test("название подсказывает, что это повтор, но остаётся правимым", () => {
  const p = rerunPrefill(SOURCE);
  assert.match(p.title, /Пилот/);
  assert.match(p.title, /повтор/i);
});

test("прогон без набора персон перезапуску не подлежит", () => {
  // Аудитория собиралась на лету и нигде не сохранена: «те же персоны» взять
  // неоткуда, и молча собрать новых значило бы подменить смысл кнопки.
  const p = rerunPrefill({ ...SOURCE, personaSetId: null });
  assert.equal(p.personaSetId, null);
  assert.match(p.warning ?? "", /персон/i);
});

test("прогон без материала перезапуску не подлежит", () => {
  const p = rerunPrefill({ ...SOURCE, videoRef: null });
  assert.equal(p.videoRef, null);
  assert.match(p.warning ?? "", /материал/i);
});

test("исправный прогон предупреждений не порождает", () => {
  assert.equal(rerunPrefill(SOURCE).warning, null);
});

test("пустое название исходника не даёт названия из одного слова «повтор»", () => {
  const p = rerunPrefill({ ...SOURCE, title: null, sourceName: "ролик.mp4" });
  assert.match(p.title, /ролик\.mp4/);
});
