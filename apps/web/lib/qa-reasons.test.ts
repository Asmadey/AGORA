import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { parseAnswer, qaKindLabel } from "./report-view.ts";

/**
 * Замечания QA доезжают до экрана словами, а не словом «regenerate».
 *
 * ─── Что было ─────────────────────────────────────────────────────────────
 * Воркер кладёт в `report_personas[].qa_flags[]` объекты с полем `reasons` —
 * СПИСКОМ причин. Читатель отчёта спрашивал `f.reason` (единственное число),
 * получал `undefined` и падал на запасной путь `?? str(f.verdict)`. У всех
 * забракованных ответов `verdict` один и тот же — `"regenerate"`, — поэтому на
 * экране во всех 25 подсказках прогона 0091 стояло «QA: regenerate».
 *
 * Дефект прожил незамеченным именно из-за запасного пути: без него значок был
 * бы пустым, и пустоту заметили бы в первый день. Запасной путь превратил
 * промах в правдоподобный шум — это ровно тот класс дефектов, который в этом
 * проекте уже стоил нескольких проходов.
 *
 * ─── Что проверяем ────────────────────────────────────────────────────────
 * 1. Форма документа — настоящая, снятая с боевого прогона 0091, а не
 *    придуманная. Тест на выдуманной форме проверял бы согласие автора с самим
 *    собой, а разошлись здесь именно писатель и читатель.
 * 2. Слово `verdict` в причины не подставляется НИКОГДА: «regenerate» — это
 *    решение системы, а не объяснение, и на экране оно не значило ничего.
 * 3. Замечание доезжает целиком: вид проверки и уверенность нужны, чтобы
 *    отличить придирку судьи с 0.70 от ошибки таймкода с 0.95.
 * 4. Замечание без причин не исчезает: исчезнувший флаг делает забракованный
 *    ответ похожим на чистый, и число «исключено QA» перестаёт сходиться.
 */

/** Настоящий флаг прогона 0091 (сокращён по длине текста, поля — как в базе). */
const REAL_FLAG = {
  kind: "grounding",
  persona_id: "64d65635-3e9c-49e8-a646-494d88354077",
  persona_name: "Алексей",
  replication: 0,
  verdict: "regenerate",
  confidence: 0.95,
  reasons: [
    "Персона ссылается на сцену с молитвой и отступничеством в таймкоде " +
      "4:05–4:18. В материале в этом таймкоде священнослужитель читает молитву, " +
      "но нет ни сцены отступничества, ни упоминания Саблиной.",
  ],
  source: "judge",
  escalated: false,
};

function answerWith(flags: Record<string, unknown>[]) {
  return parseAnswer({
    personaId: "64d65635-3e9c-49e8-a646-494d88354077",
    personaName: "Алексей",
    replication: 0,
    segment: {},
    answer: {},
    qaFlags: flags,
  });
}

test("причина приезжает текстом из reasons, а не словом regenerate", () => {
  const a = answerWith([REAL_FLAG]);

  assert.equal(a.qaFlags.length, 1, "флаг не потерян");
  assert.deepEqual(
    a.qaFlags[0].reasons,
    REAL_FLAG.reasons,
    "причины берутся из поля reasons целиком и в том же порядке",
  );

  const shown = JSON.stringify(a.qaFlags);
  assert.ok(
    !shown.includes("regenerate"),
    `вердикт на экран не идёт, а он там: ${shown.slice(0, 200)}`,
  );
});

test("вид проверки и уверенность сохраняются", () => {
  const a = answerWith([REAL_FLAG]);
  assert.equal(a.qaFlags[0].kind, "grounding");
  assert.equal(a.qaFlags[0].confidence, 0.95);
});

test("несколько причин у одного флага показываются все", () => {
  // На прогоне 0091 у 33 флагов 66 причин: судья часто называет две сразу,
  // и первая из них — не всегда главная.
  const a = answerWith([{ ...REAL_FLAG, reasons: ["первая", "вторая"] }]);
  assert.deepEqual(a.qaFlags[0].reasons, ["первая", "вторая"]);
});

test("флаг без причин остаётся флагом, а не исчезает", () => {
  // Прежний разбор выбрасывал такой флаг целиком. Забракованный ответ после
  // этого выглядел чистым, и «исключено QA» в шапке не сходилось с экраном.
  const a = answerWith([{ ...REAL_FLAG, reasons: [] }]);
  assert.equal(a.qaFlags.length, 1);
  assert.deepEqual(a.qaFlags[0].reasons, []);
});

