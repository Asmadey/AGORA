import assert from "node:assert/strict";
import { test } from "node:test";

import { objectKeysOf } from "./run-cleanup.ts";

/**
 * Что уходит из хранилища вместе с исследованием.
 *
 * ─── Что было ───────────────────────────────────────────────────────────────
 * Ручка удаления убирала строку в Postgres, документы `reports` и
 * `report_personas` в Mongo и ИСХОДНЫЙ ролик. Всё остальное оставалось:
 *
 *   * `content_packs` — таймлайн, сцены и расшифровка. На боевой базе 36 из 41
 *     пакета уже осиротели: прогонов, которым они принадлежали, нет;
 *   * кадры сцен в S3 — по одному файлу на сцену, сотни на прогон;
 *   * `playback_ref` — вторая копия ролика, перекодированная для плеера.
 *
 * Заметить это нельзя ниоткуда: исследование пропадает из списка, экран чист, а
 * место занято. Счёт за хранилище приходит раз в месяц и не объясняет, чем.
 */

const PACK = {
  scenes: [
    { screenshot: "tenants/t1/runs/r1/frames/000000000.jpg" },
    { screenshot: "tenants/t1/runs/r1/frames/000004000.jpg" },
    { screenshot: "" },
    {},
  ],
};

test("исходный ролик, копия для плеера и заставка — всё уходит", () => {
  const keys = objectKeysOf({
    videoRef: "tenants/t1/uploads/a.mp4",
    playbackRef: "playback/t1/r1.mp4",
    posterRef: "tenants/t1/runs/r1/frames/000000000.jpg",
    pack: null,
  });
  assert.ok(keys.includes("tenants/t1/uploads/a.mp4"));
  assert.ok(keys.includes("playback/t1/r1.mp4"), "копия для плеера оставалась в хранилище");
  assert.ok(keys.includes("tenants/t1/runs/r1/frames/000000000.jpg"));
});

test("кадры сцен берутся из пакета материала", () => {
  const keys = objectKeysOf({ videoRef: null, playbackRef: null, posterRef: null, pack: PACK });
  assert.equal(keys.length, 2);
  assert.ok(keys.every((k) => k.includes("/frames/")));
});

test("ключи не повторяются", () => {
  // Заставка — это первый кадр, и он же лежит в пакете. Дважды удалять незачем.
  const keys = objectKeysOf({
    videoRef: null,
    playbackRef: null,
    posterRef: "tenants/t1/runs/r1/frames/000000000.jpg",
    pack: PACK,
  });
  assert.equal(new Set(keys).size, keys.length);
  assert.equal(keys.length, 2);
});

test("пустые и отсутствующие значения не превращаются в ключи", () => {
  // Пустая строка, отправленная в S3 как ключ, удаляет не то, что задумано,
  // либо отвечает ошибкой — и то и другое хуже пропуска.
  assert.deepEqual(
    objectKeysOf({ videoRef: null, playbackRef: "", posterRef: undefined, pack: { scenes: [] } }),
    [],
  );
});

test("пакет без сцен и без пакета вовсе — законные случаи", () => {
  assert.deepEqual(objectKeysOf({ videoRef: null, playbackRef: null, posterRef: null, pack: {} }), []);
  assert.deepEqual(objectKeysOf({ videoRef: null, playbackRef: null, posterRef: null, pack: null }), []);
});

test("посторонние поля пакета ключами не считаются", () => {
  const keys = objectKeysOf({
    videoRef: null,
    playbackRef: null,
    posterRef: null,
    pack: { scenes: [{ screenshot: 42 as unknown as string }, { screenshot: "ok/key.jpg" }] },
  });
  assert.deepEqual(keys, ["ok/key.jpg"]);
});
