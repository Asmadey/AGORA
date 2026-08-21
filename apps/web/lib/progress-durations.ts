/**
 * Длительности шагов на экране прогресса.
 *
 * ─── Что чинится ──────────────────────────────────────────────────────────
 * Владелец видел «Расшифровка и спикеры (559 сек)», пока шаг шёл, и прочерк,
 * как только конвейер переходил к следующему.
 *
 * Воркер считает `duration_sec` для каждого завершённого узла и кладёт
 * `timings` в КАЖДОЕ публикуемое событие (`agent_core/pipeline/progress.py`,
 * `_track`). До экрана они не доезжали: интерфейс `ProgressEvent` этого поля не
 * объявлял, и клиент его выбрасывал. Оставался серверный проп `durations`,
 * который заполняется из Postgres в конце ВСЕГО прогона (`_save_timings`), —
 * то есть ровно тогда, когда на экран прогресса уже не смотрят.
 *
 * ─── Почему отдельная функция, а не выражение в компоненте ────────────────
 * Слияние двух источников с приоритетом — то место, где ошибка не видна: она
 * даёт правдоподобное число, просто не то. Здесь его можно проверить, не
 * поднимая React и SSE.
 */

/** Запись таймингов, как её кладёт воркер. Поля читаются защитно: снимок
 *  приходит из Valkey и разбирается как есть. */
export interface TimingEntry {
  node?: unknown;
  duration_sec?: unknown;
  status?: unknown;
}

/**
 * Серверные длительности, поверх которых легли живые.
 *
 * Живое значение важнее: серверное приходит из Postgres и записывается в конце
 * прогона, а при возобновлении из чекпоинта может остаться от предыдущего
 * прохода того же узла.
 *
 * `duration_sec: null` пропускается: у идущего узла воркер проставляет его в
 * момент перехода, и ноль на его месте показал бы «(0 сек)» на шаге, который
 * прямо сейчас идёт.
 */
export function mergeDurations(
  fromServer: Record<string, number>,
  live: TimingEntry[] | undefined | null,
): Record<string, number> {
  const out = { ...fromServer };
  if (!Array.isArray(live)) return out;

  for (const entry of live) {
    if (!entry || typeof entry !== "object") continue;
    const node = typeof entry.node === "string" ? entry.node.trim() : "";
    const seconds = entry.duration_sec;
    if (!node) continue;
    if (typeof seconds !== "number" || !Number.isFinite(seconds)) continue;
    out[node] = seconds;
  }
  return out;
}
