import assert from "node:assert/strict";
import { test } from "node:test";

import { humanDuration, progressStates } from "./progress-state.ts";

/**
 * ─── Что сломалось ──────────────────────────────────────────────────────────
 * На завершённом прогоне 0051 экран прогресса показывал «Шаг 1 из 13», а
 * пройденные шаги стояли без галочек — при том, что время у каждого было.
 *
 * Причина в источнике правды. Состояние шагов выводилось ТОЛЬКО из последнего
 * события SSE, а событие берётся из снимка в Valkey. У снимка есть срок жизни:
 * через сутки после прогона его нет, событие не приходит, и экран считает, что
 * прогон не начинался. Длительности при этом рисуются — они приходят из
 * Postgres отдельным пропом, и потому картинка получалась противоречивой:
 * время есть, а шаг «не пройден».
 *
 * Postgres знает и `status`, и `finished_at`, и длительность каждого шага. Он и
 * есть источник правды после прогона; Valkey — только для живого.
 */

const NODES = ["probe", "extract", "transcribe", "report"];

test("завершённый прогон без единого события всё равно пройден", () => {
  const s = progressStates({
    nodes: NODES,
    taskStatus: "REPORT_READY",
    durations: { probe: 12, extract: 3, transcribe: 900, report: 1 },
  });
  assert.equal(s.finished, true);
  assert.deepEqual(s.states, ["done", "done", "done", "done"]);
  assert.equal(s.doneCount, 4);
});

test("шаг с записанной длительностью пройден, даже если событий нет", () => {
  // Прогон упал на транскрипции: два первых шага отработали и время у них есть.
  const s = progressStates({
    nodes: NODES,
    taskStatus: "FAILED",
    durations: { probe: 12, extract: 3 },
  });
  assert.deepEqual(s.states.slice(0, 2), ["done", "done"]);
  assert.equal(s.failed, true);
});

test("идущий прогон ведётся по событию, а не по базе", () => {
  const s = progressStates({
    nodes: NODES,
    currentNode: "transcribe",
    eventStatus: "RUNNING",
    taskStatus: "RUNNING",
    durations: { probe: 12, extract: 3 },
  });
  assert.deepEqual(s.states, ["done", "done", "running", "waiting"]);
  assert.equal(s.currentIndex, 2);
  assert.equal(s.doneCount, 2);
});

test("событие DONE по узлу закрывает его", () => {
  const s = progressStates({
    nodes: NODES,
    currentNode: "extract",
    eventStatus: "DONE",
    taskStatus: "RUNNING",
    durations: {},
  });
  assert.deepEqual(s.states, ["done", "done", "waiting", "waiting"]);
  assert.equal(s.doneCount, 2);
});

test("ничего не известно — ничего и не показываем пройденным", () => {
  const s = progressStates({ nodes: NODES, taskStatus: "QUEUED", durations: {} });
  assert.deepEqual(s.states, ["waiting", "waiting", "waiting", "waiting"]);
  assert.equal(s.doneCount, 0);
  assert.equal(s.currentIndex, -1);
});

test("отменённый прогон не выдаётся за успешный", () => {
  const s = progressStates({
    nodes: NODES,
    taskStatus: "CANCELLED",
    durations: { probe: 12 },
  });
  assert.equal(s.finished, false);
  assert.equal(s.failed, true);
});

/**
 * ─── Время по-человечески ───────────────────────────────────────────────────
 * «172:14» — это две минуты? три часа? Прочитать нельзя, а именно это число
 * владелец видит первым. Просьба владельца 20.08.2026: часы, минуты и секунды
 * словами.
 */

test("меньше минуты — только секунды", () => {
  assert.equal(humanDuration(0), "0 сек");
  assert.equal(humanDuration(45), "45 сек");
});

test("минуты и секунды", () => {
  assert.equal(humanDuration(90), "1 мин 30 сек");
  assert.equal(humanDuration(600), "10 мин");
});

test("часы, минуты и секунды", () => {
  assert.equal(humanDuration(5310), "1 час 28 мин 30 сек");
  // Прогон 0051: 172:14 на экране — это два часа пятьдесят две минуты.
  assert.equal(humanDuration(10334), "2 часа 52 мин 14 сек");
  assert.equal(humanDuration(18000), "5 часов");
});

test("нули внутри не печатаются", () => {
  assert.equal(humanDuration(3600), "1 час");
  assert.equal(humanDuration(3601), "1 час 1 сек");
  assert.equal(humanDuration(3660), "1 час 1 мин");
});

test("склонение часов идёт по последней цифре, а не по первой", () => {
  assert.equal(humanDuration(21 * 3600), "21 час");
  assert.equal(humanDuration(11 * 3600), "11 часов", "одиннадцать — не «час»");
});

test("дробные секунды округляются, отрицательные не пропускаются", () => {
  assert.equal(humanDuration(59.6), "1 мин");
  assert.equal(humanDuration(-5), "0 сек");
});
