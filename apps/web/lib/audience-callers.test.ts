import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

/**
 * Кто заводит наборы персон.
 *
 * ─── Зачем файл ───────────────────────────────────────────────────────────
 * Владелец попросил убрать кнопку «Сгенерировать набор» из разделов
 * «Аудитории» и «Персоны» — и назвал ровно то опасение, ради которого этот
 * тест и написан: чтобы удаление не задело генерацию в визарде запуска.
 *
 * Опасение обоснованное. Конструктор на `/audience` и шаг «Аудитория» визарда
 * ходят в ОДИН маршрут `POST /api/audience`. Убирая конструктор, легко унести
 * с ним и маршрут — «его больше никто не зовёт», — а обнаружится это на
 * первом же запуске исследования, то есть после загрузки ролика.
 *
 * Поэтому проверка двусторонняя: убранного быть не должно, а оставшееся
 * обязано работать. Односторонняя («кнопки нет») прошла бы и на продукте, где
 * заодно вырезали визард.
 */

const WEB = new URL("..", import.meta.url).pathname;

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.tsx?$/.test(entry) && !entry.endsWith(".test.ts")) out.push(full);
  }
  return out;
}

/** Исходники экранов и компонентов — без маршрутов API и тестов. */
const sources = [...walk(join(WEB, "app")), ...walk(join(WEB, "components"))].filter(
  (f) => !f.includes(`${join("app", "api")}${""}`) && !/[\\/]route\.ts$/.test(f),
);

const read = (f: string) => readFileSync(f, "utf8");

/**
 * Код без комментариев.
 *
 * Искать по всему файлу нельзя: объяснение, почему кнопку убрали, содержит её
 * название, а маршрут `/api/audience` упоминается в комментариях сразу в
 * нескольких файлах. Проверка, срабатывающая на собственном объяснении,
 * заставляет писать код так, чтобы он нравился регулярке, — а не так, чтобы
 * он был понятен. Тот же урок уже был с проверкой на домен agora.studio.
 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}
const rel = (f: string) => f.slice(WEB.length).replace(/^\//, "");

test("генерация набора вызывается только оттуда, где она осталась", () => {
  const callers = sources.filter((f) => /fetch\(\s*["'`]\/api\/audience/.test(stripComments(read(f))));

  const allowed = ["components/agora/AudienceStep.tsx", "components/agora/PersonaSetChips.tsx"];
  assert.deepEqual(
    callers.map(rel).sort(),
    allowed.sort(),
    "список вызывающих генерацию набора изменился",
  );
});

test("шаг «Аудитория» визарда генерацию по-прежнему вызывает", () => {
  // Главная проверка второй части: удаление конструкторов не должно отрезать
  // визард. Без неё «кнопок нет» было бы зелёным и на сломанном продукте.
  const step = read(join(WEB, "components", "agora", "AudienceStep.tsx"));
  assert.match(step, /fetch\(\s*["'`]\/api\/audience["'`],\s*\{/, "визард не создаёт набор");
  assert.match(step, /method:\s*["'`]POST["'`]/, "визард не шлёт POST на /api/audience");
});

test("кнопки «Сгенерировать набор» больше нет", async (t) => {
  await t.test("в разделе «Аудитории» нет конструктора", () => {
    const page = read(join(WEB, "app", "audience", "page.tsx"));
    assert.doesNotMatch(page, /AudienceBuilder/, "страница всё ещё рисует конструктор");
  });

  await t.test("ни один экран не предлагает сгенерировать набор", () => {
    const offenders = sources
      .filter((f) => /Сгенерируйте|Сгенерировать набор/.test(stripComments(read(f))))
      .map(rel);
    assert.deepEqual(offenders, [], `кнопка или призыв остались в ${offenders.join(", ")}`);
  });
});
