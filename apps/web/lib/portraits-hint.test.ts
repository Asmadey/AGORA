import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

/**
 * Подсказка у заголовка «Портреты аудиторий».
 *
 * ─── Зачем она ────────────────────────────────────────────────────────────
 * Раздел отвечает на вопрос, который по экрану не читается: портрет влияет на
 * то, КАК персона описана, а не на то, кто она. Без этого различия раздел
 * выглядит вторым местом, где задаётся состав аудитории, — и правка портрета
 * читается как правка выборки.
 *
 * Проверяется не текст дословно, а то, что названы факты, без которых
 * объяснение вводит в заблуждение сильнее, чем его отсутствие.
 */

const WEB = new URL("..", import.meta.url).pathname;
const read = (rel: string) => {
  const p = join(WEB, rel);
  return existsSync(p) ? readFileSync(p, "utf8") : "";
};
const code = (src: string) =>
  src.replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

test("подсказка стоит у заголовка и доступна", async (t) => {
  await t.test("компонент подсказки заведён", () => {
    assert.notEqual(read("components/agora/Hint.tsx"), "");
    assert.notEqual(read("components/agora/PortraitsHint.tsx"), "");
  });

  await t.test("встроена в заголовок раздела", () => {
    const page = code(read("app/portraits/page.tsx"));
    assert.match(page, /<PortraitsHint\s*\/>/);
    assert.match(page, /Портреты аудиторий/);
  });

  await t.test("открывается не только наведением", () => {
    // На сенсорном экране наводить нечем, с клавиатуры до подсказки по
    // наведению не добраться вовсе. Один onMouseEnter сделал бы объяснение
    // недоступным там, где оно нужнее всего.
    const hint = code(read("components/agora/Hint.tsx"));
    assert.match(hint, /onMouseEnter/);
    assert.match(hint, /onClick/);
    assert.match(hint, /onFocus/);
    assert.match(hint, /<button/);
  });

  await t.test("закрывается с клавиатуры", () => {
    assert.match(code(read("components/agora/Hint.tsx")), /Escape/);
  });
});

test("подсказка называет то, без чего вводит в заблуждение", async (t) => {
  const hint = code(read("components/agora/PortraitsHint.tsx"));

  await t.test("портрет влияет на описание, а не на состав", () => {
    assert.match(hint, /как персона описана, а не кто она/);
  });

  await t.test("ключ сегмента назван", () => {
    assert.match(hint, /возраст \| география \| пол/);
  });

  await t.test("отсутствующий портрет не подменяется похожим", () => {
    // Самый опасный для доверия пункт: подстановка чужого портрета выглядела
    // бы убедительно и была бы неотличима от верной.
    assert.match(hint, /пустая строка/);
    assert.match(hint, /ближайший похожий/);
  });

  await t.test("сказано, когда портрет применяется", () => {
    assert.match(hint, /шаг[еу] «Аудитория»/);
  });

  await t.test("сказано, что правка не трогает созданные аудитории", () => {
    // Без этого человек правит портрет и ждёт, что изменится готовый отчёт.
    assert.match(hint, /не меняет уже созданные/);
  });

  await t.test("назван запасной ключ для тонких сегментов", () => {
    assert.match(hint, /возраст \| гео/);
  });
});
