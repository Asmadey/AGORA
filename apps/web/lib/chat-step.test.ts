import assert from "node:assert/strict";
import { test } from "node:test";

import { parseChatEvent } from "./chat.ts";

/**
 * Ход инструментов доезжает до экрана.
 *
 * ─── Зачем ────────────────────────────────────────────────────────────────
 * При большом материале модель сначала ходит за сценами и речью, и только
 * потом пишет ответ. Раунды идут ДО первого слова: на сорокавосьмиминутном
 * ролике это несколько секунд молчания, которые читаются как зависание.
 *
 * Разбор, не знающий события `step`, вернул бы `null`, и ход пропал бы молча —
 * то есть ровно так же, как если бы его не было.
 */

test("ход инструментов разбирается", () => {
  const e = parseChatEvent('data: {"step":"смотрю сцены № 12, 13 (get_scenes)"}');
  assert.ok(e, "событие разобрано");
  assert.equal(e.kind, "step");
  assert.equal(e.kind === "step" && e.text, "смотрю сцены № 12, 13 (get_scenes)");
});

test("режим контекста разбирается", () => {
  // Переключение «целиком / оглавлением» объясняет разное поведение чата.
  // Молча переключившийся режим объяснял бы его ничем.
  const e = parseChatEvent('data: {"context_mode":"tools","context_tokens":170613}');
  assert.ok(e, "событие разобрано");
  assert.equal(e.kind, "mode");
  assert.equal(e.kind === "mode" && e.mode, "tools");
});

test("прежние события не сломаны", () => {
  const d = parseChatEvent('data: {"delta":"текст"}');
  assert.equal(d?.kind, "delta");

  const err = parseChatEvent('data: {"error":"беда"}');
  assert.equal(err?.kind, "error");

  const done = parseChatEvent(
    'data: {"done":{"answer":"итог","grounded":true,"citations":[]}}',
  );
  assert.equal(done?.kind, "done");
});
