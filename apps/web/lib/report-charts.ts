/** Общие расчёты для диаграмм отчёта. Разметка только отображает их результат. */

export const SEGMENT_SCORE_MAX = 10;

/** Секунды -> M:SS или H:MM:SS для подписей оси и таймкодных ссылок. */
export function formatTimecode(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const rest = String(total % 60).padStart(2, "0");
  const minutes = Math.floor(total / 60) % 60;
  const hours = Math.floor(total / 3600);
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}`
    : `${minutes}:${rest}`;
}

/** Подпись конца оси не округает фактическую длительность ролика. */
export function formatAxisTimecode(seconds: number): string {
  const safe = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
  const whole = Math.floor(safe);
  const fraction = Math.round((safe - whole) * 10) / 10;
  if (fraction === 0) return formatTimecode(whole);
  if (fraction >= 1) return formatTimecode(whole + 1);
  return `${formatTimecode(whole)}.${String(fraction).slice(2)}`;
}

/** Таймкод старого снимка -> секунды для точки на шкале. */
export function parseTimecode(timecode: string): number | null {
  const parts = timecode.split(":");
  if (parts.length < 2 || parts.length > 3 || parts.some((part) => !/^\d+$/.test(part))) {
    return null;
  }
  const values = parts.map(Number);
  const seconds = parts.length === 3
    ? values[0] * 3600 + values[1] * 60 + values[2]
    : values[0] * 60 + values[1];
  return Number.isFinite(seconds) ? seconds : null;
}

/** Положение точки на честной шкале ролика. */
export function riskPointPosition(seconds: number, durationSec: number): number | null {
  if (!Number.isFinite(seconds) || !Number.isFinite(durationSec) || durationSec <= 0) {
    return null;
  }
  return Math.max(0, Math.min(100, (seconds / durationSec) * 100));
}

/** Размер маркера: больше персон - заметнее точка, но без линейного перекоса. */
export function riskMarkerScale(personas: number, maxPersonas: number): number {
  if (!Number.isFinite(personas) || personas <= 0 || maxPersonas <= 0) return 0.75;
  return 0.75 + (Math.sqrt(personas) / Math.sqrt(maxPersonas)) * 0.75;
}

/** Насыщенность маркера по числу персон. */
export function riskMarkerOpacity(personas: number, maxPersonas: number): number {
  if (!Number.isFinite(personas) || personas <= 0 || maxPersonas <= 0) return 0.45;
  return 0.45 + (Math.sqrt(personas) / Math.sqrt(maxPersonas)) * 0.55;
}

/** Процент заполнения полосы сегмента на общей шкале 0-10. */
export function segmentBarPercent(value: number | null, max = SEGMENT_SCORE_MAX): number | null {
  if (value === null || !Number.isFinite(value) || !Number.isFinite(max) || max <= 0) {
    return null;
  }
  return Math.max(0, Math.min(100, (value / max) * 100));
}

export function segmentDimensionLabel(dimension: string): string {
  return {
    age_group: "Возраст",
    geo: "Тип населённого пункта",
    gender: "Пол",
  }[dimension] ?? dimension;
}

/**
 * Что показать в разделе «Где собирались бросить».
 *
 * ─── Почему это состояние, а не просто «прятать при нуле» ─────────────────
 * Раздел скрывался целиком, когда точек риска нет. На прогоне «Тизер_Дорога_
 * домой» их ноль при удержании 100 % — то есть **никто не собирался бросать**.
 * Это результат исследования, причём хороший, и прятать его значит выдавать
 * успех за отсутствие данных. Владелец открыл отчёт и спросил, куда делись
 * графики; ответ «их не рисуют, потому что всё хорошо» отчёт обязан давать сам.
 *
 * Отличить «спросили, и никто» от «не мерили» можно по `retentionRate`: он
 * приходит из агрегата и равен null, когда удержание не считалось вовсе.
 *
 * Шкала отделена от наличия точек намеренно: без длительности ролика ось
 * построить нечестно, но сами точки показать по-прежнему можно.
 */
export type RiskSectionState =
  /** Точки есть и есть длительность — рисуем шкалу. */
  | { kind: "chart" }
  /** Точки есть, длительности нет — список без выдуманной оси. */
  | { kind: "list" }
  /** Точек нет, но удержание измерено: никто не заявил о прекращении. */
  | { kind: "none-stopped" }
  /** Точек нет и удержание не считалось — сказать об этом прямо. */
  | { kind: "not-measured" };

export function riskSectionState(
  pointCount: number,
  retentionRate: number | null,
  durationSec: number | null,
): RiskSectionState {
  if (pointCount > 0) {
    return durationSec !== null && durationSec > 0 ? { kind: "chart" } : { kind: "list" };
  }
  return retentionRate !== null ? { kind: "none-stopped" } : { kind: "not-measured" };
}

/**
 * Почему отсутствует плитка «Донесённые ценности» (вопрос 8).
 *
 * Пустую плитку рисовать нельзя — она утверждала бы, что вопрос задавали и
 * никто не ответил (решение владельца 17.09.2026, см. ReportBody). Но и молчать
 * нельзя: на месте прежнего графика ценностей аудитории теперь пустота, и
 * читатель законно считает, что продукт сломался.
 *
 * null — плитку показываем, объяснять нечего.
 */
export function donatedValuesAbsence(
  hasQuestionEight: boolean,
  hasSurvey: boolean,
): string | null {
  if (hasQuestionEight) return null;
  return hasSurvey
    ? "Вопрос 8 о донесённых ценностях в анкете этого прогона не задавался."
    : "Прогон шёл без анкеты заказчика — вопроса 8 о донесённых ценностях в нём не было.";
}
