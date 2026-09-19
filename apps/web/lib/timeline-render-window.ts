/**
 * Количество ячеек, которое оставляем выше и ниже видимой области.
 * Три строки перекрывают один быстрый жест прокрутки на панели высотой 600px,
 * но не превращают окно обратно в полный список.
 */
export const TIMELINE_WINDOW_OVERSCAN = 3;

/** Минимум строк, который показываем до первого ответа IntersectionObserver. */
export const TIMELINE_INITIAL_VISIBLE = 3;

export interface TimelineRenderWindow {
  /** Первый индекс, включённый в окно. */
  start: number;
  /** Первый индекс после окна. */
  end: number;
}

function finiteIndex(value: number, fallback: number): number {
  return Number.isFinite(value) ? Math.floor(value) : fallback;
}

/**
 * Возвращает окно ячеек вокруг видимого полуинтервала [visibleStart, visibleEnd).
 *
 * Все границы нормализуются здесь, а не в компоненте: нулевой список, короткий
 * список и прокрутка к самому концу должны давать один и тот же предсказуемый
 * контракт для любого потребителя таймлайна.
 */
export function timelineRenderWindow(
  total: number,
  visibleStart: number,
  visibleEnd: number,
  overscan: number = TIMELINE_WINDOW_OVERSCAN,
): TimelineRenderWindow {
  const count = Math.max(0, finiteIndex(total, 0));
  if (count === 0) return { start: 0, end: 0 };

  const rawStart = finiteIndex(visibleStart, 0);
  const rawEnd = finiteIndex(visibleEnd, rawStart + 1);
  const start = Math.max(0, Math.min(count - 1, Math.min(rawStart, rawEnd)));
  const end = Math.max(start + 1, Math.min(count, Math.max(rawStart, rawEnd)));
  const extra = Math.max(0, finiteIndex(overscan, 0));

  return {
    start: Math.max(0, start - extra),
    end: Math.min(count, end + extra),
  };
}

/** Активная ячейка остаётся в DOM, даже если плеер находится далеко от окна. */
export function isTimelineCellRendered(
  index: number,
  window: TimelineRenderWindow,
  pinnedIndex: number | null = null,
): boolean {
  return (
    (index >= window.start && index < window.end) ||
    (pinnedIndex !== null && index === pinnedIndex)
  );
}
