import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { showsSection } from "./share-scope.ts";
import { parseReport, type SurveyView } from "./report-view.ts";
import {
  matrixPairs,
  matrixRows,
  optionPairs,
  optionRows,
  surveyBlocks,
  surveyQuestion,
} from "./report-survey.ts";

/**
 * Читатель поля `survey` обязан совпадать с писателем.
 *
 * ─── Почему фикстура, а не придуманный объект ──────────────────────────────
 * Числа анкеты кладёт `survey_tally` (services/agent-core/agent_core/analytics/
 * survey_stats.py), а забирает их этот разбор. Форма у них общая, и в этом
 * репозитории писатель с читателем расходились уже не раз: разошедшийся
 * читатель не падает — он показывает пустоту, а пустота на экране читается как
 * «анкету не спрашивали».
 *
 * Поэтому фикстура `lib/fixtures/survey-tally.json` — не сочинение, а ВЫВОД
 * самого `survey_tally`: он снят запуском функции на подмножестве анкеты
 * заказчика (вопросы 1, 8, 9, 10, 15 плюс открытый вопрос оператора) и записан
 * без правок. Ключ `counted` снят при `min_segment=2`, ключ `below_threshold` —
 * при `min_segment=20` на тех же данных, потому что подавленный срез имеет
 * СВОЮ форму: числа становятся `null`, а `n` и `base` остаются.
 *
 * Обновлять фикстуру можно только тем же способом — прогоном писателя. Правка
 * её руками возвращает ровно ту болезнь, против которой она заведена.
 */

const WEB = new URL("..", import.meta.url).pathname;

function read(rel: string): string {
  const p = join(WEB, rel);
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}

