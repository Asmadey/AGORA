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
