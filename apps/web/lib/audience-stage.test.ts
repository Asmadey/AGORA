import { test } from "node:test";
import assert from "node:assert/strict";

import { AUDIENCE_LABEL, audienceStage, stageScale } from "./audience-stage.ts";

/**
 * «Я выбираю создать 100 персон и сразу перехожу к запуску исследования — и не
 * вижу, что персоны создаются, мне кажется, что интерфейс завис» (18.09.2026).
 *
 * Экран прогресса начинался с «Разбор файла» и стоял на нём, пока единственный
 * воркер дописывал аудиторию. Работа шла, счётчик «40 из 100» был в базе, а на
 * экране не было ничего.
 */

const READY = { name: "Аудитория 0093", status: "ready", size: 20, generatedCount: 20, error: null };
const BUSY = { name: "Сто персон", status: "generating", size: 100, generatedCount: 40, error: null };

test("идущая генерация показана числами, а не долей", () => {
  const stage = audienceStage(BUSY);
  assert.equal(stage?.state, "running");
  assert.equal(stage?.label, AUDIENCE_LABEL);
  assert.match(stage!.detail, /40 из 100/);
});

test("готовый набор — галочка с числом персон", () => {
  const stage = audienceStage(READY);
  assert.equal(stage?.state, "done");
  assert.match(stage!.detail, /20 персон/);
});

test("отказ несёт причину, а не только красный значок", () => {
  const stage = audienceStage({ ...BUSY, status: "failed", error: "слепок корпуса не найден" });
  assert.equal(stage?.state, "failed");
  assert.match(stage!.detail, /слепок корпуса/);
});

test("прогона без набора этап не выдумывает", () => {
  assert.equal(audienceStage(null), null);
});

test("пока аудитория считается, текущий шаг — она, а не «Разбор файла»", () => {
  const scale = stageScale({ nodeCount: 12, nodeDone: 0, nodeIndex: -1, stage: audienceStage(BUSY) });
  assert.equal(scale.total, 13);
  assert.equal(scale.stepNumber, 1);
  assert.equal(scale.done, 0);
});

test("готовая аудитория — пройденный шаг, и конвейер сдвинут на единицу", () => {
  const scale = stageScale({ nodeCount: 12, nodeDone: 3, nodeIndex: 3, stage: audienceStage(READY) });
  assert.equal(scale.total, 13);
  assert.equal(scale.done, 4, "три узла плюс сама аудитория");
  assert.equal(scale.stepNumber, 5, "четвёртый узел — пятый шаг шкалы");
});

test("без набора шкала считается ровно как прежде", () => {
  const scale = stageScale({ nodeCount: 12, nodeDone: 3, nodeIndex: 3, stage: null });
  assert.equal(scale.total, 12);
  assert.equal(scale.stepNumber, 4);
  assert.equal(scale.pct, 25);
});

test("шаг не выходит за шкалу на завершённом прогоне", () => {
  const scale = stageScale({ nodeCount: 12, nodeDone: 12, nodeIndex: 11, stage: audienceStage(READY) });
  assert.equal(scale.stepNumber, 13);
  assert.equal(scale.pct, 100);
});
