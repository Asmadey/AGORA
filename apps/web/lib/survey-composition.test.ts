import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import {
  BASE_QUESTIONS,
  DEFAULT_QUESTIONS,
  MANDATORY_THEME_IDS,
  groundingIssues,
  isMandatory,
  newQuestionDraft,
  withMandatory,
} from "./survey-composition.ts";

/**
 * Состав анкеты живёт в одном месте, и проверка читает его же.
 *
 * ─── Дефект, который эта проверка закрывает ────────────────────────────────
 * Базовым критериям решением владельца от 17.09.2026 запрещена любая шкала,
 * кроме 0–10. Константы `BASE_QUESTIONS` перевели, схему перевели, валидатор
 * перевели, промпт перевели. А проверку в самом конструкторе — нет:
 *
 *     base.some((q) => q.type !== "scale" || q.scaleMin !== 1 || q.scaleMax !== 10)
 *
 * Читатель остался на 1–10, писатель ушёл на 0–10. Никакой ошибки при этом не
 * возникает: у оператора просто на ЛЮБОЙ правильной анкете горит предупреждение
 * «заземление сломано», а кнопка восстановления предлагает вернуть то, что и так
 * стоит. Отказ выглядит придиркой интерфейса, а не расхождением констант.
 *
 * Это пятый случай в этом репозитории, когда писатель и читатель разошлись по
 * литералу. Поэтому здесь закрывается не конкретное число, а сама возможность
 * завести его копию: проверка сверяет шкалу с той, что объявлена у базовых
 * вопросов, и отдельно следит, чтобы в компоненте не появилось числовых
 * литералов шкалы.
 */

const ROOT = join(import.meta.dirname, "..");
const BUILDER = readFileSync(
  join(ROOT, "components", "agora", "SurveyBuilder.tsx"),
  "utf8",
);
const SURVEY_FILE = JSON.parse(
  readFileSync(join(ROOT, "..", "..", "data", "survey", "customer_2026.json"), "utf8"),
) as { questions: { baseKey?: string; scaleMin?: number; scaleMax?: number }[] };

/** Места, где анкета заводится с нуля, — их засев обязан быть обязательным блоком. */
const SEEDS = {
  "studies/new/page.tsx": readFileSync(join(ROOT, "app", "studies", "new", "page.tsx"), "utf8"),
  "SurveyPicker.tsx": readFileSync(join(ROOT, "components", "agora", "SurveyPicker.tsx"), "utf8"),
};

test("базовые вопросы в исходном виде проходят проверку заземления", () => {
  assert.deepEqual(
    groundingIssues(BASE_QUESTIONS),
    [],
    "конструктор считает сломанной анкету, которую сам же и предлагает — " +
      "значит проверка сверяется не с базовыми вопросами, а с копией их шкалы",
  );
});

test("новый вопрос создаётся на той же шкале, что и базовые", () => {
  const draft = newQuestionDraft("q-test");
  const base = BASE_QUESTIONS[0];

  assert.equal(draft.scaleMin, base.scaleMin);
  assert.equal(draft.scaleMax, base.scaleMax);
});

test("шкала базовых вопросов совпадает с анкетой заказчика", () => {
  for (const base of BASE_QUESTIONS) {
    const shipped = SURVEY_FILE.questions.find((q) => q.baseKey === base.baseKey);
    assert.ok(shipped, `в анкете заказчика нет базового критерия ${base.baseKey}`);
    assert.equal(
      shipped.scaleMin,
      base.scaleMin,
      `нижняя граница ${base.baseKey} разошлась с анкетой заказчика`,
    );
    assert.equal(
      shipped.scaleMax,
      base.scaleMax,
      `верхняя граница ${base.baseKey} разошлась с анкетой заказчика`,
    );
  }
});

test("заземление ломается, когда базовый критерий действительно испорчен", () => {
  const broken = BASE_QUESTIONS.map((q, i) =>
    i === 0 ? { ...q, scaleMax: (q.scaleMax ?? 0) + 1 } : q,
  );
  assert.notDeepEqual(groundingIssues(broken), []);

  const withoutOne = BASE_QUESTIONS.slice(1);
  assert.notDeepEqual(groundingIssues(withoutOne), []);
});

