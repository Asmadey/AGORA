import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

/**
 * Порядок первой отрисовки: сначала каркас, потом содержимое.
 *
 * ─── Что было ─────────────────────────────────────────────────────────────
 * При обновлении страницы владелец видел обратный порядок: справа уже
 * нарисованы исследования, а левого меню ещё нет.
 *
 * Причина не в скорости. `AppShell` — клиентский компонент, и он прячет всё
 * меню за `useSession()`. Провайдер сессии заводился без начального значения,
 * поэтому на СЕРВЕРНОЙ отрисовке `status` равен "loading", `isAuthenticated`
 * ложно, и тега `<aside>` в отправленном HTML нет вовсе. Меню появляется не
 * «медленно», а после гидратации и сетевого похода за `/api/auth/session`.
 *
 * Содержимое при этом отдаётся сервером сразу — отсюда и порядок наоборот.
 *
 * ─── Почему тест смотрит на исходники ─────────────────────────────────────
 * Проверить порядок отрисовки без браузера нельзя, а браузер требует входа.
 * Но причина — структурная и видна в исходнике: провайдер без начальной
 * сессии означает меню вне серверного HTML при любых данных.
 */

const WEB = new URL("..", import.meta.url).pathname;
const APP = join(WEB, "app");

function read(p: string): string {
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}

/** Убирает комментарии: тест не должен ловить сам себя на объяснении. */
function code(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

test("меню попадает в серверный HTML", async (t) => {
  await t.test("провайдер сессии получает начальное значение", () => {
    const src = code(read(join(WEB, "components", "Providers.tsx")));
    assert.match(
      src,
      /<SessionProvider[^>]*\bsession=/,
      "SessionProvider без session: на сервере status='loading', и меню в HTML не попадает",
    );
  });

  await t.test("начальное значение берётся на сервере", () => {
    const src = code(read(join(APP, "layout.tsx")));
    assert.match(src, /\bauth\(\)/, "layout не спрашивает сессию у сервера");
    assert.match(src, /session=\{/, "сессия не передана в Providers");
  });

  await t.test("каркас остаётся серверным", () => {
    // Если layout станет клиентским, серверной отрисовки меню не будет
    // независимо от сессии.
    const src = read(join(APP, "layout.tsx"));
    assert.doesNotMatch(src, /^\s*["']use client["']/m, "layout стал клиентским");
  });
});

/** Разделы верхнего уровня — те, что перечислены в меню. */
function navSections(): string[] {
  const shell = read(join(WEB, "components", "AppShell.tsx"));
  const block = shell.slice(shell.indexOf("const NAV"), shell.indexOf("] as const"));
  return [...block.matchAll(/href:\s*"\/([^"/]+)"/g)].map((m) => m[1]);
}

test("ждущий раздел показывает свой скелетон", async (t) => {
  const sections = navSections();

  await t.test("меню разобрано", () => {
    assert.ok(sections.length >= 10, `разобрано разделов: ${sections.length}`);
  });

  await t.test("у каждого ждущего раздела есть собственный loading.tsx", () => {
    // Собственный, а не унаследованный от корня. Корневой запасной скелетон
    // может иметь форму только одного экрана, и для всех остальных он даёт
    // скачок вёрстки в тот момент, когда данные приехали, — то есть ровно
    // тогда, когда пользователь начал читать.
    const missing = sections.filter((s) => {
      const page = join(APP, s, "page.tsx");
      if (!existsSync(page)) return false;
      const waits = /export default async function/.test(read(page));
      return waits && !existsSync(join(APP, s, "loading.tsx"));
    });
    assert.deepEqual(missing, [], `разделы ждут данные без своего скелетона: ${missing}`);
  });
});

test("корневой скелетон — общий, а не форма одного экрана", async (t) => {
  await t.test("не называет себя списком прогонов", () => {
    // Файл писался, когда список прогонов жил на корне. Список уехал на
    // /researches, а скелетон остался и стал запасным для ВСЕХ разделов —
    // сохранив форму одного из них. Тот же класс дефекта, что и данные,
    // оставшиеся во вкладке: ничего не сломалось заметно.
    const src = read(join(APP, "loading.tsx"));
    assert.doesNotMatch(
      src,
      /списка прогонов/,
      "корневой скелетон описан как принадлежащий одному разделу",
    );
  });
});

test("скелетоны берутся из общего набора", async (t) => {
  await t.test("ни один loading.tsx не рисует свою анимацию", () => {
    // Иначе на разных экранах разный ритм мигания, и это читается как разная
    // скорость загрузки, а не как один продукт.
    const found: string[] = [];
    const walk = (dir: string) => {
      for (const e of readdirSync(dir)) {
        if (e === "node_modules" || e === ".next") continue;
        const full = join(dir, e);
        if (statSync(full).isDirectory()) walk(full);
        else if (e === "loading.tsx") {
          const src = code(read(full));
          if (/animate-pulse|animate-\[/.test(src)) found.push(full.slice(APP.length));
        }
      }
    };
    walk(APP);
    assert.deepEqual(found, [], `свои анимации вместо общих Skeleton*: ${found}`);
  });
});
