import assert from "node:assert/strict";
import { test } from "node:test";

import { chatBudget, parseChatEvent, replyNote, type ChatFlags } from "./chat.ts";

const OK: ChatFlags = {
  grounded: true,
  insufficientData: false,
  outOfProfile: false,
  contradictsPrevious: false,
};

test("разбор потока", async (t) => {
  await t.test("кусок текста", () => {
    const e = parseChatEvent('data: {"delta":"Сегмент 45+ "}');
    assert.deepEqual(e, { kind: "delta", text: "Сегмент 45+ " });
  });

  await t.test("финал с флагами", () => {
    const e = parseChatEvent(
      'data: {"done":{"answer":"На 00:12 музыка","grounded":true,"insufficient_data":false}}',
    );
    assert.equal(e?.kind, "done");
    assert.equal(e && e.kind === "done" && e.flags.grounded, true);
  });

  await t.test("отказ доезжает до экрана", () => {
    // Молчащий поток неотличим от долгого ответа. Пользователь должен увидеть
    // причину, а не ждать вечно.
    const e = parseChatEvent('data: {"error":"TimeoutError: провайдер не ответил"}');
    assert.equal(e?.kind, "error");
  });

  await t.test("не-события пропускаются", () => {
    for (const line of ["", "   ", ": heartbeat", "event: ping", "retry: 1000"]) {
      assert.equal(parseChatEvent(line), null, `строка «${line}» разобрана как событие`);
    }
  });

  await t.test("битый JSON не роняет разбор", () => {
    // Один испорченный кусок не должен обрывать ответ, пришедший в остальном
    // целым.
    assert.equal(parseChatEvent("data: {не json"), null);
  });

  await t.test("отсутствие поля grounded читается как «не проверено»", () => {
    // Строгое умолчание: считать необоснованный ответ обоснованным опаснее,
    // чем наоборот. Весь продукт держится на том, что утверждение имеет опору.
    const e = parseChatEvent('data: {"done":{"answer":"текст"}}');
    assert.equal(e && e.kind === "done" && e.flags.grounded, false);
  });
});

test("бюджет реплик", async (t) => {
  await t.test("режим «авто» не ограничивает", () => {
    const b = chatBudget({ costCap: "auto", costCapValue: 500 }, 9999);
    assert.equal(b.allowed, true);
    assert.equal(b.limit, null);
  });

  await t.test("жёсткий кап считает реплики", () => {
    const b = chatBudget({ costCap: "hard", costCapValue: 10 }, 3);
    assert.equal(b.allowed, true);
    assert.equal(b.used, 3);
    assert.equal(b.limit, 10);
  });

  await t.test("исчерпанный кап запирает чат и объясняет почему", () => {
    const b = chatBudget({ costCap: "hard", costCapValue: 10 }, 10);
    assert.equal(b.allowed, false);
    assert.match(b.reason, /10 из 10/);
    // Пользователь должен узнать, где ручка, а не только что дверь закрыта.
    assert.match(b.reason, /Настройк/);
    // И что кап общий с прогоном — иначе непонятно, почему чат вообще платный.
    assert.match(b.reason, /общий с прогоном/);
  });

  await t.test("жёсткий кап без числа не запирает чат", () => {
    // Недонастройка — не запрет. Ноль или мусор в снимке иначе сделали бы чат
    // мёртвым без единого сообщения о причине.
    for (const value of [0, -5, Number.NaN, 1.5]) {
      const b = chatBudget({ costCap: "hard", costCapValue: value }, 0);
      assert.equal(b.allowed, true, `значение ${value} заперло чат`);
    }
  });
});

test("подпись под ответом", async (t) => {
  await t.test("обычный опорный ответ комментария не требует", () => {
    assert.equal(replyNote(OK, "analyst"), "");
  });

  await t.test("«данных нет» не выдаётся за дефект", () => {
    // Честное «в исследовании это не измерялось» — верный ответ, и ругать за
    // него отсутствием опоры значит наказывать за честность.
    const note = replyNote({ ...OK, insufficientData: true, grounded: false }, "analyst");
    assert.match(note, /данных нет/);
    assert.doesNotMatch(note, /без опоры/i);
  });

  await t.test("ответ без опоры назван прямо", () => {
    const note = replyNote({ ...OK, grounded: false }, "analyst");
    assert.match(note, /Без опоры/);
    assert.match(note, /Проверьте/);
  });

  await t.test("флаги персоны не показываются аналитику", () => {
    // out_of_profile у аналитика бессмыслен: у него нет профиля.
    assert.equal(replyNote({ ...OK, outOfProfile: true }, "analyst"), "");
  });

  await t.test("вопрос вне профиля персоны объяснён", () => {
    assert.match(replyNote({ ...OK, outOfProfile: true }, "persona"), /за пределами профиля/);
  });

  await t.test("расхождение с прежними ответами названо", () => {
    assert.match(replyNote({ ...OK, contradictsPrevious: true }, "persona"), /расходится/);
  });
});