test("мусор вместо флага не роняет разбор", () => {
  const a = answerWith([{ kind: 42, confidence: "много", reasons: "не массив" }]);
  assert.equal(a.qaFlags.length, 1);
  assert.deepEqual(a.qaFlags[0].reasons, []);
  assert.equal(a.qaFlags[0].confidence, null);
  assert.ok(a.qaFlags[0].kind.length > 0, "вид проверки не пустая строка");
});

test("вид проверки переводится, а незнакомый показывается как есть", () => {
  assert.equal(qaKindLabel("consistency"), "Согласованность");
  assert.equal(qaKindLabel("grounding"), "Опора на материал");
  // Судья может завести новый вид раньше, чем сюда допишут подпись. Пропасть
  // он при этом не должен: незнакомое имя честнее пустоты.
  assert.equal(qaKindLabel("tone"), "tone");
});

// ─── Разметка ───────────────────────────────────────────────────────────────

const WEB = new URL("..", import.meta.url).pathname;

function read(rel: string): string {
  const p = join(WEB, rel);
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}

/** Без комментариев: разбор идёт по коду, а не по его объяснению. */
function code(text: string): string {
  return text
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

const accordion = code(read("components/agora/PersonaAccordion.tsx"));
const panel = code(read("components/agora/QaFlags.tsx"));

test("значок QA — кнопка с панелью, а не мёртвый title", () => {
  assert.ok(panel, "components/agora/QaFlags.tsx существует");
  assert.ok(
    /<button/.test(panel),
    "значок открывается нажатием: на сенсорном экране навести нечем",
  );
  assert.ok(
    /onMouseEnter/.test(panel),
    "и наведением тоже — владелец просил «навести ИЛИ нажать»",
  );
  assert.ok(
    /Escape/.test(panel) || /useDismissable/.test(panel),
    "панель закрывается Escape и щелчком мимо",
  );
});

test("щелчок мимо считается мимо ВСЕГО значка, а не только панели", () => {
  // Кнопка стоит снаружи панели. Если область «внутри» — только панель, то
  // нажатие ради закрытия ловится сначала как щелчок мимо (панель
  // закрывается), а следом собственным обработчиком — и открывается обратно.
  // Кнопка при этом выглядит сломанной, хотя срабатывает дважды.
  const wrapper = /<span\s+ref=\{box\}/.test(panel);
  assert.ok(wrapper, "ссылка на закрытие висит на обёртке, а не на панели");
  assert.ok(
    !/<div\s+ref=\{box\}/.test(panel),
    "на самой панели ссылки нет — иначе кнопка окажется «снаружи»",
  );
});

test("значок не глотается строкой аккордеона", () => {
  // Вся строка — role=button, раскрывающий карточку. Нажатие на значок без
  // stopPropagation раскрыло бы карточку вместо показа причин.
  assert.ok(
    /stopPropagation/.test(panel),
    "нажатие на значок не доходит до обработчика строки",
  );
});

test("аккордеон печатает причины, а не одно поле флага", () => {
  assert.ok(
    /QaFlags|QaFlagsBadge/.test(accordion),
    "разметка значка вынесена в отдельный компонент и используется здесь",
  );
  assert.ok(
    !/title=\{`QA:/.test(accordion),
    "прежний мёртвый title убран: он показывал «QA: regenerate»",
  );
  assert.ok(
    !/\{a\.qaFlags\.join\(/.test(accordion),
    "флаг больше не строка, join по нему собрал бы [object Object]",
  );
  assert.ok(
    /reasons/.test(accordion) || /reasons/.test(panel),
    "на экран идут причины",
  );
});

test("значок виден и на узком экране", () => {
  // Раньше значок стоял с `hidden … sm:inline-flex`: причина забраковки
  // пропадала на телефоне целиком. Это не украшение для широких экранов.
  const badge = /<QaFlags[\s\S]{0,400}?\/>/.exec(accordion)?.[0] ?? "";
  assert.ok(badge, "значок вставлен как <QaFlags .../>");
  assert.ok(
    !/\bhidden\b/.test(badge),
    `значок не прячется по ширине: ${badge.replace(/\s+/g, " ").slice(0, 200)}`,
  );
});
