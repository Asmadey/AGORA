/** Minimum respondent count at which the 14-35 slice is safe to display. */
export const SMALL_SLICE_MIN = 15;

export type NullableShare = number | null;

function finiteOrNull(value: number | null): number | null {
  return value !== null && Number.isFinite(value) ? value : null;
}

function cleanNumber(value: number): number {
  return Math.round(value * 1_000_000_000_000) / 1_000_000_000_000;
}

/** Formats a measured share. A measured zero is deliberately not a missing value. */
export function formatShare(share: NullableShare): string {
  const value = finiteOrNull(share);
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

/** Formats a mean score with the decimal separator used in the customer report. */
export function formatMean(value: number | null): string {
  const safe = finiteOrNull(value);
  if (safe === null) return "—";
  const rounded = Math.round(safe * 10) / 10;
  return String(rounded).replace(".", ",");
}

/** Percentage of a scale occupied by a value, clamped to the scale bounds. */
export function scaleFillPercent(
  value: number | null,
  min: number,
  max: number,
): number | null {
  const safeValue = finiteOrNull(value);
  if (
    safeValue === null ||
    !Number.isFinite(min) ||
    !Number.isFinite(max) ||
    max <= min
  ) {
    return null;
  }
  return Math.max(0, Math.min(100, ((safeValue - min) / (max - min)) * 100));
}

/** Length of a bar relative to the largest measured share. */
export function barLengthPercent(share: number, maxShare: number): number {
  if (!Number.isFinite(share) || !Number.isFinite(maxShare) || maxShare <= 0) return 0;
  return Math.max(0, Math.min(100, (share / maxShare) * 100));
}

/** Converts a share to a clamped visual percentage while preserving null. */
export function sharePercent(share: NullableShare): number | null {
  const value = finiteOrNull(share);
  return value === null ? null : Math.max(0, Math.min(100, value * 100));
}

/** Largest measured share used as the common comparison baseline for bars. */
export function maxMeasuredShare(shares: readonly NullableShare[]): number {
  return shares.reduce<number>((maximum, share) => {
    const value = finiteOrNull(share);
    return value === null ? maximum : Math.max(maximum, value);
  }, 0);
}

export interface DonutPartInput {
  id: string;
  share: NullableShare;
}

export interface DonutSegment {
  id: string;
  share: NullableShare;
  offset: number;
  length: number;
  missing: boolean;
}

export interface DonutSegmentsResult {
  segments: DonutSegment[];
  totalShare: number;
  exceedsTotal: boolean;
  hasGap: boolean;
  missingCount: number;
}

/**
 * Turns parts into non-overlapping circumference percentages.
 *
 * A malformed overfull ring is normalized for drawing, but the raw total is
 * retained and exposed so a caller can explain the data problem to the reader.
 */
export function donutSegments(parts: readonly DonutPartInput[]): DonutSegmentsResult {
  const totalShare = cleanNumber(parts.reduce((sum, part) => {
    const share = finiteOrNull(part.share);
    return sum + (share === null ? 0 : Math.max(0, share));
  }, 0));
  const normalization = totalShare > 1 ? 1 / totalShare : 1;
  let offset = 0;
  let missingCount = 0;

  const segments = parts.map((part) => {
    const share = finiteOrNull(part.share);
    if (share === null) missingCount += 1;
    const length = share === null ? 0 : Math.max(0, share) * 100 * normalization;
    const segment = {
      id: part.id,
      share,
      offset,
      length,
      missing: share === null,
    };
    offset = cleanNumber(offset + length);
    return segment;
  });

  if (totalShare > 1) {
    const lastMeasured = [...segments].reverse().find((segment) => !segment.missing);
    if (lastMeasured) lastMeasured.length = cleanNumber(100 - lastMeasured.offset);
  }

  return {
    segments,
    totalShare,
    exceedsTotal: totalShare > 1,
    hasGap: offset < 100 - 0.000001,
    missingCount,
  };
}

export interface StackedPartInput {
  id: string;
  label: string;
  share: NullableShare;
}

export interface StackedSegment {
  id: string;
  label: string;
  share: NullableShare;
  offset: number;
  length: number;
  remainder: boolean;
  missing: boolean;
}

export interface StackedSegmentsResult {
  segments: StackedSegment[];
  totalShare: number;
  exceedsTotal: boolean;
  missingCount: number;
}

/**
 * Builds a 100%-stacked row without stretching measured parts to hide an
 * unanswered remainder. Overfull input is normalized and reported explicitly.
 */
export function stackedSegments(
  parts: readonly StackedPartInput[],
): StackedSegmentsResult {
  const totalShare = cleanNumber(parts.reduce((sum, part) => {
    const share = finiteOrNull(part.share);
    return sum + (share === null ? 0 : Math.max(0, share));
  }, 0));
  const normalization = totalShare > 1 ? 1 / totalShare : 1;
  let offset = 0;
  let missingCount = 0;

  const segments = parts.map((part) => {
    const share = finiteOrNull(part.share);
    if (share === null) missingCount += 1;
    const length = share === null ? 0 : Math.max(0, share) * normalization;
    const segment = {
      id: part.id,
      label: part.label,
      share,
      offset,
      length,
      remainder: false,
      missing: share === null,
    };
    offset = cleanNumber(offset + length);
    return segment;
  });

  const remainder = totalShare < 1 ? cleanNumber(1 - totalShare) : 0;
  if (remainder > 0.000001) {
    segments.push({
      id: "unanswered",
      label: "Не ответили",
      share: remainder,
      offset,
      length: remainder,
      remainder: true,
      missing: false,
    });
  }

  return {
    segments,
    totalShare,
    exceedsTotal: totalShare > 1,
    missingCount,
  };
}

/** Net Promoter Score in percentage points, or null when either input is absent. */
export function npsPoints(promoters: NullableShare, detractors: NullableShare): number | null {
  const safePromoters = finiteOrNull(promoters);
  const safeDetractors = finiteOrNull(detractors);
  if (safePromoters === null || safeDetractors === null) return null;
  return Math.round((safePromoters - safeDetractors) * 100);
}

/** Explains why a slice is hidden, without treating an unknown size as zero. */
export function smallSliceNote(
  n: number | null,
  minSegment: number,
  label: string,
): string | null {
  if (n === null || !Number.isFinite(n) || !Number.isFinite(minSegment) || n >= minSegment) {
    return null;
  }
  return `Срез ${label} содержит ${n} персон. Показатель не отображается из-за малого размера группы.`;
}

export interface SliceTargetState {
  n: number | null;
  belowThreshold?: boolean;
}

/** Single source of truth for whether a target slice may show a number. */
export function targetUnavailableNote(
  target: SliceTargetState | null | undefined,
  label = "14-35 лет",
): string | null {
  if (!target) return "Показатель по срезу не задан.";
  if (target.belowThreshold || (target.n !== null && target.n < SMALL_SLICE_MIN)) {
    return smallSliceNote(target.n, SMALL_SLICE_MIN, label) ??
      `Срез ${label} слишком мал для отображения показателя.`;
  }
  if (target.n === null) return `Показатель среди ${label} не считался.`;
  return null;
}
