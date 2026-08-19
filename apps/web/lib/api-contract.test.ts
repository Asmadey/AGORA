import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

/**
 * Контракт API: спецификация против кода, и роли против замысла.
 *
 * ─── Что здесь ловится ────────────────────────────────────────────────────
 * Два расхождения, каждое из которых не видно ни в ревью, ни в прогоне.
 *
 * ПЕРВОЕ: маршрут есть в коде и отсутствует в OpenAPI (или наоборот). Клиенты
 * строятся по спецификации; описанный и не существующий маршрут — это код,
 * который кто-то напишет и который никогда не сработает. Существующий и не
 * описанный — функция, о которой не знают.
 *
 * ВТОРОЕ: правка прав. `requireOwner` отличается от `requireSession` одним
 * словом, и замена одного другим не ломает ни один экран владельца — она
 * открывает участнику то, что должно быть закрыто. Заметить это можно, только
 * зайдя участником и попробовав.
 *
 * ─── Почему статически, а не вызовами ─────────────────────────────────────
 * Ролевая проверка вызовами требует двух живых учётных записей и поднятого
 * сервера. Она полезна и остаётся в плане, но она НЕ идёт в CI — то есть не
 * ловит регрессию в тот момент, когда её вносят. Эта ловит.
 */

const ROOT = new URL("..", import.meta.url).pathname;
const REPO = join(ROOT, "..", "..");

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (entry === "route.ts") out.push(full);
  }
  return out;
}

/** `app/api/tasks/[id]/report/route.ts` → `/api/tasks/{id}/report` */
function pathOf(file: string): string {
  return (
    "/" +
    file
      .slice(join(ROOT, "app").length + 1)
      .replace(/\/route\.ts$/, "")
      .split("/")
      .map((seg) => seg.replace(/^\[(?:\.{3})?(.+)\]$/, "{$1}"))
      .join("/")
  );
}

// Не только app/api: спецификация описывает и /api-docs/openapi, который
// лежит рядом. Обход только по app/api объявил бы его нереализованным.
const ROUTES = [
  ...walk(join(ROOT, "app", "api")),
  ...walk(join(ROOT, "app", "api-docs")),
].map((file) => ({
  file,
  rel: file.slice(ROOT.length),
  path: pathOf(file),
  src: readFileSync(file, "utf8"),
  methods: methodsOf(readFileSync(file, "utf8")),
}));

/**
 * Какие HTTP-методы экспортирует файл.
 *
 * Две формы, и обе законны. Обычная — `export async function GET`. Вторая —
 * `export const { GET, POST } = handlers` у Auth.js: маршрут реализован
 * библиотекой, и своей функции в файле нет. Первая редакция этого разбора
 * знала только первую форму и объявила вход нереализованным.
 */
function methodsOf(src: string): string[] {
  const verbs = ["GET", "POST", "PUT", "PATCH", "DELETE"];
  const found = new Set<string>();

  for (const m of src.matchAll(/export\s+async\s+function\s+(GET|POST|PUT|PATCH|DELETE)\b/g)) {
    found.add(m[1].toLowerCase());
  }
  for (const m of src.matchAll(/export\s+const\s*\{([^}]*)\}/g)) {
    for (const name of m[1].split(",").map((x) => x.trim())) {
      if (verbs.includes(name)) found.add(name.toLowerCase());
    }
  }
  return [...found];
}

const SPEC = JSON.parse(
  readFileSync(join(REPO, "packages", "shared", "openapi", "agora.openapi.json"), "utf8"),
) as { paths: Record<string, Record<string, unknown>> };

test("маршруты вообще нашлись", () => {
  assert.ok(ROUTES.length > 20, `найдено маршрутов: ${ROUTES.length}`);
  assert.ok(Object.keys(SPEC.paths).length > 20, "спецификация подозрительно пуста");
});

test("каждый маршрут кода описан в OpenAPI", () => {
  // Auth.js разворачивается в десяток служебных адресов и описывать их незачем:
  // спецификация описывает НАШ API, а не библиотеку аутентификации.
  const SKIP = ["/api/auth/{nextauth}"];

  const missing = ROUTES.filter((r) => !SKIP.includes(r.path))
    .filter((r) => !(r.path in SPEC.paths))
    .map((r) => r.path);

  assert.deepEqual(missing, [], `есть в коде, нет в OpenAPI: ${missing}`);
});

