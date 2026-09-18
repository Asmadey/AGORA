import assert from "node:assert/strict";
import { test } from "node:test";

import {
  formatAxisTimecode,
  formatTimecode,
  parseTimecode,
  riskMarkerOpacity,
  riskMarkerScale,
  riskPointPosition,
  segmentBarPercent,
  segmentDimensionLabel,
} from "./report-charts.ts";

test("таймкод диаграммы сохраняет часы и ведущие нули", () => {
  assert.equal(formatTimecode(0), "0:00");
  assert.equal(formatTimecode(125), "2:05");
  assert.equal(formatTimecode(3725), "1:02:05");
  assert.equal(formatAxisTimecode(161.7), "2:41.7");
});

test("точка риска получает положение только по известной длительности", () => {
  assert.equal(riskPointPosition(30, 120), 25);
  assert.equal(riskPointPosition(150, 120), 100);
  assert.equal(riskPointPosition(30, 0), null);
  assert.equal(parseTimecode("1:02:05"), 3725);
  assert.equal(parseTimecode("битый"), null);
});

test("масштаб и насыщенность маркера растут вместе с числом персон", () => {
  assert.ok(riskMarkerScale(10, 10) > riskMarkerScale(1, 10));
  assert.ok(riskMarkerOpacity(10, 10) > riskMarkerOpacity(1, 10));
});

test("полосы сегментов имеют общий предел и не рисуют отсутствие числа", () => {
  assert.equal(segmentBarPercent(8), 80);
  assert.equal(segmentBarPercent(12), 100);
  assert.equal(segmentBarPercent(null), null);
});

test("подавленный сегмент получает человеческую подпись измерения", () => {
  assert.equal(segmentDimensionLabel("geo"), "Тип населённого пункта");
  assert.equal(segmentDimensionLabel("unknown"), "unknown");
});
