import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

/**
 * Страницы прогона показывают текст целиком (две претензии владельца).
 *
 * ─── 1. Реплики обрезаны ──────────────────────────────────────────────────
 * Замерено в браузере 18.09.2026 на боевом, `/runs/0092`, окно 1512×792:
 *
 *     колонка речи ................ 182 px
 *     контейнер реплик ............ .block.max-h-24.space-y-1.overflow-hidden
 *     max-height (вычисленный) .... 96 px
 *     scrollHeight ................ 160 px
 *     clientHeight ................ 96 px
 *
 * То есть 64 px текста — около четырёх строк — отрезаны без единого признака
 * того, что они были. Из 14 размеченных ячеек обрезана была одна, и это не
 * «редкий случай»: обрезается ровно та ячейка, где речи много, то есть ровно
 * та, ради которой колонку и читают.
 *
 * Описание сцены обрезано тем же способом и так же молча: `line-clamp-3`.
 * Замер тем же заходом, клон без клампа против элемента с клампом:
 *
 *     «Сцена показывает группу солдат…» ... 120 px против 100 px
 *     «Мужчина в военной форме постепенно…» 100 px против  80 px
 *
 * Обе обрезки противоречат `lib/timeline-columns.ts`: пропорция колонок там
 * подбирается перебором так, чтобы СУММАРНАЯ ВЫСОТА ленты была наименьшей, и
 * высота каждой строки считается по ПОЛНОМУ тексту обеих колонок. Подобрать
 * ширину под текст, а потом отрезать текст по высоте — значит решать задачу и
 * выбрасывать её решение.
 *
 * Отрицательный отступ `-indent-2` при `pl-2` под подозрение попал, но
 * невиновен: это висячий отступ, он двигает первую строку на те же 8 px,
 * которые добавляет `pl-2`. Замер: `scrollWidth` 169 против `clientWidth`
 * 169 — по горизонтали не обрезано ничего.
 *
 * ─── 2. Markdown в чате не отрисован ──────────────────────────────────────
 * Модель отвечает разметкой, а `ChatView` кладёт ответ в
 * `<p className="whitespace-pre-wrap">{m.content}</p>`. На экране это выглядит
 * как звёздочки вокруг слов и точки с отступом вместо списка.
 */

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

const timeline = code(read("components/agora/Timeline.tsx"));
const chatView = code(read("components/agora/ChatView.tsx"));
const markdownView = code(read("components/agora/Markdown.tsx"));

// ─── 1. Ячейка ленты подстраивается под объём текста ────────────────────────

test("контейнер реплик не ограничен фиксированной высотой", () => {
  const speech = timeline.match(/className="[^"]*space-y-1[^"]*"/g) ?? [];
  assert.ok(speech.length > 0, "блок реплик должен найтись по space-y-1");
  for (const cls of speech) {
    assert.ok(
      !/\bmax-h-/.test(cls),
      `max-h- на блоке реплик режет текст по высоте: ${cls}`,
    );
    assert.ok(
      !/\boverflow-hidden\b/.test(cls),
      `overflow-hidden прячет то, что не поместилось, без единого признака: ${cls}`,
    );
  }
});

test("описание сцены не обрезано по числу строк", () => {
  assert.ok(
    !/line-clamp/.test(timeline),
    "line-clamp обрезает описание сцены так же молча, как max-h- обрезал речь; " +
      "ширину колонок подбирает timeline-columns.ts по полному тексту",
  );
});

// ─── 2. Чат отрисовывает markdown ───────────────────────────────────────────

test("ChatView рисует ответ через разбор markdown, а не сырым текстом", () => {
  assert.ok(
    /from "@\/lib\/markdown"|from "@\/components\/agora\/Markdown"/.test(chatView),
    "ответ модели должен проходить через разбор markdown",
  );
  assert.ok(
    /<Markdown\b/.test(chatView),
    "ответ ассистента рисуется компонентом Markdown",
  );
});

test("сырой текст остаётся только у реплики человека", () => {
  // Человек пишет обычным текстом, и его перенос строки сохраняется. Но
  // ответ модели в `whitespace-pre-wrap` — это ровно тот дефект, что чинится.
  const preWrap = chatView.match(/whitespace-pre-wrap/g) ?? [];
  assert.ok(
    preWrap.length <= 1,
    "whitespace-pre-wrap остаётся не более чем в одном месте — у реплики человека",
  );
  assert.ok(
    !/whitespace-pre-wrap[\s\S]{0,400}<Markdown/.test(chatView),
    "ответ модели не заворачивается в pre-wrap: markdown сам расставляет абзацы",
  );
});

test("разметка собирается React-узлами, без dangerouslySetInnerHTML", () => {
  assert.ok(markdownView.length > 0, "components/agora/Markdown.tsx должен существовать");
  for (const [name, src] of [
    ["Markdown.tsx", markdownView],
    ["ChatView.tsx", chatView],
  ] as const) {
    assert.ok(
      !/dangerouslySetInnerHTML/.test(src),
      `${name}: текст от модели нельзя вставлять как HTML`,
    );
  }
});

test("Markdown только рисует — разбор живёт в lib и покрыт тестами", () => {
  assert.ok(
    /from "@\/lib\/markdown"/.test(markdownView),
    "разбор берётся из lib/markdown: npm test собирает только lib/**",
  );
  assert.ok(
    !/replace\(\s*\/.*\*\*/.test(markdownView),
    "разбор разметки в компоненте — вторая реализация, которая разойдётся с первой",
  );
});
