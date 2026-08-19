import assert from "node:assert/strict";
import { test } from "node:test";

import { readFileSync } from "node:fs";

// Файл читается напрямую, а не через lib/pipeline-nodes.ts: импорт JSON в
// node --test требует import attributes, которых у модуля нет — он собирается
// сборщиком Next.js. Проверяются всё равно ДАННЫЕ, а не обёртка над ними.
interface PipelineNode {
  name: string;
  label: string;
  detail: string;
  longOnly?: boolean;
}

const PIPELINE_NODES: PipelineNode[] = JSON.parse(
  readFileSync(
    new URL("../../../packages/shared/pipeline/nodes.json", import.meta.url),
    "utf8",
  ),
).nodes;

/**
 * Подписи узлов на экране прогресса.
 *
 * ─── Откуда взялась проверка ──────────────────────────────────────────────
 * Владелец сказал про узел «Расшифровка и спикеры»: «текст какой-то странный,
 * он не отражает суть заголовка». Там стояло:
 *
 *   «Whisper и pyannote одновременно, в двух потоках. По очереди они съедали
 *    473 секунды из восьмисот: параллельность по PRD §8 была структурной, а не
 *    временной»
 *
 * Три беды разом. Это описание не ШАГА, а истории его оптимизации. Оно вчетверо
 * длиннее остальных двенадцати. И оно перестало быть верным: с 19.08 узел
 * решает по свободной памяти, идти в два потока или по очереди.
 *
 * Подпись на экране отвечает на вопрос «что сейчас происходит», а не «почему
 * код написан так». Второе живёт в комментарии у кода и там полезно.
 */

test("узлов достаточно, чтобы проверка что-то значила", () => {
  assert.ok(PIPELINE_NODES.length >= 13, `узлов: ${PIPELINE_NODES.length}`);
});

test("подписи не превращаются в абзац", () => {
  // Порог с запасом к самой длинной из «нормальных» — он ловит не длину как
  // таковую, а смену жанра: развёрнутое объяснение вместо подписи.
  const long = PIPELINE_NODES.filter((n) => n.detail.length > 90).map(
    (n) => `${n.name} (${n.detail.length})`,
  );
  assert.deepEqual(long, [], `подпись стала абзацем: ${long}`);
});

test("подпись описывает шаг, а не историю его оптимизации", () => {
  // Ссылка на PRD и число из замера — признаки того, что в подпись переехал
  // комментарий из кода. Читателю экрана они не говорят ничего.
  const offenders = PIPELINE_NODES.filter(
    (n) => /PRD|§|\d{3,}\s*секунд/i.test(n.detail),
  ).map((n) => n.name);
  assert.deepEqual(offenders, [], `в подписи ссылка на PRD или замер: ${offenders}`);
});

test("подписи в одном жанре: одно предложение", () => {
  const multi = PIPELINE_NODES.filter((n) => /\.\s+[А-ЯA-Z]/.test(n.detail)).map(
    (n) => n.name,
  );
  assert.deepEqual(multi, [], `подпись из нескольких предложений: ${multi}`);
});

test("длинный режим добавляет ровно один узел", () => {
  const longOnly = PIPELINE_NODES.filter((n) => n.longOnly);
  assert.equal(longOnly.length, 1, `узлов только для длинного режима: ${longOnly.length}`);
});
