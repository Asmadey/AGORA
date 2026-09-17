import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

/**
 * Состав снимка настроек, который уезжает в задачу.
 *
 * ─── Почему этот тест появился ───────────────────────────────────────────────
 * 17.09.2026 в настройки выведено число попыток пересоздания персоны. Разбор в
 * воркере написан, стык `tasks.py → validate_set` проверен разбором через `ast`,
 * все тесты зелёные — и настройка при этом не работала вовсе.
 *
 * Обрыв был здесь. `buildSettingsSnapshot` собирает снимок БЕЛЫМ СПИСКОМ: у
 * соседнего механизма есть `pickRequestionCap` и ключ во всех трёх ветках
 * возврата, а у нового не было ничего — воркер видел `raw is None` при любом
 * положении ползунка.
 *
 * То есть проверка на «ручку, которая ничего не крутит» стояла слоем НИЖЕ места
 * обрыва. Нашло это ревью диффа, обе модели независимо.
 *
 * ─── Почему по исходнику, а не прогоном ──────────────────────────────────────
 * `tasks.ts` импортирует через алиас `@/lib`, который node без сборщика не
 * разрешает, — потому тестов на него и не было ни одного. Разбор текста слабее
 * прогона и ловит ровно то, ради чего написан: ключ, забытый в белом списке.
 *
 * ─── Почему сравнение с соседом, а не список ключей ─────────────────────────
 * `requestionCap` — работающий образец: он объявлен, вычислен и разложен по всем
 * веткам. Требование «новый ключ встречается столько же раз» переживает правку
 * числа веток, а прибитый список — нет.
 */

const SOURCE = readFileSync(new URL("./tasks.ts", import.meta.url), "utf8");

function snapshotBody(): string {
  const start = SOURCE.indexOf("export async function buildSettingsSnapshot");
  assert.notEqual(start, -1, "функция buildSettingsSnapshot не найдена — тест устарел");
  const end = SOURCE.indexOf("\n}", start);
  assert.notEqual(end, -1, "не нашёл конец функции");
  return SOURCE.slice(start, end);
}

/** Сколько раз имя встречается в теле функции. */
function mentions(name: string): number {
  return snapshotBody().split(name).length - 1;
}

describe("снимок настроек задачи", () => {
  it("несёт число попыток пересоздания персоны", () => {
    assert.ok(
      mentions("personaAttempts") > 0,
      "personaAttempts нет в снимке: настройка не доедет до воркера и будет " +
        "выглядеть исправной — ползунок двигается, прогон считает по умолчанию",
    );
  });

  it("новый ключ разложен по всем веткам возврата, как и сосед", () => {
    // Веток три: без строки настроек, авто-кап и жёсткий кап. Добавить ключ
    // можно было в одну, и две другие молчали бы.
    assert.equal(
      mentions("personaAttempts"),
      mentions("requestionCap"),
      "personaAttempts встречается в снимке не столько же раз, сколько " +
        "requestionCap — значит какая-то из веток возврата его теряет",
    );
  });

  it("значение берётся из настроек, а не прибито числом", () => {
    assert.ok(
      /pickPersonaAttempts\(/.test(SOURCE),
      "нет функции чтения personaAttempts из provider_config",
    );
    assert.ok(
      /personaAttempts\?: unknown/.test(SOURCE),
      "чтение не разбирает jsonb как непроверенный вход: мусор из базы доедет до воркера",
    );
  });

  it("мусор в jsonb заменяется умолчанием", () => {
    // Поле пишет не только наш интерфейс, и дробное или строка в jsonb
    // возможны. Сосед проверяет Number.isInteger — новый обязан тоже.
    const pick = SOURCE.slice(SOURCE.indexOf("function pickPersonaAttempts"));
    assert.ok(
      /Number\.isInteger/.test(pick.slice(0, 400)),
      "pickPersonaAttempts не проверяет целочисленность",
    );
    assert.ok(
      /DEFAULT_SETTINGS\.personaAttempts/.test(pick.slice(0, 400)),
      "при мусоре не подставляется умолчание",
    );
  });
});
