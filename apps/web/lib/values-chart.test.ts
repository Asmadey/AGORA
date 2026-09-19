import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import {
  VCIOM_VALUES_SOURCE,
  VALUES_MIN_SAMPLE_SIZE,
  outsideListCount,
  TRADITIONAL_VALUES,
  valueComparison,
  valueChartRows,
} from "./values-chart.ts";

/**
 * Плитка «Ценности ВЦИОМ» на панели показателей.
 *
 * ─── Что показывает ───────────────────────────────────────────────────────
 * Сколько персон этой аудитории несут каждую из семнадцати ценностей. Не то,
 * что ответили реальные респонденты ВЦИОМ, — подпись называет ПЕРЕЧЕНЬ, из
 * которого сделан выбор, а числа принадлежат синтетической аудитории.
 *
 * Разница существенна: у ВЦИОМ «Крепкая семья» набрала 72 из 100, здесь она
 * наберёт столько, сколько выпало при генерации. Спутать одно с другим — это
 * выдать сгенерированное за измеренное.
 *
 * ─── Почему все семнадцать, включая нули ──────────────────────────────────
 * Отсутствующая ценность — это факт об аудитории, а не пустое место. Список из
 * двенадцати строк не даёт понять, двенадцать их всего или пять просто не
 * выпали.
 */

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

// ─── Перечень ───────────────────────────────────────────────────────────────

test("перечень тот же, что у генератора", () => {
  assert.equal(TRADITIONAL_VALUES.length, 17);
  assert.ok(TRADITIONAL_VALUES.includes("Созидательный труд"));
  assert.ok(TRADITIONAL_VALUES.includes("Жизнь"));
});

test("перечень в вебе не разошёлся со справочником в данных", () => {
  // Два источника правды расходятся молча. Здесь их сверяет тест: справочник
  // лежит в data/, веб не читает файлы на клиенте, и копия обязана совпадать.
  const raw = read("../../data/values/traditional_values.json");
  assert.ok(raw, "справочник data/values/traditional_values.json читается");
  const doc = JSON.parse(raw) as { values: string[] };
  assert.deepEqual([...TRADITIONAL_VALUES], doc.values);
});

// ─── Строки графика ─────────────────────────────────────────────────────────

test("показаны все семнадцать, даже с нулём", () => {
  const rows = valueChartRows({ "Крепкая семья": 18, Справедливость: 12 });
  assert.equal(rows.length, 17);
  const zero = rows.find((r) => r.value === "Созидательный труд");
  assert.equal(zero?.count, 0);
});

test("сортировка по убыванию, при равенстве — по перечню", () => {
  const rows = valueChartRows({
    Справедливость: 5,
    "Крепкая семья": 9,
    Достоинство: 5,
  });
  assert.equal(rows[0].value, "Крепкая семья");
  // «Достоинство» стоит в перечне раньше «Справедливости» — при равном счёте
  // порядок обязан быть устойчивым, иначе две отрисовки дадут разный график.
  const names = rows.slice(1, 3).map((r) => r.value);
  assert.deepEqual(names, ["Достоинство", "Справедливость"]);
});

test("доля считается от максимума, а не от суммы", () => {
  // Столбик показывает «сколько относительно самой частой», а не долю в общем
  // объёме: каждая персона несёт пять ценностей, и сумма долей дала бы 500 %.
  const rows = valueChartRows({ "Крепкая семья": 20, Справедливость: 10 });
  assert.equal(rows[0].share, 1);
  assert.equal(rows[1].share, 0.5);
});

test("пустая аудитория не делит на ноль", () => {
  const rows = valueChartRows({});
  assert.equal(rows.length, 17);
  assert.ok(rows.every((r) => r.count === 0 && r.share === 0));
});

test("неканоническое значение не попадает в график", () => {
  // У персон, созданных до 16.09.2026, встречаются «Неравенство, разделение
  // людей…» и служебные ответы анкеты. Они не ценности и в перечне их нет.
  const rows = valueChartRows({
    "Крепкая семья": 4,
    "Неравенство, разделение людей в соответствии с их способностями": 3,
    "Затрудняюсь ответить": 2,
  });
  assert.equal(rows.length, 17);
  assert.ok(!rows.some((r) => r.value.startsWith("Неравенство")));
});

test("неканоническое считается отдельно, а не пропадает молча", () => {
  // Отброшенное без счёта — это тихая потеря: читатель не узнает, что у части
  // персон стоят значения не из перечня.
  assert.equal(outsideListCount({ "Крепкая семья": 4, "Затрудняюсь ответить": 2 }), 2);
  assert.equal(outsideListCount({ "Крепкая семья": 4 }), 0);
});

function valuePersona(ageGroup: string, values: string[]) {
  return {
    dna: {
      demographics: { age_group: ageGroup },
      values_and_beliefs: { important_values: values },
    },
  };
}

test("доля аудитории считается по персонам и показывает пару чисел", () => {
  const personas = Array.from({ length: 40 }, (_, index) =>
    valuePersona("35-44", index < 30 ? ["Крепкая семья"] : []),
  );

  const row = valueComparison(personas, VCIOM_VALUES_SOURCE).rows.find(
    (item) => item.value === "Крепкая семья",
  );

  assert.ok(row);
  assert.equal(row.audiencePercent, 75);
  assert.equal(row.sourcePercent, 80);
  assert.equal(row.audienceCount, 30);
});

