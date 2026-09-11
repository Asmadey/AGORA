import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

/**
 * Мусор, который некому найти.
 *
 * ─── Что накопилось ───────────────────────────────────────────────────────
 * На боевой базе 11.09.2026: 59 слепков корпуса без единой ссылки, 38
 * портретов на 19 сегментов, 864 кадра тридцати шести удалённых прогонов и
 * 11 роликов, которым не принадлежит ни один прогон. Три разные причины, и
 * ни одна не видна из интерфейса: экран показывает пусто, место занято.
 *
 * ─── Причина первая: дистилляция добавляла, а не обновляла ────────────────
 * `POST /api/portraits/distill` звал `createPortrait` для каждого сегмента.
 * Десять запусков — десять комплектов портретов на одни и те же сегменты.
 * Выбор между близнецами доставался случаю: `_load_portraits` брал того, кто
 * раньше попался. Сегмент — это ключ, а не метка, и запись по нему одна.
 *
 * ─── Причина вторая: слепок переживал свой набор ──────────────────────────
 * `persona_sets.corpus_snapshot_id` объявлен `ON DELETE SET NULL`: удаление
 * набора обнуляло ссылку и оставляло слепок. Найти его после этого нечем —
 * на него не ссылается уже ничто.
 *
 * Удалять слепок вместе с набором безопасно ровно потому, что `deletePersonaSets`
 * ОТКАЗЫВАЕТСЯ удалять набор, на который смотрит хоть один прогон: значит у
 * удаляемого набора нет отчёта, которому слепок был бы нужен для объяснения
 * «на ком это считали».
 *
 * ─── Причина третья: уборка за пределами Postgres не повторяется ──────────
 * `DELETE /api/tasks/{id}` убирает строку последней и честно пишет, что
 * отказ внешнего хранилища удаления не отменяет. Но после этого строки уже
 * нет, а значит некому и повторить: объект становится недостижим навсегда.
 * Отсюда сборщик, который ищет мусор по хранилищу, а не по строке.
 */

const WEB = new URL("..", import.meta.url).pathname;

function read(rel: string): string {
  const p = join(WEB, rel);
  return existsSync(p) ? readFileSync(p, "utf8") : "";
}

/** Без комментариев: тест не должен ловить себя на чужом объяснении. */
function code(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

// ─── Портрет сегмента один ──────────────────────────────────────────────────

test("дистилляция обновляет портрет сегмента, а не заводит новый", () => {
  const route = code(read("app/api/portraits/distill/route.ts"));
  assert.ok(route, "маршрут дистилляции существует");

  assert.ok(
    /upsertDistilledPortrait/.test(route),
    "маршрут зовёт upsertDistilledPortrait — иначе каждый запуск добавляет комплект",
  );
  assert.ok(
    !/\bcreatePortrait\s*\(/.test(route),
    "createPortrait в дистилляции больше не зовётся напрямую",
  );
});

test("upsert ищет портрет по сегменту и пишет версию", () => {
  const lib = code(read("lib/server/portraits.ts"));
  assert.ok(
    /export async function upsertDistilledPortrait/.test(lib),
    "upsertDistilledPortrait объявлен в серверном слое портретов",
  );

  const fn = lib.slice(lib.indexOf("export async function upsertDistilledPortrait"));
  assert.ok(
    /segment_key\s*=\s*\$/.test(fn),
    "поиск существующего идёт по segment_key, а не по имени: имя правят руками",
  );
  assert.ok(
    /audience_portrait_versions/.test(fn),
    "обновление пишет новую версию — история сегмента не теряется",
  );
  assert.ok(
    /'distilled'|"distilled"/.test(fn),
    "версия помечена редактором distilled, а не manual",
  );
});

test("сегмент без ключа в upsert не попадает", () => {
  const lib = code(read("lib/server/portraits.ts"));
  const fn = lib.slice(lib.indexOf("export async function upsertDistilledPortrait"));
  assert.ok(
    /segmentKey/.test(fn) && /throw|Error/.test(fn.slice(0, 1200)),
    "пустой segmentKey отвергается: без ключа обновлять нечего и матчить нечем",
  );
});

// ─── Слепок уходит вместе с набором ─────────────────────────────────────────

test("удаление набора уносит его слепок корпуса", () => {
  const lib = code(read("lib/server/personas.ts"));
  const fn = lib.slice(lib.indexOf("export async function deletePersonaSets"));
  assert.ok(fn, "deletePersonaSets на месте");

  assert.ok(
    /corpus_snapshots/.test(fn),
    "deletePersonaSets удаляет corpus_snapshots — иначе слепок переживёт набор навсегда",
  );
  assert.ok(
    /corpus_snapshot_id/.test(fn),
    "удаляются именно слепки удаляемых наборов, а не все подряд",
  );

  // Порядок, а не факт: важно, что АДРЕСА прочитаны до удаления наборов.
  // После удаления `ON DELETE SET NULL` обнулит ссылку, и списка не будет —
  // слепок останется, а найти его будет уже нечем.
  const readRefs = fn.search(/SELECT[^;]*corpus_snapshot_id/);
  const delSets = fn.indexOf("DELETE FROM persona_sets");
  const delSnaps = fn.indexOf("DELETE FROM corpus_snapshots");
  assert.ok(readRefs >= 0, "адреса слепков читаются запросом");
  assert.ok(delSnaps >= 0, "слепки удаляются");
  assert.ok(
    readRefs < delSets,
    "чтение адресов идёт ДО удаления наборов, иначе ссылка уже обнулена",
  );
  assert.ok(
    /NOT EXISTS/.test(fn.slice(delSnaps)),
    "слепок, на который смотрит уцелевший набор, не удаляется",
  );
});
