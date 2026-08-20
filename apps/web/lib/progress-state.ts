/**
 * Состояние шагов прогона и человеческое время.
 *
 * ─── Почему это отдельный модуль ──────────────────────────────────────────
 * Логика жила внутри `ProgressView` и опиралась на единственный источник —
 * последнее событие SSE. На завершённом прогоне 0051 экран показывал «Шаг 1 из
 * 13», а пройденные шаги стояли без галочек, хотя время у каждого было.
 *
 * Событие берётся из снимка в Valkey, у снимка есть срок жизни. Через сутки
 * после прогона его нет — событие не приходит, и экран считает, что прогон не
 * начинался. Длительности при этом рисуются: они приходят из Postgres отдельным
 * пропом. Получалась противоречивая картинка: время есть, а шаг «не пройден».
 *
 * Postgres знает и статус задачи, и длительность каждого шага. После прогона
 * он и есть источник правды; Valkey — только для живого.
 */

export type NodeState = "waiting" | "running" | "done" | "failed";

export interface ProgressInput {
  /** Имена узлов в порядке исполнения. */
  nodes: string[];
  /** Узел из последнего события SSE. Пусто — событий не было. */
  currentNode?: string | null;
  /** Статус из последнего события: RUNNING | DONE | FAILED | REPORT_READY. */
  eventStatus?: string | null;
  /** Статус задачи из Postgres. Он переживает срок жизни снимка в Valkey. */
  taskStatus?: string | null;
  /** Длительности завершённых шагов, секунды. */
  durations: Record<string, number>;
}

export interface ProgressSnapshot {
  states: NodeState[];
  doneCount: number;
  /** Индекс текущего шага; −1, когда о текущем шаге ничего не известно. */
  currentIndex: number;
  finished: boolean;
  failed: boolean;
}

const STOPPED = new Set(["FAILED", "CANCELLED"]);

export function progressStates(input: ProgressInput): ProgressSnapshot {
  const { nodes, currentNode, eventStatus, taskStatus, durations } = input;

  const finished = eventStatus === "REPORT_READY" || taskStatus === "REPORT_READY";
  const failed =
    eventStatus === "FAILED" || STOPPED.has(String(taskStatus ?? ""));

  const currentIndex = currentNode ? nodes.indexOf(currentNode) : -1;

  const states: NodeState[] = nodes.map((node, index) => {
    // Завершённый прогон пройден весь — независимо от того, дожил ли снимок.
    if (finished) return "done";

    // Записанная длительность означает, что шаг отработал до конца. Это
    // единственный признак, переживающий и снимок, и падение прогона.
    if (typeof durations[node] === "number") return "done";

    if (currentIndex < 0) return "waiting";
    if (index < currentIndex) return "done";
    if (index > currentIndex) return "waiting";
    if (failed) return "failed";
    return eventStatus === "DONE" ? "done" : "running";
  });

  return {
    states,
    doneCount: states.filter((s) => s === "done").length,
    currentIndex,
    finished,
    failed,
  };
}

/**
 * Секунды → «2 часа 52 мин 14 сек».
 *
 * Прежде здесь было `172:14`, и прочитать это нельзя: две минуты? три часа?
 * Именно это число владелец видит первым, открывая экран прогона.
 *
 * Нулевые части не печатаются: «1 час 0 мин 30 сек» читается медленнее, чем
 * «1 час 30 сек», и ничего не добавляет.
 */
export function humanDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;

  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours} ${hourWord(hours)}`);
  if (minutes > 0) parts.push(`${minutes} мин`);
  if (rest > 0 || parts.length === 0) parts.push(`${rest} сек`);
  return parts.join(" ");
}

/**
 * Склонение слова «час».
 *
 * По ПОСЛЕДНИМ двум цифрам, а не по первой: одиннадцать, двенадцать,
 * тринадцать и четырнадцать — «часов», хотя оканчиваются на 1–4. Проверка на
 * это стоит отдельным тестом: правило «смотрим последнюю цифру» выглядит
 * работающим ровно до 11.
 */
function hourWord(n: number): string {
  const two = n % 100;
  if (two >= 11 && two <= 14) return "часов";
  const one = n % 10;
  if (one === 1) return "час";
  if (one >= 2 && one <= 4) return "часа";
  return "часов";
}