test("каждый метод из OpenAPI реализован", () => {
  const VERBS = new Set(["get", "post", "put", "patch", "delete"]);
  const byPath = new Map(ROUTES.map((r) => [r.path, r]));

  const missing: string[] = [];
  for (const [path, ops] of Object.entries(SPEC.paths)) {
    const route = byPath.get(path);
    if (!route) {
      missing.push(`${path} (маршрута нет вовсе)`);
      continue;
    }
    for (const verb of Object.keys(ops)) {
      if (!VERBS.has(verb)) continue;
      if (!route.methods.includes(verb)) missing.push(`${verb.toUpperCase()} ${path}`);
    }
  }

  assert.deepEqual(missing, [], `описано и не реализовано: ${missing}`);
});

/**
 * Маршруты, меняющие то, что действует на всю команду или на её состав.
 *
 * Список закрытый и живёт здесь намеренно. `requireOwner` отличается от
 * `requireSession` одним словом; замена не ломает ни один экран владельца и
 * открывает участнику то, что должно быть закрыто. Правка этого списка —
 * решение, которое обязано быть замечено на ревью.
 */
const OWNER_ONLY = [
  "app/api/settings/route.ts",
  "app/api/users/route.ts",
  "app/api/users/[id]/route.ts",
  "app/api/prompts/route.ts",
  "app/api/prompts/[key]/route.ts",
  "app/api/prompts/[key]/activate/route.ts",
];

test("права владельца не размениваются на права участника", () => {
  const downgraded = OWNER_ONLY.filter((rel) => {
    const route = ROUTES.find((r) => r.rel === rel);
    // Пропавший из списка файл — тоже сигнал: маршрут переименовали или убрали,
    // и права его преемника никто не проверил.
    if (!route) return true;
    return !/requireOwner\s*\(/.test(route.src);
  });

  assert.deepEqual(
    downgraded,
    [],
    `маршрут потерял requireOwner (или файл переехал): ${downgraded}. ` +
      `Это не ломает ни один экран владельца — оно открывает участнику то, ` +
      `что должно быть закрыто`,
  );
});

test("маршруты, меняющие данные, объявляют nodejs-рантайм", () => {
  // Edge-рантайм не тянет pg. Маршрут, попавший туда по умолчанию, падает не
  // при сборке, а при первом вызове — и падает одинаково для всех клиентов.
  const offenders = ROUTES.filter((r) => /client\.query\s*\(/.test(r.src))
    .filter((r) => !/runtime\s*=\s*["']nodejs["']/.test(r.src))
    .map((r) => r.rel);

  assert.deepEqual(offenders, [], `маршрут с запросом к базе без runtime=nodejs: ${offenders}`);
});

// ─── Содержимое схем, а не только форма двери ────────────────────────────────
//
// Проверки выше сверяют пути и методы. Спецификация при этом разъехалась с
// кодом и оставалась зелёной: в `Settings` было три поля из одиннадцати, одно
// из них — `aiModel`, которого в продукте нет вовсе. Клиенты строятся по
// спецификации, и поле, описанное неверно, — это код, который кто-то напишет и
// который не сработает.

import { DEFAULT_SETTINGS, WHISPER_MODELS } from "./settings.ts";

test("схема Settings описывает те же поля, что и продукт", () => {
  const schema = (SPEC as unknown as {
    components: { schemas: Record<string, { properties?: Record<string, unknown> }> };
  }).components.schemas.Settings;

  const described = Object.keys(schema.properties ?? {}).sort();
  // apiKeyMask отдаётся только на чтение и в схему входит; сам ключ — никогда.
  const actual = Object.keys(DEFAULT_SETTINGS).sort();

  const missing = actual.filter((k) => !described.includes(k));
  const extra = described.filter((k) => !actual.includes(k));

  assert.deepEqual(missing, [], `есть в продукте, нет в схеме: ${missing}`);
  assert.deepEqual(extra, [], `описано и не существует: ${extra}`);
});

test("каталог моделей в схеме совпадает с каталогом продукта", () => {
  const schema = (SPEC as unknown as {
    components: { schemas: Record<string, { properties?: Record<string, { enum?: string[] }> }> };
  }).components.schemas.Settings;

  const described = schema.properties?.whisperModel?.enum;
  assert.ok(described, "whisperModel описан свободной строкой — выбор не ограничен ничем");
  assert.deepEqual([...described].sort(), [...WHISPER_MODELS].sort());
});

test("статусы прогона в схеме совпадают с теми, что показывает список", () => {
  // CANCELLED появился вместе с отменой прогона и в схему не попал: клиент,
  // построенный по ней, на отменённом прогоне упадёт на разборе enum.
  const schema = (SPEC as unknown as {
    components: { schemas: Record<string, { properties?: Record<string, { enum?: string[] }> }> };
  }).components.schemas.LaunchedTask;

  const described = schema.properties?.status?.enum ?? [];
  for (const status of ["QUEUED", "RUNNING", "REPORT_READY", "FAILED", "CANCELLED"]) {
    assert.ok(described.includes(status), `статус ${status} не описан`);
  }
});
