import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { checkVideoRef, looksLikeObjectKey } from "./launch-contract.ts";

/**
 * Запуск без пригодного материала отвергается до постановки в очередь.
 *
 * Поводом стали два прогона на боевом сервере, оба упавшие в первом же узле:
 * один с пустым `video_ref` («ValueError: video_ref пуст»), другой с
 * `s3://fixtures/short_60s.mp4` («FileNotFoundError»). Оба были созданы
 * маршрутом без единого возражения, поставлены в очередь и провалились уже у
 * воркера — то есть пользователь увидел появившееся исследование, которое
 * тут же стало FAILED.
 */

const TENANT = "de15d1e3-e2f6-41c7-966d-91c186046066";
const OTHER = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
const GOOD = `tenants/${TENANT}/uploads/8f14e45f-ceea-467a-9575-1c1d1d1d1d1d.mp4`;

test("материал обязателен", async (t) => {
  await t.test("отсутствует — отказ", () => {
    for (const empty of [undefined, null, ""]) {
      const err = checkVideoRef(empty, TENANT);
      assert.ok(err, `${JSON.stringify(empty)} прошёл как материал`);
      assert.match(err, /обязателен/);
    }
  });

  await t.test("отказ объясняет, откуда взять ключ", () => {
    // Маршрут открыт не только визарду. «videoRef: некорректен» отправляет
    // читающего в исходники вместо исправления запроса.
    const err = checkVideoRef(undefined, TENANT);
    assert.ok(err);
    assert.match(err, /upload\/complete/);
  });
});

test("негодный ключ отвергается", async (t) => {
  await t.test("адрес s3:// — не ключ", () => {
    // Ровно то значение, на котором упал прогон 0063.
    const err = checkVideoRef("s3://fixtures/short_60s.mp4", TENANT);
    assert.ok(err);
    assert.match(err, /не похож на ключ/);
  });

  await t.test("локальный путь — не ключ", () => {
    assert.ok(checkVideoRef("/tmp/video.mp4", TENANT));
    assert.ok(checkVideoRef("evals/fixtures/short_60s.mp4", TENANT));
  });

  await t.test("ключ кадров или проксивидео — не материал запуска", () => {
    // Похожая форма, другой префикс: `runs/`, а не `uploads/`.
    assert.ok(checkVideoRef(`tenants/${TENANT}/runs/abc/frames/000.jpg`, TENANT));
  });
});

test("чужой ключ отвергается", () => {
  // RLS не распространяется на S3. Без этой проверки можно было запустить
  // прогон на файле соседнего арендатора: строка tasks создалась бы в своём,
  // а воркер скачал бы чужой объект. /api/upload/complete префикс проверяет —
  // запуск не проверял, хотя это та же граница.
  const foreign = `tenants/${OTHER}/uploads/8f14e45f-ceea-467a-9575-1c1d1d1d1d1d.mp4`;
  const err = checkVideoRef(foreign, TENANT);
  assert.ok(err, "чужой ключ принят");
  assert.match(err, /другому арендатору/);
});

test("настоящий ключ принимается", () => {
  assert.equal(checkVideoRef(GOOD, TENANT), null);
  assert.equal(checkVideoRef(`  ${GOOD}  `, TENANT), null, "пробелы по краям не должны мешать");
  assert.ok(looksLikeObjectKey(GOOD));
});

test("формат ключа совпадает с тем, что создаёт веб и читает воркер", () => {
  // Три копии одного формата: здесь, в lib/server/s3.ts (создаётся) и в
  // agent_core/storage.py (читается). Разойдясь, они дали бы запуск, который
  // маршрут принимает, а воркер отвергает, — то есть ровно тот отказ, который
  // эта проверка и должна была предотвратить.
  const web = new URL("..", import.meta.url).pathname;
  const s3 = readFileSync(join(web, "lib", "server", "s3.ts"), "utf8");
  assert.match(
    s3,
    /tenants\/\$\{tenantId\}\/uploads\//,
    "lib/server/s3.ts больше не строит ключ вида tenants/<id>/uploads/",
  );

  const worker = readFileSync(
    join(web, "..", "..", "services", "agent-core", "agent_core", "storage.py"),
    "utf8",
  );
  assert.match(
    worker,
    /\^tenants\/\[0-9a-f-\]\{36\}\/uploads\/\[\^\/\]\+\$/,
    "правило ключа в storage.py изменилось — проверка запуска разошлась с воркером",
  );
});