/** Разбор идёт по коду, а не по комментариям к нему. */
function code(text: string): string {
  return text
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

const FIXTURE = JSON.parse(read("lib/fixtures/survey-tally.json")) as {
  counted: Record<string, unknown>;
  below_threshold: Record<string, unknown>;
};

/** Анкета заказчика читается из данных, а не переписывается сюда второй копией. */
const SURVEY = JSON.parse(
  readFileSync(join(WEB, "../../data/survey/customer_2026.json"), "utf8"),
) as {
  blocks: { id: string; label: string }[];
  questions: { id: string; number: number; options?: { id: string; label: string }[];
               rows?: { id: string; label: string }[] }[];
};

function view(tally: unknown): SurveyView {
  const parsed = parseReport({ aggregate: { survey: tally } }).survey;
  assert.ok(parsed, "поле survey разобрано");
  return parsed;
}

/**
 * Разбор ленивый: при незакрытой задаче он падает, и падать он обязан ВНУТРИ
 * проверки. Разбор на уровне модуля обрывает файл целиком, и красный тест
 * сообщает одну строку вместо перечня невыполненных условий.
 */
let counted: SurveyView | null = null;
let below: SurveyView | null = null;
const COUNTED = () => (counted ??= view(FIXTURE.counted));
const BELOW = () => (below ??= view(FIXTURE.below_threshold));

function question(v: SurveyView, number: number) {
  const q = surveyQuestion(v, number);
  assert.ok(q, `вопрос ${number} есть в разборе`);
  return q;
}

// ─── Шкала ──────────────────────────────────────────────────────────────────

test("шкала приходит средним и долей верхних баллов", () => {
  const q = question(COUNTED(), 1);
  assert.equal(q.type, "scale");
  assert.equal(q.block, "b1");
  assert.equal(q.total.mean, 6.33);
  assert.equal(q.total.topBox, 0.3333);
  assert.equal(q.total.n, 3);
  assert.equal(q.total.base, 3);
});

test("у среза свои числа и свой размер", () => {
  // Колонка «14–35» у КАЖДОГО показателя — требование заказчика. Число без
  // размера среза не читается: доля по двум персонам и по сотне выглядят
  // одинаково.
  const q = question(COUNTED(), 1);
  assert.equal(q.target.mean, 8);
  assert.equal(q.target.n, 2);
  assert.equal(q.target.base, 2);
  assert.equal(q.target.belowThreshold, false);
});

test("группы шкалы сохраняют порядок писателя", () => {
  const q = question(COUNTED(), 15);
  assert.deepEqual(q.total.groups?.map((g) => g.id), ["9-10", "7-8", "0-6"]);
});

// ─── Выбор из списка ────────────────────────────────────────────────────────

test("доли по вариантам не теряют невыбранные", () => {
  // Исчезнувшая строка на графике читается как «такого варианта не предлагали».
  const q = question(COUNTED(), 8);
  assert.equal(q.total.options?.length, 19);
  const byId = new Map(q.total.options?.map((o) => [o.id, o]));
  assert.equal(byId.get("v-8")?.share, 0.6667);
  assert.equal(byId.get("v-8")?.count, 2);
  assert.equal(byId.get("v-2")?.share, 0);
});

test("выброшенные по форме ответы остаются видимыми", () => {
  const q = question(COUNTED(), 8);
  assert.equal(q.total.errors, 0, "ноль ошибок — это измеренный ноль, а не пусто");
});

// ─── Матрица ────────────────────────────────────────────────────────────────

test("матрица разбирается построчно и помнит тему", () => {
  const q = question(COUNTED(), 9);
  assert.equal(q.total.rows?.length, 2);
  const first = q.total.rows?.[0];
  assert.equal(first?.id, "t1-1");
  assert.equal(first?.themeId, "t1");
  assert.equal(first?.stats.options?.find((o) => o.id === "m-1")?.share, 0.6667);
});

// ─── Порог среза ────────────────────────────────────────────────────────────

test("срез ниже порога назван, а не показан нулями", () => {
  // Писатель убирает числа и оставляет размер. Ноль вместо `null` означал бы
  // «посчитали, вышло ноль» — то есть противоположное тому, что произошло.
  const scale = question(BELOW(), 1);
  assert.equal(scale.target.belowThreshold, true);
  assert.equal(scale.target.mean, null);
  assert.equal(scale.target.topBox, null);
  assert.equal(scale.target.n, 2, "размер среза остаётся");

  const choice = question(BELOW(), 8);
  assert.equal(choice.target.options, null, "долей нет, и это не пустой список");

  const matrix = question(BELOW(), 9);
  assert.equal(matrix.target.rows, null, "у подавленной матрицы строк нет вовсе");
});

test("индексы среза при подавлении не считаются", () => {
  assert.equal(BELOW().indices.nps.target, null);
  assert.equal(COUNTED().indices.nps.total, 0);
  assert.equal(COUNTED().indices.nps.target, 0.5);
  assert.equal(COUNTED().indices.perception.total, 0.6667);
  assert.equal(
    COUNTED().indices.satisfaction.total,
    null,
    "пяти критериев в анкете не было — индекс не считается вовсе",
  );
});

// ─── Открытый вопрос ────────────────────────────────────────────────────────

test("открытый вопрос доезжает числом ответов", () => {
  const q = question(COUNTED(), 16);
  assert.equal(q.type, "open");
  assert.equal(q.total.n, 2);
});

// ─── Состав аудитории ───────────────────────────────────────────────────────

test("состав аудитории приходит разрезами, а не одним числом", () => {
  assert.equal(COUNTED().audience.total, 3);
  assert.equal(COUNTED().audience.target, 2);
  assert.equal(COUNTED().audience.targetRange, "14–35");
  const city = COUNTED().audience.breakdowns.find((b) => b.key === "city");
  assert.deepEqual(city?.counts, [{ value: "Пермь", personas: 3 }]);
  assert.ok(
    COUNTED().audience.breakdowns.map((b) => b.key).includes("age_group"),
    "разрезы: пол, тип НП, город, возрастная группа",
  );
});

test("порог назван числом, а не подразумевается", () => {
  assert.equal(COUNTED().minSegment, 2);
  assert.equal(BELOW().minSegment, 20);
});

// ─── Отсутствие данных ──────────────────────────────────────────────────────

test("анкеты не было — это не пустая анкета", () => {
  assert.equal(parseReport({}).survey, null);
  assert.equal(parseReport({ aggregate: {} }).survey, null);
  assert.equal(parseReport({ aggregate: { survey: null } }).survey, null);
});

// ─── Подписи ────────────────────────────────────────────────────────────────

test("блоки заказчика приходят подписями из файла анкеты", () => {
  const blocks = surveyBlocks(COUNTED());
  const labels = new Map(SURVEY.blocks.map((b) => [b.id, b.label]));
  for (const block of blocks) {
    if (!labels.has(block.id)) continue;
    assert.equal(block.label, labels.get(block.id));
  }
  assert.deepEqual(
    blocks.map((b) => b.id),
    ["b1", "b2", "b3", "b5", "b6"],
    "порядок блоков — как в анкете, пустые блоки не рисуются",
  );
  assert.deepEqual(
    blocks.find((b) => b.id === "b1")?.questions.map((q) => q.number),
    [1, 15],
    "внутри блока вопросы идут по номеру",
  );
});

test("варианты получают подписи, а не идентификаторы", () => {
  const q = question(COUNTED(), 8);
  const rows = optionRows(q, q.total);
  const values = SURVEY.questions.find((s) => s.number === 8)?.options ?? [];
  assert.deepEqual(rows.map((r) => r.id), values.map((o) => o.id));
  assert.deepEqual(rows.map((r) => r.label), values.map((o) => o.label));
  assert.ok(rows.every((r) => r.known));
});

test("незнакомый вариант показывается идентификатором и назван незнакомым", () => {
  // Анкету можно дополнить своими вопросами, и подписей их вариантов в анкете
  // заказчика нет. Пропасть такая строка не должна: доля посчитана, и читатель
  // обязан увидеть, что подпись потерялась, а не строку целиком.
  const q = question(COUNTED(), 8);
  const rows = optionRows(q, {
    ...q.total,
    options: [{ id: "z-1", share: 0.5, count: 1 }],
  });
  const unknown = rows.find((row) => row.id === "z-1");
  assert.ok(unknown);
  assert.equal(unknown.label, "z-1");
  assert.equal(unknown.known, false);
});

test("строки матрицы получают подписи подтем", () => {
  const q = question(COUNTED(), 9);
  const rows = matrixRows(q, q.total);
  const spec = SURVEY.questions.find((s) => s.number === 9)?.rows ?? [];
  const byId = new Map(spec.map((r) => [r.id, r.label]));
  assert.equal(rows.length, 2);
  for (const row of rows) {
    assert.equal(row.label, byId.get(row.id));
    assert.ok(row.known);
  }
});

// ─── Колонка среза ──────────────────────────────────────────────────────────

test("колонка среза заполняется срезом, а не общим итогом", () => {
  // Самый дорогой промах этой секции: у подавленного среза вариантов нет
  // вовсе, и `target ?? total` подставил бы в колонку «14–35» числа всей
  // аудитории. На экране это неотличимо от посчитанного среза, который просто
  // совпал с общим итогом.
  const q = question(BELOW(), 8);
  const rows = optionPairs(q, q.total, q.target);
  assert.ok(rows.length > 0, "строки всей аудитории на месте");
  assert.ok(
    rows.every((r) => r.target === null),
    "ни одна доля среза не позаимствована у общего итога",
  );
  assert.equal(rows.find((r) => r.id === "v-8")?.total, 0.6667);
});

test("у подавленной матрицы срез пуст построчно", () => {
  const q = question(BELOW(), 9);
  const rows = matrixPairs(q, q.total, q.target);
  assert.ok(rows.length > 0, "строки подтем всей аудитории на месте");
  for (const row of rows) {
    assert.ok(
      row.options.every((o) => o.target === null),
      `строка ${row.id} взяла числа среза из общего итога`,
    );
  }
});

test("посчитанный срез в колонку доезжает", () => {
  // Обратная сторона: осторожность не должна превратиться в пустую колонку там,
  // где срез посчитан.
  const q = question(COUNTED(), 8);
  const rows = optionPairs(q, q.total, q.target);
  assert.equal(rows.find((r) => r.id === "v-8")?.target, 1.0);
  const matrix = question(COUNTED(), 9);
  const first = matrixPairs(matrix, matrix.total, matrix.target)[0];
  assert.equal(first.options.find((o) => o.id === "m-1")?.target, 1.0);
});

// ─── Экран ──────────────────────────────────────────────────────────────────

const body = code(read("components/agora/ReportBody.tsx"));

test("отчёт показывает блоки анкеты", () => {
  assert.ok(/surveyBlocks/.test(body), "тело отчёта группирует вопросы по блокам");
  assert.ok(
    /view\.survey/.test(body),
    "источник — разобранное поле survey, а не второй расчёт на экране",
  );
});

test("у каждого показателя стоит колонка среза с размером", () => {
  // Подпись среза берётся из данных (`targetRange`), а не пишется в разметке
  // строкой. Границы среза задаёт писатель — `TARGET_AGE` в survey_stats.py, —
  // и «14–35», набранное в TSX руками, стало бы второй копией этой константы:
  // изменив границы у писателя, мы получили бы экран, уверенно подписывающий
  // числа прежним диапазоном.
  assert.ok(!/["'>]14–35/.test(body), "диапазон не набран в разметке руками");
  assert.ok(/targetRange/.test(body), "подпись среза приходит из данных");
  assert.ok(
    /target\.n|surveySize/.test(body),
    "рядом с числом среза стоит его размер",
  );
});

test("неподсчитанное названо, а не показано нулём", () => {
  assert.ok(
    /belowThreshold/.test(body),
    "подавленный срез отмечается на экране",
  );
});

test("график ценностей в отчёте заменён ответами на вопрос 8", () => {
  // Решение владельца 17.09.2026: место графика ценностей занимает диаграмма
  // ответов на вопрос 8 — «какие ценности стремились донести создатели».
  // Разница существенная: график ценностей описывал СГЕНЕРИРОВАННУЮ аудиторию,
  // а вопрос 8 — то, что она увидела в материале.
  assert.ok(!/<ValuesChart/.test(body), "графика ценностей аудитории в отчёте нет");
  assert.ok(
    /SurveyValuesChart|surveyQuestion\(\s*view\.survey\s*,\s*8\s*\)/.test(body),
    "его место занял вопрос 8",
  );
});

test("сам компонент ValuesChart не удалён — он нужен реестру аудитории", () => {
  assert.ok(
    existsSync(join(WEB, "components/agora/ValuesChart.tsx")),
    "components/agora/ValuesChart.tsx на месте",
  );
});

// ─── Область публичной ссылки ───────────────────────────────────────────────

test("анкета не уходит в сводку по ссылке", () => {
  // В анкете лежат ответы персон, разобранные по вариантам, — это первичные
  // данные прогона. Граница та же, что у «Ответов персон» и «Материала».
  assert.equal(showsSection("full", "survey"), true);
  assert.equal(showsSection("aggregate", "survey"), false);
});
