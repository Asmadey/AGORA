import { MANDATORY_QUESTIONS } from "./customer-survey.ts";
import {
  matrixPairs,
  optionPairs,
  polarityPairs,
  type SurveyPairRow,
} from "./report-survey.ts";
import type { SurveyQuestionView, SurveyStats, SurveyView } from "./report-view.ts";
import type {
  SurveyBarRow,
  SurveyBarTarget,
  SurveyMetricPair,
  SurveyMatrixGroup,
  SurveyMatrixRow,
  SurveyNpsValues,
  SurveyPart,
  SurveySample,
  SurveyScaleGroup,
  SurveyScaleTarget,
  SurveyStackedPart,
  SurveyStackedTarget,
} from "../components/agora/survey-charts/types";

interface ChartHeader {
  id: string;
  number: number | null;
  title: string;
}

export type SurveyQuestionChart =
  | (ChartHeader & {
      kind: "scale";
      mean: number | null;
      min: number;
      max: number;
      topBox: number | null;
      minLabel: string;
      maxLabel: string;
      groups: readonly SurveyScaleGroup[];
      target: SurveyScaleTarget;
      sample: SurveySample;
    })
  | (ChartHeader & {
      kind: "bar";
      rows: readonly SurveyBarRow[];
      target: SurveyBarTarget;
      secondaryMetrics: readonly SurveyMetricPair[];
      sample: SurveySample;
    })
  | (ChartHeader & {
      kind: "stacked";
      parts: readonly SurveyStackedPart[];
      target: SurveyStackedTarget;
      sample: SurveySample;
    })
  | (ChartHeader & {
      kind: "matrix";
      groups: readonly SurveyMatrixGroup[];
      targetN: number | null;
      sample: SurveySample;
    })
  | (ChartHeader & {
      kind: "nps";
      values: SurveyNpsValues;
      mean: number | null;
      topBox: number | null;
      target: SurveyNpsTarget;
      sample: SurveySample;
    })
  | (ChartHeader & {
      kind: "open";
      texts: readonly string[];
      targetTexts: readonly string[] | null;
      target: { n: number | null; belowThreshold?: boolean };
      sample: SurveySample;
    })
  | (ChartHeader & {
      kind: "unsupported";
      reason: string;
      sample: SurveySample;
    });

interface SurveyNpsTarget {
  n: number | null;
  belowThreshold?: boolean;
  values: SurveyNpsValues;
  mean: number | null;
  topBox: number | null;
}

function definitionFor(question: SurveyQuestionView) {
  return MANDATORY_QUESTIONS.find((candidate) =>
    candidate.id === question.id || candidate.number === question.number,
  );
}

function sample(stats: SurveyStats): SurveySample {
  return {
    answered: stats.n,
    surveyed: stats.base,
    excluded: stats.errors,
  };
}

function targetBase(stats: SurveyStats) {
  return { n: stats.n, belowThreshold: stats.belowThreshold };
}

function groupLabel(id: string): string {
  return `Баллы ${id}`;
}

function scaleGroups(stats: SurveyStats): SurveyScaleGroup[] {
  return (stats.groups ?? []).map((group) => ({
    id: group.id,
    label: groupLabel(group.id),
    share: group.share,
  }));
}

function optionTone(question: SurveyQuestionView, id: string): SurveyPart["tone"] {
  const definition = definitionFor(question);
  if (definition?.options?.find((option) => option.id === id)?.service) return "unknown";
  const group = Object.entries(definition?.reporting?.groups ?? {}).find(([, ids]) => ids?.includes(id));
  if (group?.[0] === "positive") return "positive";
  if (group?.[0] === "negative") return "negative";
  if (group?.[0] === "neutral") return "neutral";
  return "bar";
}

function optionRows(
  question: SurveyQuestionView,
  total: SurveyStats,
  target: SurveyStats,
): SurveyPairRow[] {
  return optionPairs(question, total, target);
}

function barRows(question: SurveyQuestionView, total: SurveyStats, target: SurveyStats) {
  const rows = optionRows(question, total, target);
  return {
    rows: rows.map((row) => ({
      id: row.id,
      label: row.label,
      share: row.total,
      count: row.totalCount,
      service: row.service,
      tone: "regular" as const,
    })),
    target: {
      ...targetBase(target),
      rows: rows.map((row) => ({ id: row.id, label: row.label, share: row.target, count: row.targetCount })),
    },
  };
}

function secondaryMetrics(question: SurveyQuestionView): SurveyMetricPair[] {
  const groups = definitionFor(question)?.reporting?.groups;
  if (!groups?.positive?.length || !groups.negative?.length) return [];
  return polarityPairs(question, question.total, question.target).map((row) => ({
    id: row.id,
    label: row.label,
    total: row.total,
    target: row.target,
  }));
}

