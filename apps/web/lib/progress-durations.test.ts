import assert from "node:assert/strict";
import { test } from "node:test";

import { mergeDurations } from "./progress-durations.ts";

/**
 * Длительность завершённого шага на экране прогресса.
 *
 * ─── Что видел владелец ───────────────────────────────────────────────────
 * «Расшифровка и спикеры (559 сек)» тикало, пока шаг шёл, и обнулялось, как
 * только конвейер переходил к следующему.
 *
 * ─── Причина ──────────────────────────────────────────────────────────────
 * Воркер считает `duration_sec` для каждого завершённого узла и кладёт
 * `timings` в КАЖДОЕ публикуемое событие (`progress.py:109`). До экрана они не
 * доезжали: интерфейс `ProgressEvent` этого поля не объявлял, и клиент его
 * выбрасывал. Длительности брались только из серверного пропа, который
 * заполняется из Postgres в конце всего прогона.
 */

test("длительности из живого события попадают на экран", () => {
  const merged = mergeDurations({}, [
    { node: "extract_audio", duration_sec: 12.4, status: "DONE" },
  ]);
  assert.equal(merged.extract_audio, 12.4);
});

test("незавершённый шаг длительности не имеет", () => {
  // У идущего узла `duration_sec` равен null: воркер проставляет его в момент
  // перехода. Ноль вместо этого показал бы «(0 сек)» на шаге, который идёт.
  const merged = mergeDurations({}, [
    { node: "transcribe_and_diarize", duration_sec: null, status: "RUNNING" },
  ]);
  assert.equal(merged.transcribe_and_diarize, undefined);
});

test("живое значение важнее серверного", () => {
  // Серверное приходит из Postgres и записывается в конце прогона. Пока прогон
  // идёт, оно от предыдущего запуска того же узла — при возобновлении из
  // чекпоинта такое бывает.
  const merged = mergeDurations({ extract_audio: 99 }, [
    { node: "extract_audio", duration_sec: 12, status: "DONE" },
  ]);
  assert.equal(merged.extract_audio, 12);
});

test("серверное остаётся, если живого нет", () => {
  // Вкладка, открытая после конца прогона: событий не будет вовсе.
  const merged = mergeDurations({ extract_audio: 99 }, []);
  assert.equal(merged.extract_audio, 99);
});

test("повторный проход по узлу берёт последнюю длительность", () => {
  // Возобновление после перезапуска воркера проходит узел заново.
  const merged = mergeDurations({}, [
    { node: "extract_audio", duration_sec: 12, status: "DONE" },
    { node: "extract_audio", duration_sec: 7, status: "DONE" },
  ]);
  assert.equal(merged.extract_audio, 7);
});

test("мусор в событии не роняет экран", () => {
  // Снимок приходит из Valkey и разбирается как есть. Уронить страницу
  // идущего прогона из-за одной битой записи — худшее, что можно сделать.
  const merged = mergeDurations({ a: 1 }, [
    null,
    { node: "", duration_sec: 5 },
    { duration_sec: 5 },
    { node: "b", duration_sec: "нет" },
    { node: "c", duration_sec: 3 },
  ] as never);
  assert.deepEqual(merged, { a: 1, c: 3 });
});

test("отсутствие timings — не ошибка", () => {
  assert.deepEqual(mergeDurations({ a: 1 }, undefined), { a: 1 });
});
