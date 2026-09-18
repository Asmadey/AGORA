import type { NodeState } from "./progress-state";

/**
 * Создание персон как видимый этап прогресса.
 *
 * ─── Зачем ───────────────────────────────────────────────────────────────────
 * Владелец выбирает «создать 100 персон» и сразу запускает исследование. Шкала
 * прогресса при этом начинается с «Разбор файла» и стоит на нём ноль секунд:
 * воркер один, и прогон честно ждёт в очереди, пока та же машина дописывает
 * аудиторию. Снаружи это выглядит зависшим интерфейсом — притом что работа идёт
 * и её видно в базе («40 из 100»).
 *
 * ─── Почему этап не добавлен в nodes.json ───────────────────────────────────
 * `packages/shared/pipeline/nodes.json` — контракт узлов графа воркера, общий с
 * `agent_core/pipeline/graph.py`. Создание персон в этот граф не входит: это
 * отдельная задача Celery (`agora.generate_audience`) над отдельной строкой
 * `persona_sets`, и один и тот же набор обслуживает много прогонов. Строка,
 * добавленная в nodes.json, обязала бы воркер присылать по ней события, которых
 * у него нет, — и шкала показывала бы вечно незакрытый первый шаг.
 *
 * Поэтому этап синтетический: он приходит отдельным пропом из Postgres и
 * приставляется к списку узлов на экране, а не в контракте.
 *
 * ─── Почему у готового набора этап всё равно показан ────────────────────────
 * Чтобы ответ на вопрос «а персоны-то откуда» был на экране всегда, а не только
 * в том прогоне, которому не повезло ждать. Готовый набор — это галочка с
 * числом персон, и она же отвечает, на ком считали.
 */

export interface AudienceSetRow {
  name: string;
  status: string;
  size: number;
  generatedCount: number;
  error: string | null;
}

export interface AudienceStage {
  state: NodeState;
  label: string;
  detail: string;
}

export const AUDIENCE_LABEL = "Создание персон";

/**
 * `null` — этапа на экране нет.
 *
 * Так выходит, когда прогон не ссылается на набор: ссылка `ON DELETE SET NULL`,
 * и у старых прогонов её может не быть вовсе. Рисовать в этом случае пустой
 * серый шаг значило бы утверждать, что персон не создавали, — а их создавали,
 * просто след потерян.
 */
export function audienceStage(set: AudienceSetRow | null | undefined): AudienceStage | null {
  if (!set) return null;

  if (set.status === "generating") {
    return {
      state: "running",
      label: AUDIENCE_LABEL,
      // Числами, а не долей: «60 %» одинаково выглядит на пяти персонах и на
      // пятистах, а ждать их надо по-разному (см. миграцию 15).
      detail: `${set.generatedCount} из ${set.size} — прогон начнётся, когда аудитория будет готова`,
    };
  }

  if (set.status === "failed") {
    return {
      state: "failed",
      label: AUDIENCE_LABEL,
      detail: set.error?.trim() || "причина не записана — это дефект воркера, а не набора",
    };
  }

  return {
    state: "done",
    label: AUDIENCE_LABEL,
    detail: `${set.name} — ${set.size} ${personaWord(set.size)}`,
  };
}

/**
 * Шкала с приставленным этапом.
 *
 * Считается здесь, а не в компоненте: «Шаг 4 из 12» — это то самое число, на
 * которое смотрит человек, решая, ждать ему или перезагружать страницу, и
 * ошибка в нём не видна ни на одном скриншоте.
 */
export function stageScale(input: {
  /** Сколько узлов конвейера в списке. */
  nodeCount: number;
  /** Сколько узлов уже пройдено. */
  nodeDone: number;
  /** Индекс текущего узла; −1 — о текущем ничего не известно. */
  nodeIndex: number;
  stage: AudienceStage | null;
}): { total: number; done: number; stepNumber: number; pct: number } {
  const { nodeCount, nodeDone, nodeIndex, stage } = input;
  const extra = stage ? 1 : 0;
  const total = nodeCount + extra;
  const done = nodeDone + (stage?.state === "done" ? 1 : 0);

  // Пока аудитория не готова, текущий шаг — она сама, а не «Разбор файла»:
  // именно она сейчас и считается, и показывать вместо неё первый узел
  // конвейера значит утверждать, что прогон уже идёт.
  const stepNumber =
    stage && stage.state !== "done"
      ? 1
      : Math.min(Math.max(nodeIndex + 1 + extra, 1), total);

  return { total, done, stepNumber, pct: Math.round((done / total) * 100) };
}

function personaWord(n: number): string {
  const two = n % 100;
  if (two >= 11 && two <= 14) return "персон";
  const one = n % 10;
  if (one === 1) return "персона";
  if (one >= 2 && one <= 4) return "персоны";
  return "персон";
}
