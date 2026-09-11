import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

/**
 * «Персоны» и «Аудитории» слиты в один раздел.
 *
 * ─── Дублировали ли они друг друга ────────────────────────────────────────
 * Не полностью — и это важнее, чем кажется. `/audience` показывал НАБОРЫ,
 * `/personas` — все персоны арендатора вперемешку плюс `PersonaSetChips`,
 * то есть ВТОРОЙ список тех же наборов.
 *
 * Список наборов существовал в двух местах, а удаление набора — только в
 * плашках внутри `/personas`, то есть не в том разделе, который наборам и
 * посвящён. Раздел «Аудитории» показывал наборы и не давал с ними ничего
 * сделать.
 *
 * Плоский реестр при этом отвечал не на тот вопрос. Его собственный сосед
 * говорит об этом прямо: «Реестр /personas показывал всех персон арендатора
 * вперемешку, без разделения по наборам, поэтому ответа не было и там».
 *
 * ─── Что проверяется здесь ────────────────────────────────────────────────
 * Разметка и проводка: счётчики, форма подписи, куда ведут кнопки, каким
 * методом уходит удаление. Как это выглядит — проверяется глазами.
 */

const WEB = new URL("..", import.meta.url).pathname;

function read(rel: string): string {
  const p = join(WEB, rel);
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}

/** Без комментариев: тест не должен ловить себя на собственном объяснении. */
function code(src: string): string {
  return src
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

test("разделов стало один вместо двух", async (t) => {
  await t.test("в меню нет пункта «Персоны»", () => {
    const nav = code(read("components/AppShell.tsx"));
    const block = nav.slice(nav.indexOf("const NAV"), nav.indexOf("] as const"));
    assert.doesNotMatch(block, /href:\s*"\/personas"/, "пункт «Персоны» остался в меню");
    assert.match(block, /href:\s*"\/audience"/, "пункт «Аудитории» пропал из меню");
  });

  await t.test("старый адрес не ломается, а уводит на новый", () => {
    // По /personas ходят закладки и ссылки из переписки. Отдавать по нему 404
    // значило бы чинить дублирование ценой сломанных ссылок.
    const src = code(read("app/personas/page.tsx"));
    assert.match(src, /redirect\(\s*["']\/audience["']\s*\)/);
  });

  await t.test("адреса персоны и набора остались рабочими", () => {
    assert.ok(existsSync(join(WEB, "app/personas/[id]/page.tsx")));
    assert.ok(existsSync(join(WEB, "app/personas/sets/[id]/page.tsx")));
  });
});

test("раздел «Аудитории»: счётчики и карточки", async (t) => {
  const view = code(read("components/agora/AudienceRegistry.tsx"));

  await t.test("компонент заведён", () => {
    assert.notEqual(view, "", "components/agora/AudienceRegistry.tsx не найден");
  });

  await t.test("два счётчика", () => {
    assert.match(view, /Создано аудиторий/);
    assert.match(view, /Создано персон/);
  });

  await t.test("число персон без «из»", () => {
    // «12 из 12» отвечает на вопрос, которого не задавали, и заставляет
    // вычитать. Неполнота набора остаётся отдельной подписью.
    assert.doesNotMatch(view, /из \{s\.size\} персон/, "подпись всё ещё «N из M персон»");
    assert.match(view, /\{s\.personaCount\} персон/);
  });

  await t.test("выбор чекбоксом и удаление", () => {
    assert.match(view, /type="checkbox"/);
    assert.match(view, /Удалить/);
  });

  await t.test("удаление уходит в существующий маршрут", () => {
    // DELETE /api/audience уже написан и умеет отказывать по наборам,
    // использованным прогоном. Заводить второй маршрут значило бы иметь две
    // реализации одного правила.
    assert.match(view, /fetch\(\s*["']\/api\/audience["']/);
    assert.match(view, /method:\s*["']DELETE["']/);
  });

  await t.test("отказ по занятым наборам доезжает до экрана", () => {
    // Набор, на котором уже шёл прогон, не удаляется. Молчание в этом месте
    // читается как «кнопка не работает».
    assert.match(view, /blocked/);
  });

  await t.test("подвал карточки прижат к низу", () => {
    // Иначе предупреждение о неполном наборе сдвигает дату и ссылку вниз, и
    // в сетке они стоят на разной высоте — видно на скриншоте владельца.
    assert.match(view, /mt-auto/);
    assert.match(view, /flex-col/);
  });

  await t.test("переход в набор ведёт на страницу набора", () => {
    assert.match(view, /\/personas\/sets\//);
  });
});

test("страница набора", async (t) => {
  const page = code(read("app/personas/sets/[id]/page.tsx"));
  const criteria = code(read("components/agora/GenerationCriteria.tsx"));

  await t.test("возврат ведёт в «Аудитории»", () => {
    assert.match(page, /href=\{?["']\/audience["']/);
  });

  await t.test("критерии генерации свёрнуты по умолчанию", () => {
    assert.notEqual(criteria, "", "components/agora/GenerationCriteria.tsx не найден");
    assert.match(criteria, /useState\(\s*false\s*\)/);
    assert.match(criteria, /cursor-pointer text-sm font-semibold/);
  });

  await t.test("seed стоит первым в критериях", () => {
    assert.match(criteria, /seed/);
  });

  await t.test("у персоны есть отдельная кнопка перехода", () => {
    assert.match(page, /ArrowUpRight/);
  });

  await t.test("у персоны видно дату и автора", () => {
    assert.match(page, /Создана/);
    assert.match(page, /Создал/);
  });

  await t.test("чекбокса у персоны нет", () => {
    // Выбор оставлен только аудиториям: удаление персоны по одной ломает
    // набор, на котором считался отчёт, а удаление набора — осознанное действие.
    assert.doesNotMatch(page, /type="checkbox"/);
  });
});
