import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { DEFAULT_SETTINGS, normalizeEndpoint, parseSettings } from "./settings.ts";

/**
 * Endpoint провайдера: что принимается, что чинится, а что отвергается.
 *
 * ─── Как это нашлось ─────────────────────────────────────────────────────────
 * Владелец подвинул один ползунок температуры, нажал «Сохранить» и получил
 * «endpoint: ожидается http(s)-адрес либо пусто». Поле endpoint он не трогал и
 * находится оно в другой секции экрана — связать отказ с ним было не с чем.
 *
 * Отказ целиком правильный: непустой endpoint обязан быть адресом. Неправильно
 * то, что адресом не считалось написанное без схемы — а именно так его и
 * копируют из документации провайдера и из `.env`. Человек, написавший
 * `foundation-models.api.cloud.ru/v1`, сообщил ровно то, что требовалось;
 * отвергать его значит требовать формы там, где смысл уже однозначен.
 *
 * ─── Где проходит граница ────────────────────────────────────────────────────
 * Дописывать `https://` ко всему подряд нельзя. В поле может оказаться то, чего
 * человек туда не писал (см. `settings-autofill`), и `https://` перед чужой
 * строкой превратит мусор в правдоподобный адрес, по которому прогон пойдёт
 * стучаться уже после расшифровки. Поэтому чинится только то, что похоже на
 * хост: с точкой, без пробелов и без `@`.
 */

const BASE = { ...DEFAULT_SETTINGS };

function endpointErrors(endpoint: string): string[] {
  const parsed = parseSettings({ ...BASE, endpoint });
  return parsed.ok ? [] : parsed.errors;
}

function endpointValue(endpoint: string): string {
  const parsed = parseSettings({ ...BASE, endpoint });
  assert.ok(parsed.ok, `ожидался разбор без ошибок, получено: ${JSON.stringify(parsed)}`);
  return parsed.value.endpoint;
}

describe("endpoint провайдера", () => {
  it("пустое значение законно — это «как в окружении сервера»", () => {
    assert.deepEqual(endpointErrors(""), []);
    assert.equal(endpointValue(""), "");
  });

  it("полный адрес проходит без изменений", () => {
    const url = "https://foundation-models.api.cloud.ru/v1";
    assert.equal(endpointValue(url), url);
  });

  it("адрес без схемы дописывается, а не отвергается", () => {
    assert.equal(
      endpointValue("foundation-models.api.cloud.ru/v1"),
      "https://foundation-models.api.cloud.ru/v1",
    );
  });

  it("кавычки вокруг значения снимаются", () => {
    // Ровно та беда, что описана в CLAUDE.md §9: значение переезжает из
    // .env.local вместе с кавычками, и адрес перестаёт быть адресом.
    assert.equal(
      endpointValue('"https://foundation-models.api.cloud.ru/v1"'),
      "https://foundation-models.api.cloud.ru/v1",
    );
  });

  it("почта не превращается в адрес, а отвергается", () => {
    // Менеджер паролей заполняет соседнее с паролем поле логином. Дописав сюда
    // «https://», мы сохранили бы чужую строку как рабочий endpoint — и прогон
    // пошёл бы стучаться по ней уже после оплаченной расшифровки.
    const errors = endpointErrors("user@example.com");
    assert.equal(errors.length, 1);
    assert.match(errors[0], /^endpoint:/);
  });

  it("строка с пробелами отвергается", () => {
    assert.equal(endpointErrors("не задан").length, 1);
  });

  it("нормализация вызывается напрямую — интерфейс проверяет тем же кодом", () => {
    // Интерфейс обязан показать претензию у поля, а не после отправки. Общая
    // функция — единственный способ, которым две проверки не разъедутся.
    assert.deepEqual(normalizeEndpoint("  cloud.ru/v1  "), {
      ok: true,
      value: "https://cloud.ru/v1",
    });
    assert.equal(normalizeEndpoint("user@example.com").ok, false);
  });
});

/**
 * ─── Потолок переспроса ────────────────────────────────────────────────────
 *
 * До 19.08 переспрос забракованных включался порогом в треть, зашитым в код.
 * На прогоне № 0050 забраковали 8 ответов из 27 — 29,6 %, ниже порога, — и
 * переспроса не было. Механизм отказывал ровно там, где он дёшев.
 *
 * Порог убран, вместо него потолок, и он принадлежит команде: у одной каждый
 * вызов на счету, у другой на счету достоверность отчёта.
 */
describe("потолок переспроса", () => {
  const base = {
    costCap: "auto",
    costCapValue: 500,
    whisperModel: "gigaam-v3-e2e-rnnt",
    defaultReplication: 1,
  };

  it("умолчание есть и оно не ноль", () => {
    assert.equal(typeof DEFAULT_SETTINGS.requestionCap, "number");
    assert.ok(DEFAULT_SETTINGS.requestionCap > 0);
  });

  it("значение принимается", () => {
    const parsed = parseSettings({ ...base, requestionCap: 5 });
    assert.ok(parsed.ok);
    if (parsed.ok) assert.equal(parsed.value.requestionCap, 5);
  });

  it("ноль законен — это «не переспрашивать»", () => {
    // Без нуля тот, кто считает вызовы, выключал бы QA целиком.
    const parsed = parseSettings({ ...base, requestionCap: 0 });
    assert.ok(parsed.ok);
    if (parsed.ok) assert.equal(parsed.value.requestionCap, 0);
  });

  it("отсутствие поля — это умолчание, а не отказ", () => {
    // Настройки, сохранённые до появления поля, не содержат его вовсе.
    const parsed = parseSettings(base);
    assert.ok(parsed.ok);
    if (parsed.ok) assert.equal(parsed.value.requestionCap, DEFAULT_SETTINGS.requestionCap);
  });

  it("отрицательное и дробное отвергаются с внятной претензией", () => {
    for (const bad of [-1, 1.5, "5", null]) {
      const parsed = parseSettings({ ...base, requestionCap: bad });
      assert.ok(!parsed.ok, `принято непригодное: ${JSON.stringify(bad)}`);
      if (!parsed.ok) assert.match(parsed.errors.join(" "), /requestionCap/);
    }
  });

  it("выше потолка воркера отвергается, а не обрезается", () => {
    // Обрезка означала бы, что человек видит в настройках одно, а прогон
    // исполняет другое. Граница та же, что в RequestionConfig.MAX.
    const parsed = parseSettings({ ...base, requestionCap: 101 });
    assert.ok(!parsed.ok);
  });
});
