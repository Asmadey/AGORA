import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import {
  BASE_QUESTIONS,
  DEFAULT_QUESTIONS,
  MANDATORY_THEME_IDS,
  mandatoryThemeCountLabel,
  surveyComposition,
  toggleMandatoryTheme,
  withSelectedMandatoryThemes,
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

/** Экраны, чьи подписи описывают оператору состав анкеты. */
const SCREENS = {
  "surveys/new/page.tsx": readFileSync(join(ROOT, "app", "surveys", "new", "page.tsx"), "utf8"),
  "surveys/page.tsx": readFileSync(join(ROOT, "app", "surveys", "page.tsx"), "utf8"),
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

test("подпись чипа тем склоняется по числу выбранных тем", () => {
  assert.equal(mandatoryThemeCountLabel(0), "0 тем");
  assert.equal(mandatoryThemeCountLabel(1), "1 тема");
  assert.equal(mandatoryThemeCountLabel(2), "2 темы");
  assert.equal(mandatoryThemeCountLabel(5), "5 тем");
  assert.equal(mandatoryThemeCountLabel(10), "10 тем");
});

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

test("переключение тем сохраняет свои вопросы и меняет обязательные обеих матриц", () => {
  const mine = newQuestionDraft("q-mine");
  const result = withSelectedMandatoryThemes(withMandatory([mine], MANDATORY_THEME_IDS), ["t1"]);

  assert.equal(result.at(-1)?.id, "q-mine");
  assert.deepEqual(result.find((q) => q.number === 9)?.themes?.map((t) => t.id), ["t1"]);
  assert.ok(result.find((q) => q.number === 9)?.rows?.every((r) => r.themeId === "t1"));
  assert.ok(result.find((q) => q.number === 11)?.rows?.every((r) => r.themeId === "t1"));
});

test("переключение темы не позволяет получить нулевой набор", () => {
  assert.deepEqual(
    toggleMandatoryTheme(["t1"], "t1"),
    { selected: ["t1"], reason: "Нельзя снять последнюю тему." },
  );
  assert.deepEqual(toggleMandatoryTheme(["t1"], "t2"), { selected: ["t1", "t2"] });
  assert.deepEqual(toggleMandatoryTheme(["t1", "t2"], "t1"), { selected: ["t2"] });
});

test("конструктор показывает темы вопроса 9 чекбоксами и запрещает снять последнюю", () => {
  assert.match(
    BUILDER,
    /type="checkbox"[\s\S]*Тема/,
    "оператор должен выбирать темы целиком, а не редактировать скрытые строки вручную",
  );
  assert.match(
    BUILDER,
    /нельзя снять последнюю тему|хотя бы одну тему|выберите хотя бы одну тему/i,
    "нулевой набор тем должен быть объяснён оператору сразу в конструкторе",
  );
});

test("открытый вопрос предупреждает об отсутствии графика и текстовом блоке", () => {
  assert.match(BUILDER, /label: "Открытый"/);
  assert.match(BUILDER, /график не построится/i);
  assert.match(BUILDER, /текстовым блоком с темами и цитатами/i,
    "при выборе открытого типа оператор должен узнать формат отчёта до запуска");
});

test("подпись матрицы описывает несколько ответов внутри вопроса", () => {
  assert.doesNotMatch(
    BUILDER,
    /по одному варианту на каждую строку/,
    "устаревшая подпись обещает один ответ на строку вместо настройки каждого вопроса",
  );
  assert.match(BUILDER, /Сколько вариантов\?/);
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

test("анкету засевает только обязательный блок — ни один экран не берёт BASE_QUESTIONS", () => {
  /**
   * Проверка утверждает СВОЙСТВО, а не перечисляет известные формы засева.
   *
   * Первая её версия искала два конкретных шаблона — `useState<…>(BASE_QUESTIONS)`
   * и `questionsOf(…, BASE_QUESTIONS)`. Она была зелёной, а экран
   * `/surveys/new` показывал пять критериев вместо пятнадцати: третья точка
   * засева написана как `initialQuestions ?? BASE_QUESTIONS` и под оба шаблона
   * не подошла. Нашлось это глазами на боевом, а не тестом.
   *
   * Перечислять формы бессмысленно — их столько, сколько способов написать
   * значение по умолчанию. Поэтому здесь запрещён сам импорт: `BASE_QUESTIONS`
   * нужны ровно одному файлу — конструктору, который по ним считает, изменён
   * ли критерий, и восстанавливает исходный. Все остальные берут
   * `DEFAULT_QUESTIONS`.
   */
  const ALLOWED = new Set(["components/agora/SurveyBuilder.tsx"]);
  const offenders: string[] = [];

  const walk = (dir: string) => {
    for (const entry of readdirSync(join(ROOT, dir), { withFileTypes: true })) {
      const rel = `${dir}/${entry.name}`;
      if (entry.isDirectory()) {
        walk(rel);
      } else if (/\.tsx?$/.test(entry.name) && !entry.name.endsWith(".test.ts")) {
        const text = readFileSync(join(ROOT, rel), "utf8");
        if (text.includes("BASE_QUESTIONS") && !ALLOWED.has(rel)) offenders.push(rel);
      }
    }
  };
  walk("app");
  walk("components");

  assert.deepEqual(
    offenders,
    [],
    "эти экраны берут пять базовых критериев вместо обязательной анкеты: " +
      offenders.join(", "),
  );
});

test("экраны анкеты не обещают вопрос о доле просмотра", () => {
  /**
   * Доля просмотра убрана из обязательной анкеты решением владельца
   * 17.09.2026, а подписи на экранах продолжали её обещать. Текст — такая же
   * часть контракта с оператором, как и состав вопросов: по нему он решает,
   * нужно ли добавлять вопрос самому.
   */
  for (const [name, text] of Object.entries(SCREENS)) {
    assert.ok(
      !/доле просмотра|долей просмотра|вопросом о доле/.test(text),
      `${name} обещает вопрос о доле просмотра, которого в анкете больше нет`,
    );
  }
});

test("свежая анкета не показывает своих вопросов: их там нет", () => {
  /*
   * Владелец завёл анкету, не добавил ни одного своего вопроса — и увидел
   * плашку «10 своих».
   *
   * Счёт шёл по отсутствию `baseKey`. Пока обязательными были пять базовых
   * критериев, это совпадало со «своими». С пятнадцатью вопросами заказчика
   * `baseKey` несут только первые пять, и десять обязательных уехали в чужую
   * колонку.
   *
   * Проверка идёт по DEFAULT_QUESTIONS — ровно тому составу, который получает
   * новая анкета. На выдуманном списке из пяти вопросов дефект не проявился бы.
   */
  const fresh = surveyComposition(DEFAULT_QUESTIONS);

  assert.equal(fresh.total, 15, "новая анкета — пятнадцать вопросов заказчика");
  assert.equal(fresh.mandatory, 15, "все пятнадцать обязательные");
  assert.equal(fresh.custom, 0, "своих вопросов оператор не добавлял");

  assert.equal(
    DEFAULT_QUESTIONS.filter((q) => !q.baseKey).length,
    10,
    "прежний признак «нет baseKey» насчитал бы десять своих — он и врал",
  );
});

test("добавленный оператором вопрос считается своим, обязательные — нет", () => {
  const withOwn = surveyComposition([
    ...DEFAULT_QUESTIONS,
    { id: "own-1", label: "Свой вопрос", type: "open" } as (typeof DEFAULT_QUESTIONS)[number],
  ]);

  assert.equal(withOwn.total, 16);
  assert.equal(withOwn.mandatory, 15);
  assert.equal(withOwn.custom, 1, "плашка обязана появиться ровно теперь");
});

test("снятый базовый вопрос не превращает обязательные в свои", () => {
  /*
   * Прежняя причина, которая не отменяется: считать своё вычитанием длины
   * базового набора нельзя — базовый вопрос можно снять, и вычитание начинало
   * врать в другую сторону.
   */
  const withoutOneBase = DEFAULT_QUESTIONS.filter((q) => q.baseKey !== "music");
  const c = surveyComposition(withoutOneBase);

  assert.equal(c.total, 14);
  assert.equal(c.custom, 0, "снятый базовый — не свой вопрос");
});
