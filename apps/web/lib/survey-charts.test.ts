import assert from "node:assert/strict";
import { test } from "node:test";

import {
  barLengthPercent,
  donutSegments,
  formatMean,
  formatShare,
  npsPoints,
  scaleFillPercent,
  smallSliceNote,
  stackedSegments,
} from "./survey-charts.ts";

test("формат доли сохраняет измеренный ноль и отсутствие ответа", () => {
  assert.equal(formatShare(0), "0%");
  assert.equal(formatShare(null), "—");
  assert.notEqual(formatShare(0), formatShare(null));
});

test("среднее использует запятую и прочерк для отсутствующего значения", () => {
  assert.equal(formatMean(8.5), "8,5");
  assert.equal(formatMean(null), "—");
});

test("заливка шкалы зажимается в границах и не делит вырожденную шкалу", () => {
  assert.equal(scaleFillPercent(-2, 0, 10), 0);
  assert.equal(scaleFillPercent(12, 0, 10), 100);
  assert.equal(scaleFillPercent(5, 10, 10), null);
  assert.equal(scaleFillPercent(5, 10, 9), null);
  assert.equal(scaleFillPercent(null, 0, 10), null);
});

test("длина столбика при нулевом максимуме равна нулю", () => {
  assert.equal(barLengthPercent(0, 0), 0);
  assert.equal(barLengthPercent(0.4, 0), 0);
  assert.equal(barLengthPercent(0.4, 0.8), 50);
  assert.ok(Number.isFinite(barLengthPercent(0.4, 0)));
});

test("кольцо строит неперекрывающиеся дольки и сообщает о превышении ста процентов", () => {
  const result = donutSegments([
    { id: "a", share: 0.2 },
    { id: "b", share: 0.3 },
    { id: "missing", share: null },
  ]);

  assert.equal(result.segments[0]?.offset, 0);
  assert.equal(result.segments[0]?.length, 20);
  assert.equal(result.segments[1]?.offset, 20);
  assert.equal(result.segments[1]?.length, 30);
  assert.equal(result.totalShare, 0.5);
  assert.equal(result.exceedsTotal, false);
  assert.equal(result.segments[2]?.missing, true);

  const overfull = donutSegments([
    { id: "a", share: 0.7 },
    { id: "b", share: 0.6 },
  ]);
  assert.equal(overfull.exceedsTotal, true);
  assert.equal(overfull.totalShare, 1.3);
  assert.equal(
    overfull.segments.at(-1)!.offset + overfull.segments.at(-1)!.length,
    100,
    "после нормировки дольки не перекрываются",
  );
});

test("100%-stacked сохраняет доли и выделяет остаток как не ответили", () => {
  const result = stackedSegments([
    { id: "negative", label: "Нет", share: 0.2 },
    { id: "positive", label: "Да", share: 0.5 },
  ]);

  assert.deepEqual(
    result.segments.map(({ id, share, offset, remainder }) => ({ id, share, offset, remainder })),
    [
      { id: "negative", share: 0.2, offset: 0, remainder: false },
      { id: "positive", share: 0.5, offset: 0.2, remainder: false },
      { id: "unanswered", share: 0.3, offset: 0.7, remainder: true },
    ],
  );
  assert.equal(result.totalShare, 0.7);
});

test("NPS не считается при отсутствии одной из долей", () => {
  assert.equal(npsPoints(0.75, 0.2), 55);
  assert.equal(npsPoints(0, 0), 0);
  assert.equal(npsPoints(null, 0.2), null);
  assert.equal(npsPoints(0.75, null), null);
});

test("заметка о малом срезе появляется строго ниже порога", () => {
  assert.match(
    smallSliceNote(14, 15, "14-35") ?? "",
    /Срез 14-35 содержит 14 персон.*малого размера группы\./,
  );
  assert.equal(smallSliceNote(15, 15, "14-35"), null);
  assert.equal(smallSliceNote(null, 15, "14-35"), null);
});
