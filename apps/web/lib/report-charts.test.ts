import assert from "node:assert/strict";
import { test } from "node:test";

import {
  donatedValuesAbsence,
  formatAxisTimecode,
  formatTimecode,
  parseTimecode,
  riskMarkerOpacity,
  riskMarkerScale,
  riskPointPosition,
  riskSectionState,
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

test("ноль точек риска при измеренном удержании — это результат, а не пропажа", () => {
  /*
   * Прогон «Тизер_Дорога_домой»: удержание 100 %, точек риска ноль. Раздел
   * скрывался целиком, и владелец спросил, куда делись графики.
   *
   * Числа взяты с боевого отчёта 4cc3e7f8, а не выдуманы: на выдуманной
   * фикстуре с парой точек этот случай не воспроизводится вовсе.
   */
  assert.deepEqual(riskSectionState(0, 100, 38.56), { kind: "none-stopped" });
  assert.deepEqual(riskSectionState(0, 0, 38.56), { kind: "none-stopped" },
    "нулевое удержание — тоже измеренное; ноль и null различаются");
  assert.deepEqual(riskSectionState(0, null, 38.56), { kind: "not-measured" });
});

test("точки риска показываются со шкалой, а без длительности — списком", () => {
  // Боевой прогон 8c8f0cce: десять точек, длительность 2936 секунд.
  assert.deepEqual(riskSectionState(10, 93.3, 2936.047166), { kind: "chart" });
  assert.deepEqual(riskSectionState(10, 93.3, null), { kind: "list" },
    "без длительности ось строить нечестно, но точки показать можно");
  assert.deepEqual(riskSectionState(10, 93.3, 0), { kind: "list" },
    "нулевая длительность — та же невозможность оси");
});

test("отсутствие плитки ценностей объясняется, а не замалчивается", () => {
  assert.equal(donatedValuesAbsence(true, true), null, "вопрос есть — объяснять нечего");
  assert.match(
    donatedValuesAbsence(false, false) ?? "",
    /без анкеты/,
    "прогон без анкеты называется своей причиной",
  );
  assert.match(
    donatedValuesAbsence(false, true) ?? "",
    /не задавался/,
    "анкета была, но восьмого вопроса в ней нет — это другая причина",
  );
});
