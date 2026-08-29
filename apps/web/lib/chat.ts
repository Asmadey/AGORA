import type { TenantSettings } from "@/lib/settings";

/**
 * Чат по результатам исследования (#28): разбор потока и бюджет реплик.
 *
 * ─── Что здесь и почему не в компоненте ───────────────────────────────────
 * Разбор SSE и решение «можно ли ещё спросить» — чистая логика, и проверять её
 * браузером значит не проверять. В компоненте остаётся только отрисовка.
 */

export type ChatMode = "analyst" | "persona";

export interface ChatFlags {
  grounded: boolean;
  insufficientData: boolean;
  outOfProfile: boolean;
  contradictsPrevious: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  flags?: ChatFlags;
}

/** Событие потока: кусок текста, финал с флагами либо отказ. */
export type ChatEvent =
  | { kind: "delta"; text: string }
  | { kind: "done"; answer: string; flags: ChatFlags }
  | { kind: "error"; message: string };

function flagsOf(raw: Record<string, unknown>): ChatFlags {
  return {
    // Умолчание `false` для опоры — намеренно строгое. Событие без поля
    // означает, что разбор не состоялся, и считать такой ответ обоснованным
    // значит выдать за проверенное то, что не проверялось.
    grounded: raw.grounded === true,
    insufficientData: raw.insufficient_data === true,
    outOfProfile: raw.out_of_profile === true,
    contradictsPrevious: raw.contradicts_previous === true,
  };
}

/**
 * Разбирает одну строку `data: …` из потока.
 *
 * `null` — строка не является событием (пустая, комментарий, «event:»).
 * Битый JSON тоже даёт `null`, а не исключение: один испорченный кусок не
 * должен обрывать ответ, который в остальном пришёл целым.
 */
export function parseChatEvent(line: string): ChatEvent | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("data:")) return null;

  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(trimmed.slice(5).trim()) as Record<string, unknown>;
  } catch {
    return null;
  }

  if (typeof raw.error === "string") return { kind: "error", message: raw.error };
  if (typeof raw.delta === "string") return { kind: "delta", text: raw.delta };
  if (raw.done && typeof raw.done === "object") {
    const done = raw.done as Record<string, unknown>;
    return {
      kind: "done",
      answer: typeof done.answer === "string" ? done.answer : "",
      flags: flagsOf(done),
    };
  }
  return null;
}

/**
 * Бюджет реплик чата.
 *
 * ─── «Тот же кап» — решение владельца, и вот что оно означает точно ───────
 * `costCapValue` описывает потолок вызовов модели на исследование. Чат живёт
 * после прогона и тоже платный, поэтому его реплики берутся из того же числа.
 *
 * ЧЕГО ЭТА ФУНКЦИЯ НЕ ЗНАЕТ: сколько вызовов потратил сам конвейер. Расход
 * прогона нигде не сохраняется — `CallBudget` в воркере живёт внутри задачи и
 * умирает вместе с ней. Поэтому потолок здесь ограничивает реплики чата тем же
 * числом, а не остатком от прогона.
 *
 * Разница названа, а не замазана: написать «осталось N из потолка» и умолчать,
 * что прогон уже что-то израсходовал, значило бы показать число, которое
 * выглядит точным и таковым не является. Экран говорит «реплик израсходовано
 * N из M», а не «бюджет исчерпан на N %».
 */
export interface ChatBudget {
  allowed: boolean;
  used: number;
  limit: number | null;
  reason: string;
}

export function chatBudget(
  settings: Pick<TenantSettings, "costCap" | "costCapValue">,
  usedReplies: number,
): ChatBudget {
  if (settings.costCap !== "hard") {
    return { allowed: true, used: usedReplies, limit: null, reason: "" };
  }

  const limit = settings.costCapValue;
  if (!Number.isInteger(limit) || limit <= 0) {
    // Мусор в снимке не должен запирать чат: «жёсткий кап» без числа — это
    // недонастройка, а не запрет.
    return { allowed: true, used: usedReplies, limit: null, reason: "" };
  }

  if (usedReplies >= limit) {
    return {
      allowed: false,
      used: usedReplies,
      limit,
      reason:
        `Исчерпан потолок вызовов модели: ${usedReplies} из ${limit}. ` +
        `Потолок задаётся в Настройках командой («Кап стоимости»). ` +
        `Он общий с прогоном — чат тратит те же вызовы.`,
    };
  }

  return { allowed: true, used: usedReplies, limit, reason: "" };
}

/**
 * Подпись под ответом — то, что стоит сказать про него человеку.
 *
 * Пустая строка означает «сказать нечего», и это нормальный исход: обычный
 * ответ с таймкодом не нуждается в комментарии.
 */
export function replyNote(flags: ChatFlags, mode: ChatMode): string {
  if (flags.insufficientData) {
    return "В этом исследовании таких данных нет — ответ об этом и говорит.";
  }
  if (mode === "persona" && flags.outOfProfile) {
    return "Вопрос за пределами профиля персоны: она отвечает «не знаю», а не выдумывает.";
  }
  if (mode === "persona" && flags.contradictsPrevious) {
    return "Ответ расходится с тем, что персона говорила в прогоне.";
  }
  if (!flags.grounded) {
    return (
      "Без опоры на материал: в ответе нет ни таймкода, ни цитаты. " +
      "Проверьте его по отчёту, прежде чем на него ссылаться."
    );
  }
  return "";
}
