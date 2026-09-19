import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import {
  isTimelineCellRendered,
  timelineRenderWindow,
} from "./timeline-render-window.ts";

const WEB = new URL("..", import.meta.url).pathname;

function read(rel: string): string {
  const p = join(WEB, rel);
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}

function code(text: string): string {
  return text
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

const timelineSource = code(read("components/agora/Timeline.tsx"));

test("Timeline подключает модуль окна рендера", () => {
  assert.match(
    timelineSource,
    /timeline-render-window/,
    "правило окна рендера должно жить в apps/web/lib, а не быть условием в JSX",
  );
});

test("окно обновляется нативным IntersectionObserver", () => {
  assert.match(timelineSource, /IntersectionObserver/);
  assert.match(timelineSource, /isTimelineCellRendered/);
});

test("печать раскрывает все ячейки, а поиск получает полный текст реплик", () => {
  assert.match(timelineSource, /beforeprint/);
  assert.match(timelineSource, /afterprint/);
  assert.match(timelineSource, /data-timeline-search-index/);
  assert.match(timelineSource, /printMode/);
});

test("окно оставляет запас с обеих сторон видимой области", () => {
  assert.deepEqual(timelineRenderWindow(20, 5, 8, 2), { start: 3, end: 10 });
});

test("окно при прокрутке к началу не уходит ниже нулевого индекса", () => {
  assert.deepEqual(timelineRenderWindow(20, 0, 3, 3), { start: 0, end: 6 });
});

test("окно при прокрутке к концу не выходит за список и сохраняет запас сверху", () => {
  assert.deepEqual(timelineRenderWindow(20, 17, 20, 3), { start: 14, end: 20 });
});

test("вырожденные списки не создают фиктивные ячейки", () => {
  assert.deepEqual(timelineRenderWindow(0, 0, 0), { start: 0, end: 0 });
  assert.deepEqual(timelineRenderWindow(1, 0, 1, 20), { start: 0, end: 1 });
  assert.deepEqual(timelineRenderWindow(2, 0, 2, 20), { start: 0, end: 2 });
});

test("активная секунда сохраняет ячейку вне видимого окна", () => {
  const window = timelineRenderWindow(322, 0, 3, 3);

  assert.equal(isTimelineCellRendered(5, window), true);
  assert.equal(isTimelineCellRendered(250, window), false);
  assert.equal(isTimelineCellRendered(250, window, 250), true);
});

test("замер для ворот: 322 ячейки превращаются в девять Cell-узлов", () => {
  const total = 322;
  const window = timelineRenderWindow(total, 3, 6, 3);
  const rendered = window.end - window.start;

  console.log(`timeline Cell nodes: before=${total} after=${rendered}`);
  assert.equal(rendered, 9);
});
