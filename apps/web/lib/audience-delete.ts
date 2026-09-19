/**
 * Что не даёт удалить набор персон.
 *
 * ─── Две разные причины, а не одна ───────────────────────────────────────────
 * Прежде отказ был один: на наборе стоит прогон. Внешний ключ
 * `tasks.persona_set_id` объявлен `ON DELETE SET NULL`, поэтому удаление такого
 * набора не ломает отчёт, а молча стирает ответ на вопрос «на ком это
 * проверяли».
 *
 * 18.09.2026 выяснилась вторая: набор можно было удалить, пока воркер его
 * наполняет. Задача продолжала звать модель двадцать семь минут, писала
 * прогресс в исчезнувшую строку и занимала единственного воркера — прогон 0093
 * стоял за ней в очереди и выглядел зависшим. Удалять готовый набор значит
 * потерять сам набор; удалять генерирующийся — ещё и уже оплаченную работу.
 *
 * ─── Почему логика здесь, а не в маршруте ───────────────────────────────────
 * Веб-тесты собирают только `lib/**` (CLAUDE.md §11.7). Правило, оставленное в
 * `lib/server/*.ts` рядом с пулом соединений, не покрыто ничем по построению.
 */

/** Одна строка отказа. `runs` остаётся числом прогонов и при генерации. */
export interface BlockedSet {
  id: string;
  name: string;
  runs: number;
  reason: "runs" | "generating";
}

export interface BlockedRow {
  id: string;
  name: string;
  runs: string;
  status: "generating" | "ready" | "failed";
}

export interface AudienceDeletionState {
  status: BlockedRow["status"];
  runs: number;
}

/** Удаление разрешено только если набор не строится и не используется прогоном. */
export function canDeleteAudienceSet({ status, runs }: AudienceDeletionState): boolean {
  return status !== "generating" && runs === 0;
}

/**
 * Наборы, которые удалять нельзя, одним запросом.
 *
 * `LEFT JOIN`, а не `JOIN`: генерирующийся набор прогонов ещё не имеет, и
 * внутреннее соединение выбросило бы именно те строки, ради которых запрос
 * переписан. `HAVING` вместо `WHERE` по той же причине — условие стоит на
 * агрегате.
 */
export const BLOCKED_SETS_QUERY = `
  SELECT ps.id, ps.name, COUNT(t.id)::text AS runs, ps.status
    FROM persona_sets ps
    LEFT JOIN tasks t ON t.persona_set_id = ps.id
   WHERE ps.id = ANY($1::uuid[])
   GROUP BY ps.id, ps.name, ps.status
  HAVING COUNT(t.id) > 0 OR ps.status = 'generating'
`;

export function toBlocked(rows: BlockedRow[]): BlockedSet[] {
  return rows.flatMap((row) => {
    const runs = Number(row.runs);
    if (canDeleteAudienceSet({ status: row.status, runs })) return [];
    return [{
      id: row.id,
      name: row.name,
      runs,
      // Прогоны важнее генерации: незаконченную аудиторию можно собрать заново,
      // а отчёт, потерявший ссылку на свою аудиторию, восстановить нечем.
      reason: runs > 0 ? "runs" : "generating",
    }];
  });
}

/**
 * Текст отказа — по причине, а не один на всех.
 *
 * «Не удалены — на них уже считались прогоны» про набор, который прямо сейчас
 * генерируется, неправда, и человек пойдёт искать несуществующие прогоны.
 */
export function blockedReason(set: BlockedSet): string {
  return set.reason === "runs"
    ? `${set.name} — ${set.runs} прогон(ов)`
    : `${set.name} — персоны ещё создаются; дождитесь конца или отмените создание`;
}
