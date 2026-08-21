import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { probeVideo } from "./s3.ts";

/**
 * ffprobe читает настоящий файл, а не выдуманный (п. 21).
 *
 * ─── Что здесь проверяется ─────────────────────────────────────────────────
 * Валидация загруженного видео стояла в правильном месте — после того, как
 * байты доехали в S3, по подписанной ссылке, — и не имела ни одной проверки на
 * настоящем файле. Всё, что о ней было известно: код вызывает ffprobe и
 * разбирает JSON. Разбор полей при этом ничем не подтверждён: перепутанные
 * width и height, длительность из потока вместо контейнера, кодек в другом
 * регистре — всё это выглядит работающим, пока не посмотришь на числа.
 *
 * Проверка идёт по локальному файлу: ffprobe принимает и путь, и URL одинаково,
 * а поднимать ради теста S3 значило бы проверять сеть вместо разбора.
 */

function ffmpegAvailable(): boolean {
  try {
    execFileSync("ffmpeg", ["-version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

test("ffprobe отдаёт длительность, кодек и размер кадра настоящего файла", { skip: !ffmpegAvailable() && "ffmpeg недоступен" }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "agora-probe-"));
  const file = join(dir, "sample.mp4");

  // 3 секунды, 320×240, h264 — величины заведомо известные, поэтому ошибка
  // разбора видна как расхождение, а не как «какое-то число».
  execFileSync("ffmpeg", [
    "-y", "-v", "error",
    "-f", "lavfi", "-i", "color=c=red:s=320x240:r=25",
    "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", file,
  ]);

  const probe = await probeVideo(file, statSync(file).size);

  assert.equal(probe.codec, "h264");
  assert.equal(probe.width, 320);
  assert.equal(probe.height, 240);
  assert.ok(
    Math.abs(probe.durationSec - 3) < 0.5,
    `длительность ${probe.durationSec} не похожа на 3 секунды`,
  );
});

test("файл без видеопотока отвергается по существу", { skip: !ffmpegAvailable() && "ffmpeg недоступен" }, async () => {
  // Аудио без картинки — самый частый способ загрузить «не то»: файл валиден,
  // ffprobe его читает, а видео в нём нет. Отказ обязан называть причину, иначе
  // человек будет искать её в сети и в правах.
  const dir = mkdtempSync(join(tmpdir(), "agora-probe-"));
  const file = join(dir, "sound.m4a");
  execFileSync("ffmpeg", [
    "-y", "-v", "error",
    "-f", "lavfi", "-i", "sine=frequency=440",
    "-t", "1", "-c:a", "aac", file,
  ]);

  await assert.rejects(
    () => probeVideo(file, statSync(file).size),
    /видео/i,
    "отказ обязан называть отсутствие видеопотока",
  );
});