test("источник взвешивается по возрасту набора, а не берётся из «всего»", () => {
  const personas = Array.from({ length: 10 }, () => valuePersona("60+", ["Крепкая семья"]));
  const row = valueComparison(personas, VCIOM_VALUES_SOURCE).rows.find(
    (item) => item.value === "Крепкая семья",
  );

  assert.ok(row);
  assert.equal(row.sourcePercent, 70);
  assert.notEqual(row.sourcePercent, VCIOM_VALUES_SOURCE.shares_percent["Крепкая семья"].всего);
  assert.equal(valueComparison(personas, VCIOM_VALUES_SOURCE).sourceBasis, "60+");
});

test("пять персон получают предупреждение о малой выборке", () => {
  const result = valueComparison(
    Array.from({ length: 5 }, () => valuePersona("60+", ["Крепкая семья"])),
    VCIOM_VALUES_SOURCE,
  );

  assert.equal(VALUES_MIN_SAMPLE_SIZE, 5);
  assert.equal(result.sampleSize, 5);
  assert.equal(result.smallSample, true);
  assert.match(result.sampleMessage ?? "", /малая выборка/i);
});

test("порог графика совпадает с порогом долей отчёта", () => {
  const aggregate = read("../../services/agent-core/agent_core/analytics/aggregate.py");
  const match = /MIN_SEGMENT_PERSONAS\s*=\s*(\d+)/.exec(aggregate);

  assert.ok(match, "порог отчёта не найден");
  assert.equal(Number(match[1]), VALUES_MIN_SAMPLE_SIZE);
});

test("страница набора и отчёт импортируют один компонент ValuesChart", () => {
  const setPage = code(read("app/personas/sets/[id]/page.tsx"));
  const reportBody = code(read("components/agora/ReportBody.tsx"));

  assert.match(setPage, /import \{ ValuesChart \} from "@\/components\/agora\/ValuesChart"/);
  assert.match(reportBody, /import \{ ValuesChart \} from "@\/components\/agora\/ValuesChart"/);
  assert.doesNotMatch(reportBody, /import \{ ValuesChart \} from "[^"].*SurveyValuesChart/);
});

test("блоки заземления и графика складываются в одну колонку на телефоне", () => {
  const setPage = code(read("app/personas/sets/[id]/page.tsx"));
  const reportBody = code(read("components/agora/ReportBody.tsx"));

  assert.match(setPage, /grid-cols-1[^\n]*lg:grid-cols-2/);
  assert.match(reportBody, /grid-cols-1[^\n]*lg:grid-cols-2/);
});

// ─── Плитка ─────────────────────────────────────────────────────────────────

test("плитка модели зрения заменена на ценности", () => {
  const body = code(read("components/agora/ReportBody.tsx"));
  const chart = code(read("components/agora/ValuesChart.tsx"));

  // График DNA аудитории и ответы на вопрос 8 описывают разные вещи. В отчёте
  // должен быть первый, а в панели вопросов остаётся второй.
  assert.ok(/<ValuesChart/.test(body), "график ценностей аудитории есть в отчёте");
  assert.ok(
    !/label="Модель зрения"/.test(body),
    "плитка модели зрения убрана — её место занято",
  );
  // Заголовок живёт в самой плитке: у StatCard значение — строка, и график
  // туда не ложится, поэтому ValuesChart несёт свою оболочку целиком.
  assert.ok(/Ценности ВЦИОМ/.test(chart), "плитка называется «Ценности ВЦИОМ»");
});

test("подпись не выдаёт сгенерированное за измеренное", () => {
  // «Ценности ВЦИОМ» описывает ПЕРЕЧЕНЬ, из которого сделан выбор. Числа
  // принадлежат синтетической аудитории, и подпись обязана это сказать.
  //
  // 16.09.2026 подвал плитки убран по просьбе владельца — плитка должна быть
  // в высоту соседних. Оговорка при этом НЕ убрана, а переехала в строку
  // заголовка, где не стоит высоты. Требование то же, место другое.
  const chart = code(read("components/agora/ValuesChart.tsx"));
  assert.ok(
    /персон аудитории/.test(chart),
    "сказано, что считаются персоны аудитории",
  );
  assert.ok(
    !/border-t/.test(chart),
    "подвала с разделителем под графиком нет",
  );
});

test("пустого графика нет, а отсутствие плитки объясняется", () => {
  // Пустой график хуже отсутствующей плитки: он утверждает, что аудитория не
  // назвала ни одной ценности, тогда как на деле анкеты в прогоне не было.
  //
  // Требование пережило смену содержимого плитки (17.09.2026): теперь на этом
  // месте вопрос 8 анкеты, и условие сторожит его.
  //
  // 18.09.2026 проверка переписана со ШАБЛОНА на СВОЙСТВО. Прежняя искала
  // литерал `donatedValues &&` и покраснела на тернарнике, хотя график
  // по-прежнему рисовался только при данных: она сторожила способ записи, а не
  // требование. Заодно добавлено второе требование — молчать тоже нельзя.
  // Владелец открыл отчёт без вопроса 8, увидел на месте графика пустоту и
  // спросил, куда делись графики.
  const body = code(read("components/agora/ReportBody.tsx"));

  for (const match of body.matchAll(/<SurveyValuesChart/g)) {
    const before = body.slice(Math.max(0, match.index - 200), match.index);
    assert.ok(
      /donatedValues\s*(&&|\?)/.test(before),
      "график ценностей рисуется только под проверкой donatedValues",
    );
  }
  assert.ok(
    /<SurveyValuesChart/.test(body),
    "сам график из отчёта не исчез",
  );
  assert.ok(
    /donatedValuesAbsence\(/.test(body),
    "отсутствие плитки называется причиной, а не оставляет пустоту",
  );
});
