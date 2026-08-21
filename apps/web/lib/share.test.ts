import assert from "node:assert/strict";
import { test } from "node:test";

import { shareUrl, ttlToExpiry, TTL_OPTIONS } from "./share.ts";
import { hashToken, newToken } from "./server/share-token.ts";

/**
 * Публичная ссылка на отчёт (#29).
 *
 * ─── Что было ───────────────────────────────────────────────────────────────
 * Диалог выдумывал токен ЧЕТЫРЬМЯ вызовами Math.random прямо в браузере и
 * показывал ссылку на `https://agora.studio/s/…` — домен, которого у продукта
 * нет. Ничего не сохранялось, отозвать было нечего, открыть — некуда.
 *
 * Со стороны это неотличимо от работающей функции: диалог открывается, срок
 * выбирается, ссылка копируется. Обнаружить можно было только отправив её
 * кому-нибудь.
 *
 * ─── Что требуется ──────────────────────────────────────────────────────────
 * Токен выпускает сервер и хранит только SHA-256 (схема так и заведена:
 * `report_shares.token_hash`, утечка дампа не даёт доступа). Адрес строится от
 * ТЕКУЩЕГО источника, а не от константы: продукт живёт на sslip.io, у него нет
 * постоянного домена, и вписанный в код домен разойдётся с ним снова.
 */

test("токен непредсказуем и достаточно длинный", () => {
  const a = newToken();
  const b = newToken();
  assert.notEqual(a, b);
  // 32 байта энтропии в base64url — 43 символа.
  assert.ok(a.length >= 32, `слишком короткий токен: ${a.length}`);
  assert.match(a, /^[A-Za-z0-9_-]+$/, "токен должен быть безопасен для адреса");
});

test("в базу уходит хеш, а не сам токен", () => {
  const token = newToken();
  const hash = hashToken(token);
  assert.notEqual(hash, token);
  assert.match(hash, /^[0-9a-f]{64}$/, "SHA-256 в hex — как ждёт app.current_share_token_hash()");
  assert.equal(hashToken(token), hash, "хеш обязан быть детерминированным");
});

test("хеш совпадает с тем, что считает Postgres", () => {
  // Значение выписано числом намеренно. Если реализация здесь разойдётся с
  // digest('sha256') в базе, ссылка перестанет открываться, а выглядеть это
  // будет как «токен не найден» — то есть как отозванная ссылка.
  assert.equal(
    hashToken("agora"),
    "f7070d57bbe5496e29249421e91572f46ac4c2b62953b7ea046fa3707b9e6b2a",
  );
  assert.equal(hashToken("").length, 64, "пустая строка тоже хешируется");
});

test("адрес строится от текущего источника", () => {
  assert.equal(
    shareUrl("https://agora.185-154-194-125.sslip.io", "abc"),
    "https://agora.185-154-194-125.sslip.io/s/abc",
  );
  assert.equal(shareUrl("http://localhost:3000/", "abc"), "http://localhost:3000/s/abc");
});

test("выдуманного домена в коде не осталось", async () => {
  const { readFile } = await import("node:fs/promises");
  const raw = await readFile(
    new URL("../components/agora/ShareDialog.tsx", import.meta.url),
    "utf8",
  );
  // Комментарии снимаются перед сверкой. Первая редакция этой проверки нашла
  // `agora.studio` в докстроке, ОПИСЫВАЮЩЕЙ починенный дефект, и объявила его
  // невылеченным. Парсер, читающий комментарии как код, врёт тем убедительнее,
  // чем подробнее написано объяснение — на этом же спотыкалась проверка
  // каталога моделей.
  const code = raw
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  assert.doesNotMatch(code, /agora\.studio/, "ссылка снова ведёт на несуществующий домен");
  assert.doesNotMatch(code, /Math\.random/, "токен снова выдумывается в браузере");
  assert.match(code, /fetch\(`\/api\/tasks\/\$\{runId\}\/share`/, "диалог не зовёт сервер");
});

test("сроки жизни переводятся в дату, «навсегда» остаётся пустым", () => {
  const now = new Date("2026-08-21T10:00:00Z");
  assert.equal(ttlToExpiry("7d", now)?.toISOString(), "2026-08-28T10:00:00.000Z");
  assert.equal(ttlToExpiry("24h", now)?.toISOString(), "2026-08-22T10:00:00.000Z");
  assert.equal(ttlToExpiry("never", now), null);
});

test("неизвестный срок не превращается в вечную ссылку", () => {
  // Тихий откат на «навсегда» — худший из возможных: опечатка в поле делает
  // ссылку бессрочной, и заметить это нечем.
  assert.throws(() => ttlToExpiry("77d" as never, new Date()));
});

test("все предложенные сроки разбираются", () => {
  for (const option of TTL_OPTIONS) {
    assert.doesNotThrow(() => ttlToExpiry(option.value, new Date()));
  }
});
