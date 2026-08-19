import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

/**
 * Изоляция арендаторов на уровне кода.
 *
 * ─── Почему это важнее контрактных и ролевых проверок ─────────────────────
 * Утечка между командами — единственный дефект в списке §2.3 плана, который
 * нельзя починить извинением. Всё остальное чинится следующим релизом.
 *
 * ─── Что именно проверяется ───────────────────────────────────────────────
 * Не сама RLS — её проверяет `evals/tests/test_task02_db_rls.py` на живом
 * Postgres (изоляция подтверждена 19.08.2026 на боевой базе). Здесь другое:
 * что код не ходит в базу МИМО механизма, который эту изоляцию включает.
 *
 * `withTenant` открывает транзакцию, переключается на роль `agora_app` и
 * ставит `app.tenant_id`. Политики сверяются именно с ним. Запрос, ушедший
 * мимо — через `getPool()` напрямую или через `withoutTenant`, — идёт от роли
 * владельца, для которой политик нет, и ведёт себя одним из двух способов:
 * либо возвращает ноль строк (и это выглядит потерей данных), либо, если
 * когда-нибудь `FORCE` снимут, возвращает ЧУЖИЕ строки.
 *
 * Такую ошибку не видно в ревью: `withoutTenant` и `withTenant` отличаются
 * тремя буквами и оба выглядят намеренными.
 */

const ROOT = new URL("..", import.meta.url).pathname;

/**
 * Единственные законные места без тенант-контекста — функции идентичности из
 * миграции 05: поиск пользователя при входе и список его команд. Тенанта в этот
 * момент ещё нет, узнать его неоткуда, и `SECURITY DEFINER` в базе даёт им
 * узкий доступ ровно к двум таблицам.
 *
 * Список закрытый. Добавление сюда — решение, которое обязано быть замечено на
 * ревью: именно поэтому оно требует правки теста, а не только кода.
 */
const ALLOWED_WITHOUT_TENANT = ["lib/server/auth.ts"];

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next" || entry.startsWith(".")) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) out.push(full);
  }
  return out;
}

const FILES = [join(ROOT, "app"), join(ROOT, "lib"), join(ROOT, "components")]
  .flatMap((dir) => {
    try {
      return walk(dir);
    } catch {
      return [];
    }
  })
  .map((path) => ({ path, rel: path.slice(ROOT.length), src: readFileSync(path, "utf8") }));

test("исходники вообще нашлись", () => {
  // Без этой проверки все остальные позеленели бы на пустом списке — и
  // молчали бы ровно тогда, когда сломан обход каталогов.
  assert.ok(FILES.length > 50, `найдено файлов: ${FILES.length}`);
});

test("никто не берёт пул соединений напрямую", () => {
  // getPool не экспортируется, но импорт `pg` в обход db.ts дал бы соединение
  // без роли и без тенант-контекста.
  const offenders = FILES.filter(
    (f) => f.rel !== "lib/server/db.ts" && /from\s+["']pg["']/.test(f.src) &&
      /new\s+Pool\s*\(/.test(f.src),
  ).map((f) => f.rel);

  assert.deepEqual(offenders, [], `пул создаётся мимо lib/server/db.ts: ${offenders}`);
});

test("withoutTenant зовут только функции идентичности", () => {
  const offenders = FILES.filter(
    (f) =>
      f.rel !== "lib/server/db.ts" &&
      !ALLOWED_WITHOUT_TENANT.includes(f.rel) &&
      /\bwithoutTenant\s*\(/.test(f.src),
  ).map((f) => f.rel);

  assert.deepEqual(
    offenders,
    [],
    `запрос без тенант-контекста вне разрешённого списка: ${offenders}. ` +
      `Такой запрос идёт от роли владельца, для которой политик нет: он либо ` +
      `вернёт ноль строк, либо — если FORCE когда-нибудь снимут — чужие`,
  );
});

test("каждый маршрут API проверяет сессию", () => {
  // Маршрут без requireSession/requireOwner отдаёт данные кому угодно. Health
  // и auth — публичные по назначению.
  const PUBLIC = ["app/api/health/route.ts", "app/api/auth/[...nextauth]/route.ts"];

  const routes = FILES.filter((f) => /^app\/api\/.*\/route\.ts$/.test(f.rel));
  assert.ok(routes.length > 20, `маршрутов найдено ${routes.length}`);

  const offenders = routes
    .filter((f) => !PUBLIC.includes(f.rel))
    .filter((f) => !/require(Session|Owner|Member)\s*\(/.test(f.src))
    .map((f) => f.rel);

  assert.deepEqual(offenders, [], `маршрут не проверяет сессию: ${offenders}`);
});

test("маршрут, читающий базу, делает это через withTenant", () => {
  const PUBLIC = ["app/api/health/route.ts", "app/api/auth/[...nextauth]/route.ts"];

  const offenders = FILES.filter((f) => /^app\/api\/.*\/route\.ts$/.test(f.rel))
    .filter((f) => !PUBLIC.includes(f.rel))
    // Маршрут «читает базу», если он вообще упоминает client.query или зовёт
    // что-то из lib/server, что её читает. Признак грубый намеренно: точный
    // разбор потребовал бы графа импортов, а грубый ловит то, ради чего писан.
    .filter((f) => /client\.query\s*\(/.test(f.src))
    .filter((f) => !/withTenant\s*\(/.test(f.src))
    .map((f) => f.rel);

  assert.deepEqual(
    offenders,
    [],
    `маршрут выполняет запрос без тенант-контекста: ${offenders}`,
  );
});

test("серверные действия тоже перечитывают сессию", () => {
  // Форма отправляется из браузера, и tenantId, полученный при отрисовке
  // страницы, к моменту отправки уже не доказательство: вкладка могла быть
  // открыта до выхода из учётной записи.
  const actions = FILES.filter((f) => /^app\/.*\/actions\.ts$/.test(f.rel));
  assert.ok(actions.length > 0, "файлов серверных действий не найдено");

  const offenders = actions
    .filter((f) => !/require(Session|Owner|Member)\s*\(/.test(f.src))
    .map((f) => f.rel);

  assert.deepEqual(offenders, [], `серверное действие не проверяет сессию: ${offenders}`);
});
