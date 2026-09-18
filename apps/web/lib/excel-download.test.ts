import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import {
  EXCEL_MEDIA_TYPE,
  excelDisposition,
  excelFileName,
  excelHref,
  excelUpstreamError,
} from "./excel-download.ts";

/**
 * Книга Excel доходит до кнопки.
 *
 * ─── Повод ─────────────────────────────────────────────────────────────────
 * Сборщик книги (`agent_core/analytics/excel_export.py`) был написан целиком и
 * покрыт тестами, но звали его только они. В меню скачивания стоял один формат
 * — `report-<id>.json`, — и оператор, которому нужна таблица, получал дерево
 * JSON. Зелёный тест сборщика об этом не сообщал ничего: он проверял форму
 * книги, а не то, что книгу кто-то отдаёт.
 *
 * ─── Почему логика в `lib/`, а не в маршруте ───────────────────────────────
 * `npm test` собирает только `lib/**`. Имя файла и тип содержимого обязаны
 * совпадать у маршрута и у меню; две копии строки
 * «application/vnd.openxmlformats-…» разошлись бы молча, и браузер показал бы
 * книгу текстом вместо того, чтобы сохранить её.
 */

const WEB = join(import.meta.dirname, "..");
const ROUTE = join(WEB, "app", "api", "tasks", "[id]", "excel", "route.ts");
const MENU = join(WEB, "components", "agora", "DownloadMenu.tsx");

const RUN = "8f14e45f-ceea-467a-9575-1c1d1d1d1d1d";

test("адрес и имя файла", async (t) => {
  await t.test("ссылка ведёт в маршрут прогона", () => {
    assert.equal(excelHref(RUN), `/api/tasks/${RUN}/excel`);
  });

  await t.test("имя файла называет прогон и оканчивается на .xlsx", () => {
    const name = excelFileName(RUN);
    assert.ok(name.endsWith(".xlsx"), `${name} не .xlsx — Excel такой файл не откроет`);
    assert.ok(name.includes(RUN), `${name} не называет прогон: две выгрузки в «Загрузках» неразличимы`);
  });

  await t.test("заголовок просит сохранить, а не показать", () => {
    const header = excelDisposition(RUN);
    assert.match(header, /^attachment;/);
    assert.ok(header.includes(excelFileName(RUN)));
  });

  await t.test("тип содержимого — именно xlsx", () => {
    assert.equal(
      EXCEL_MEDIA_TYPE,
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    );
  });
});

test("отказ службы объясняет, куда смотреть", () => {
  const message = excelUpstreamError(502, "connection refused");
  // «Ошибка 502» отправляет читающего в исходники веба, где ничего нет:
  // собирает книгу другой контейнер, и поднят он или нет — первое, что надо
  // проверить.
  assert.match(message, /502/);
  assert.match(message, /agent-api/);
});

test("маршрут выгрузки существует и проверяет доступ", async (t) => {
  assert.ok(existsSync(ROUTE), "нет app/api/tasks/[id]/excel/route.ts — скачивать нечего");
  const source = readFileSync(ROUTE, "utf-8");

  await t.test("сессия и принадлежность прогона проверяются в вебе", () => {
    assert.match(source, /requireSession/);
    // Служба агента не опубликована наружу и доступ не проверяет — это делает
    // веб. Забыть здесь значит отдать чужую выгрузку по угаданному id.
    assert.match(source, /withTenant/);
  });

  await t.test("незавершённый прогон не выгружается", () => {
    assert.match(
      source,
      /REPORT_READY/,
      "книга по прогону без отчёта собралась бы пустой и выглядела бы как потерянные данные",
    );
  });

  await t.test("книгу собирает воркер, а не веб", () => {
    // §6: нативные npm-модули в apps/web запрещены, и сборка xlsx на Node —
    // ровно тот случай. Появление здесь имени пакета-сборщика означает, что
    // запрет обошли.
    assert.match(source, /AGENT_API_URL/);
    assert.doesNotMatch(source, /exceljs|xlsx-populate|node-xlsx|require\("xlsx"\)/);
  });

  await t.test("заголовки берутся из общего места", () => {
    assert.match(source, /excelDisposition/);
    assert.match(source, /EXCEL_MEDIA_TYPE/);
  });
});

test("меню предлагает Excel", () => {
  const menu = readFileSync(MENU, "utf-8");
  assert.match(menu, /excelHref/, "меню не ведёт в маршрут выгрузки");
  assert.match(menu, /Excel/, "пункта «Excel» в меню нет — кнопки по-прежнему не существует");
});
