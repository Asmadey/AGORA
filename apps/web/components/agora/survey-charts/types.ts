import type { NullableShare } from "@/lib/survey-charts";

export type SurveyTone =
  | "positive"
  | "positive-soft"
  | "negative"
  | "negative-soft"
  | "neutral"
  | "unknown"
  | "scale"
  | "bar"
  | "key"
  | "slice";

export interface SurveySample {
  answered: number | null;
  surveyed: number | null;
  excluded: number | null;
  notAsked?: boolean;
}

export interface SurveyTargetBase {
  n: number | null;
  belowThreshold?: boolean;
}

export interface SurveyPart {
  id: string;
  label: string;
  tone: SurveyTone;
  share: NullableShare;
  service?: boolean;
}

export interface SurveySecondaryMetric {
  share: NullableShare;
  caption: string;
}

export interface SurveyScaleTarget extends SurveyTargetBase {
  mean: number | null;
  topBox: NullableShare;
  groups?: readonly SurveyScaleGroup[];
}

export interface SurveyScaleGroup {
  id: string;
  label: string;
  share: NullableShare;
}

export interface SurveyDonutTarget extends SurveyTargetBase {
  parts: readonly SurveyPart[];
}

export interface SurveyBarRow {
  id: string;
  label: string;
  share: NullableShare;
  count?: number | null;
  service?: boolean;
  tone?: "regular" | "key";
}

export interface SurveyBarTargetRow {
  id: string;
  label?: string;
  share: NullableShare;
  count?: number | null;
}

export interface SurveyBarTarget extends SurveyTargetBase {
  rows: readonly SurveyBarTargetRow[];
}

export interface SurveyMetricPair {
  id: string;
  label: string;
  total: NullableShare;
  target: NullableShare;
}

export interface SurveyStackedTarget extends SurveyTargetBase {
  parts: readonly SurveyPart[];
}

export interface SurveyStackedPart extends SurveyPart {
  side?: "negative" | "neutral" | "positive" | "service";
}

export interface SurveyMatrixTarget {
  n: number | null;
  count: number | null;
  share: NullableShare;
  belowThreshold?: boolean;
}

export interface SurveyMatrixRow {
  id: string;
  label: string;
  parts: readonly SurveyStackedPart[];
  target: SurveyMatrixTarget;
}

export interface SurveyMatrixGroup {
  id: string;
  title: string;
  rows: readonly SurveyMatrixRow[];
}

export interface SurveyNpsValues {
  promoters: NullableShare;
  neutral: NullableShare;
  detractors: NullableShare;
}

export interface SurveyNpsTarget extends SurveyTargetBase {
  values: SurveyNpsValues;
  mean?: number | null;
  topBox?: NullableShare;
}