test("в конструкторе не осталось числовых литералов шкалы", () => {
  const literal = /scale(?:Min|Max)\s*(?:[!=]==?|:)\s*-?\d+/g;
  const found = BUILDER.match(literal) ?? [];

  assert.deepEqual(
    found,
    [],
    "числа шкалы вернулись в SurveyBuilder.tsx: " +
      found.join(", ") +
      ". Состав анкеты объявляется в lib/survey-composition.ts, " +
      "иначе копия снова разойдётся с оригиналом",
  );
});

test("конструктор не называет шкалу числами в тексте на экране", () => {
  /**
   * Прозу типы не охраняют. Экран объяснял оператору, почему важна «шкала 1–10»,
   * ещё полдня после того, как константы ушли на 0–10, — и это ровно тот текст,
   * по которому оператор решает, можно ли трогать критерий.
   */
  const spelled = /\b\d{1,2}\s*[–—-]\s*10\b/g;
  const found = BUILDER.match(spelled) ?? [];

  assert.deepEqual(
    found,
    [],
    "подпись шкалы вписана в текст конструктора: " +
      found.join(", ") +
      ". Берите её из BASE_SCALE_LABEL — тогда текст не переживёт смену шкалы",
  );
});

// ─── Обязательный блок заказчика ──────────────────────────────────────────

test("анкета по умолчанию — это пятнадцать обязательных вопросов заказчика", () => {
  const numbers = DEFAULT_QUESTIONS.map((q) => q.number);

  assert.deepEqual(
    numbers,
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    "конструктор начинает не с обязательной анкеты — оператор соберёт исследование, " +
      "в котором заказчику не задали его собственные вопросы",
  );
  assert.deepEqual(
    groundingIssues(DEFAULT_QUESTIONS),
    [],
    "обязательный блок несёт все пять базовых критериев, заземление обязано быть целым",
  );
});

test("свои вопросы оператора идут после обязательных", () => {
  const mine = newQuestionDraft("q-mine");
  const composed = withMandatory([mine], MANDATORY_THEME_IDS);

  assert.equal(composed.length, DEFAULT_QUESTIONS.length + 1);
  assert.equal(composed.at(-1)?.id, "q-mine");
  assert.ok(
    composed.slice(0, -1).every((q) => isMandatory(q)),
    "обязательные вопросы перемешались со своими",
  );
});

test("невыбранная тема убирает свои строки из обеих матриц", () => {
  const one = withMandatory([], ["t1"]);
  const matrix = one.find((q) => q.number === 9);
  const impact = one.find((q) => q.number === 11);

  assert.ok(matrix?.rows && matrix.rows.length > 0);
  assert.ok(
    matrix.rows.every((r) => r.themeId === "t1"),
    "в матрице остались строки невыбранных тем",
  );
  assert.ok(
    impact?.rows?.every((r) => r.themeId === "t1"),
    "зависимый вопрос 11 не пошёл за выбором тем — интегральный показатель " +
      "восприятия считался бы по разному числу строк и стал бы несравним",
  );
});

test("обязательная анкета целиком проходит валидатор", async () => {
  const { validateSurvey } = await import("./server/survey-validator.ts");
  const result = validateSurvey({ name: "Обязательная", questions: DEFAULT_QUESTIONS });

  assert.deepEqual(
    result.errors,
    [],
    "конструктор предлагает анкету, которую сервер откажется сохранять",
  );
  assert.equal(result.valid, true);
});

test("конструктор больше не начинает с голых базовых критериев", () => {
  for (const [name, text] of Object.entries(SEEDS)) {
    assert.ok(
      !/useState<SurveyQuestion\[\]>\(BASE_QUESTIONS\)|questionsOf\([^)]*BASE_QUESTIONS\)/.test(text),
      `${name} всё ещё засевает анкету пятью базовыми критериями вместо ` +
        "обязательного блока заказчика",
    );
  }
});