function stackedParts(question: SurveyQuestionView, rows: readonly SurveyPairRow[], side?: boolean): SurveyStackedPart[] {
  return rows.map((row) => {
    const tone = optionTone(question, row.id);
    return {
      id: row.id,
      label: row.label,
      tone,
      share: side ? row.target : row.total,
      side: row.service ? "service" : tone === "negative" ? "negative" : tone === "positive" ? "positive" : "neutral",
      service: row.service,
    };
  });
}

function stackedChart(question: SurveyQuestionView): SurveyQuestionChart {
  const rows = optionRows(question, question.total, question.target);
  return {
    id: question.id,
    number: question.number,
    title: question.label,
    kind: "stacked",
    parts: stackedParts(question, rows),
    target: {
      ...targetBase(question.target),
      parts: stackedParts(question, rows, true),
    },
    sample: sample(question.total),
  };
}

function matrixChart(question: SurveyQuestionView): SurveyQuestionChart {
  const rows = matrixPairs(question, question.total, question.target);
  const groups = new Map<string, SurveyMatrixRow[]>();
  for (const row of rows) {
    const id = row.themeId ?? "unknown";
    const targetPositive = row.options.find((option) => option.id === "m-1" || option.id === "y-1");
    const matrixRow: SurveyMatrixRow = {
      id: row.id,
      label: row.label,
      parts: stackedParts(question, row.options),
      target: {
        n: question.target.n,
        count: targetPositive?.targetCount ?? null,
        share: targetPositive?.target ?? null,
        belowThreshold: question.target.belowThreshold,
      },
    };
    const existing = groups.get(id) ?? [];
    existing.push(matrixRow);
    groups.set(id, existing);
  }
  const definition = definitionFor(question);
  return {
    id: question.id,
    number: question.number,
    title: question.label,
    kind: "matrix",
    groups: [...groups.entries()].map(([id, groupedRows]) => ({
      id,
      title: definition?.themes?.find((theme) => theme.id === id)?.label ?? id,
      rows: groupedRows,
    })),
    targetN: question.target.n,
    sample: sample(question.total),
  };
}

function npsValues(stats: SurveyStats): SurveyNpsValues {
  const byId = new Map((stats.groups ?? []).map((group) => [group.id, group.share]));
  return {
    promoters: byId.get("9-10") ?? null,
    neutral: byId.get("7-8") ?? null,
    detractors: byId.get("0-6") ?? null,
  };
}

export function buildSurveyQuestionChart(question: SurveyQuestionView): SurveyQuestionChart {
  const definition = definitionFor(question);
  const hint = definition?.reporting?.chart;

  if (question.type === "open") {
    return {
      id: question.id,
      number: question.number,
      title: question.label,
      kind: "open",
      texts: question.total.texts ?? [],
      targetTexts: question.target.texts,
      target: targetBase(question.target),
      sample: sample(question.total),
    };
  }

  if (hint === "nps" || question.number === 15) {
    return {
      id: question.id,
      number: question.number,
      title: question.label,
      kind: "nps",
      values: npsValues(question.total),
      mean: question.total.mean,
      topBox: question.total.topBox,
      target: {
        ...targetBase(question.target),
        values: npsValues(question.target),
        mean: question.target.mean,
        topBox: question.target.topBox,
      },
      sample: sample(question.total),
    };
  }

  if (question.type === "scale" || hint === "scale" || hint === "scale_top_box") {
    const min = definition?.scaleMin ?? 0;
    const max = definition?.scaleMax ?? 10;
    return {
      id: question.id,
      number: question.number,
      title: question.label,
      kind: "scale",
      mean: question.total.mean,
      min,
      max,
      topBox: question.total.topBox,
      minLabel: "минимум",
      maxLabel: "максимум",
      groups: scaleGroups(question.total),
      target: {
        ...targetBase(question.target),
        mean: question.target.mean,
        topBox: question.target.topBox,
        groups: scaleGroups(question.target),
      },
      sample: sample(question.total),
    };
  }

  if (question.type === "multi_choice" || hint === "bars") {
    const bars = barRows(question, question.total, question.target);
    return {
      id: question.id,
      number: question.number,
      title: question.label,
      kind: "bar",
      ...bars,
      secondaryMetrics: secondaryMetrics(question),
      sample: sample(question.total),
    };
  }

  if (question.type === "matrix_single" || hint === "matrix_stacked") return matrixChart(question);
  if (question.type === "single_choice") return stackedChart(question);

  return {
    id: question.id,
    number: question.number,
    title: question.label,
    kind: "unsupported",
    reason: `Для типа вопроса ${question.type} не найден примитив диаграммы.`,
    sample: sample(question.total),
  };
}

export function surveyQuestionCharts(survey: SurveyView): SurveyQuestionChart[] {
  return survey.questions.map(buildSurveyQuestionChart);
}
