import { strict as assert } from "node:assert";
import { describe, it } from "node:test";

import { uploadProgressLabel, type UploadState } from "./upload.ts";

/**
 * Подпись состояния загрузки.
 *
 * ─── Почему это вообще тестируется ─────────────────────────────────────────
 * Загрузка шла через `fetch`, а он не сообщает прогресса в принципе. Всё, что
 * видел пользователь на 700-мегабайтном ролике, — неопределённый спиннер и
 * слово «Загружается…». Отличить «идёт» от «повисло» было нечем, и на четвёртом
 * шаге визарда появлялось «не приложен материал» — верное по сути и
 * необъяснимое на вид.
 *
 * Подпись отделена от компонента, потому что именно в ней живут все решения:
 * что показывать при нуле, что при завершённой заливке, но незакрытом
 * `complete`, и как не соврать про сто процентов раньше времени.
 */

describe("подпись загрузки", () => {
  it("до начала не обещает процентов", () => {
    const state: UploadState = { phase: "idle", sent: 0, total: 0 };
    assert.equal(uploadProgressLabel(state), "");
  });

  it("во время заливки показывает проценты и объём", () => {
    const state: UploadState = { phase: "uploading", sent: 35_000_000, total: 100_000_000 };
    const label = uploadProgressLabel(state);
    assert.match(label, /35\s?%/);
    assert.match(label, /из/);
  });

  it("подпись при неизвестном размере не делит на ноль", () => {
    const state: UploadState = { phase: "uploading", sent: 10, total: 0 };
    const label = uploadProgressLabel(state);
    assert.doesNotMatch(label, /NaN|Infinity/);
  });

  /**
   * Сто процентов заливки — ещё не готовый материал.
   *
   * После последнего байта идёт `POST /api/upload/complete`: ffprobe проверяет
   * контейнер, кодеки и длительность. Написать «готово» до его ответа значит
   * пообещать принятый файл, который может быть отвергнут — и тогда «100%»
   * сменится ошибкой, а пользователь решит, что сломалось на ровном месте.
   */
  it("после последнего байта говорит о проверке, а не о готовности", () => {
    const state: UploadState = { phase: "checking", sent: 100, total: 100 };
    const label = uploadProgressLabel(state);
    assert.doesNotMatch(label, /готов/i);
    assert.match(label, /провер/i);
  });

  it("ошибка вытесняет проценты", () => {
    const state: UploadState = {
      phase: "failed",
      sent: 50,
      total: 100,
      error: "заливка в S3 вернула 403",
    };
    assert.match(uploadProgressLabel(state), /403/);
  });
});

describe("процент загрузки", () => {
  it("не превышает ста при округлении", async () => {
    const { uploadPercent } = await import("./upload.ts");
    assert.equal(uploadPercent({ phase: "uploading", sent: 999_999, total: 1_000_000 }), 99);
    assert.equal(uploadPercent({ phase: "checking", sent: 1_000_000, total: 1_000_000 }), 100);
  });

  it("при неизвестном размере возвращает null, а не ноль", async () => {
    const { uploadPercent } = await import("./upload.ts");
    // Ноль означал бы «ничего не отправлено» — то есть неправду про идущую
    // заливку. Полоса в таком случае обязана быть неопределённой.
    assert.equal(uploadPercent({ phase: "uploading", sent: 10, total: 0 }), null);
  });
});
