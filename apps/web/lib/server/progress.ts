import "server-only";

import { subscriber, valkey } from "@/lib/server/valkey";

/**
 * Чтение прогресса прогона (задача #12).
 *
 * Зеркало контракта воркера: `services/agent-core/agent_core/pipeline/progress.py`.
 * Префикс ключа и канала обязан совпадать побайтово. Разойтись они могут молча:
 * веб подпишется на канал, которого никто не публикует, поток останется пустым,
 * и выглядеть это будет как «исследование не стартовало», а не как опечатка.
 */

/** Совпадает с `_PREFIX` в pipeline/progress.py. */
const PREFIX = "agora:progress:";

export function progressKey(taskId: string): string {
  return `${PREFIX}${taskId}`;
}

export function progressChannel(taskId: string): string {
  return `${PREFIX}${taskId}`;
}

export interface ProgressEvent {
  task_id: string;
  node: string;
  status: string;
  at: number;
  detail?: string;
  error?: string;
  degraded?: string[];
}

function parse(raw: string | null): ProgressEvent | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ProgressEvent;
  } catch {
    // Битый снимок показывает «нет данных», а не роняет экран запущенного
    // прогона: 500 на странице идущего исследования хуже пустой шкалы.
    return null;
  }
}

/**
 * Текущее состояние прогона.
 *
 * Это ответ на «обрыв соединения переподключается без потери состояния» из cdd.
 * Pub/Sub ничего не помнит, и подписчик, пришедший к середине прогона, не
 * получит ни одного уже отправленного сообщения — а экран прогресса открывают
 * именно так. Снимок из ключа отдаётся первым же событием потока.
 */
export async function progressSnapshot(taskId: string): Promise<ProgressEvent | null> {
  const client = await valkey();
  return parse(await client.get(progressKey(taskId)));
}

/**
 * Подписка на смены узлов. Возвращает функцию отписки.
 *
 * Соединение создаётся своё на каждый поток и закрывается вызывающим. Общий
 * подписчик не годится: отписка одного ушедшего клиента снимала бы подписку у
 * всех, кто смотрит тот же прогон.
 */
export async function subscribeProgress(
  taskId: string,
  onEvent: (event: ProgressEvent) => void,
): Promise<() => Promise<void>> {
  const client = await subscriber();
  const channel = progressChannel(taskId);

  await client.subscribe(channel, (message: string) => {
    const event = parse(message);
    if (event) onEvent(event);
  });

  return async () => {
    try {
      await client.unsubscribe(channel);
    } finally {
      // quit() дожидается ответа сервера и на оборванном соединении висит до
      // таймаута; destroy() закрывает сокет сразу. Клиент к этому моменту уже
      // ушёл, ждать ради него нечего.
      client.destroy();
    }
  };
}
