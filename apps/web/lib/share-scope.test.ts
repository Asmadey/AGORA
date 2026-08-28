import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import {
  REPORT_SECTIONS,
  parseScope,
  sectionsFor,
  showsSection,
  type ReportSection,
} from "./share-scope.ts";

/**
 * Что уходит наружу по публичной ссылке.
 *
 * Это единственное место в продукте, где данные арендатора покидают его
 * периметр. Утверждения о таком месте пишутся тестом, а не подразумеваются:
 * ошибка в сторону «показали лишнее» необратима — ссылку уже открыли.
 */

const WEB = new URL("..", import.meta.url).pathname;

test("режим «весь отчёт» показывает весь отчёт", async (t) => {
  await t.test("не пропущена ни одна секция", () => {
    // Тот самый дефект: `scope === "full"` включал одну секцию из двенадцати,
    // и «весь отчёт» отличался от «только сводки» наличием тем.
    assert.deepEqual(sectionsFor("full"), [...REPORT_SECTIONS]);
  });

  await t.test("видны ответы персон и материал", () => {
    for (const s of ["personas", "material", "asked", "synthesis", "qa", "segments"] as ReportSection[]) {
      assert.equal(showsSection("full", s), true, `в режиме full не видно ${s}`);
    }
  });
});

test("режим «только сводка» не отдаёт сырьё", async (t) => {
  await t.test("нет ответов персон, материала, цитат и точек риска", () => {
    // Обратная сторона: расширяя «весь отчёт», легко заодно открыть и сводку.
    for (const s of ["personas", "material", "asked", "synthesis", "riskPoints", "qa", "segments"] as ReportSection[]) {
      assert.equal(showsSection("aggregate", s), false, `сводка отдаёт ${s}`);
    }
  });

  await t.test("числа и выводы видны — иначе сводка ни о чём", () => {
    for (const s of ["metrics", "narrative", "criteria", "emotions"] as ReportSection[]) {
      assert.equal(showsSection("aggregate", s), true, `сводка не показывает ${s}`);
    }
  });

  await t.test("предупреждение о неполном отчёте видно в обеих областях", () => {
    // Скрытый `degraded` означал бы неполный отчёт, выглядящий полным.
    assert.equal(showsSection("aggregate", "degraded"), true);
    assert.equal(showsSection("full", "degraded"), true);
  });

  await t.test("сводка — подмножество полного отчёта, а не другой набор", () => {
    const full = new Set(sectionsFor("full"));
    for (const s of sectionsFor("aggregate")) {
      assert.ok(full.has(s), `секция ${s} есть в сводке и отсутствует в полном отчёте`);
    }
  });
});

test("разбор области из базы", async (t) => {
  await t.test("full распознаётся", () => {
    assert.equal(parseScope("full"), "full");
  });

  await t.test("что угодно другое — сводка, а не полный отчёт", () => {
    // Колонка текстовая. Опечатка при записи не должна оборачиваться показом
    // большего, чем выбрал выпускающий ссылку.
    for (const raw of ["aggregate", "FULL", "", null, undefined, 0, {}, "полный"]) {
      assert.equal(parseScope(raw), "aggregate", `${JSON.stringify(raw)} прочиталось как full`);
    }
  });
});

test("публичная страница рисует отчёт общим компонентом, а не своей копией", () => {
  // Дефект был не в переключателе, а в том, что страница публичной ссылки
  // повторяла отчёт от руки: пять секций против двенадцати. Дописать
  // недостающие семь значило бы завести расхождение заново, только позже.
  //
  // Проверка статическая и грубая: обе страницы обязаны рисовать ReportBody.
  // Она не утверждает, что они одинаковы, — она запрещает второй рисовальщик.
  const shared = readFileSync(join(WEB, "app", "share", "[token]", "page.tsx"), "utf8");
  const internal = readFileSync(join(WEB, "app", "runs", "[id]", "page.tsx"), "utf8");

  for (const [name, src] of [["публичная", shared], ["внутренняя", internal]] as const) {
    assert.match(src, /<ReportBody/, `${name} страница не использует общий ReportBody`);
  }

  // Кнопки действий на публичной странице недопустимы: они ведут в разделы,
  // закрытые сессией, и предлагают гостю то, чего он не может сделать.
  for (const control of ["ShareDialog", "DeleteRunButton", "DownloadMenu"]) {
    assert.doesNotMatch(
      shared,
      new RegExp(`<${control}`),
      `публичная страница показывает ${control}`,
    );
  }
});
