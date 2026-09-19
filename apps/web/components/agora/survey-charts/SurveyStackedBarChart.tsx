import { formatShare, stackedSegments } from "@/lib/survey-charts";

import {
  ChartCard,
  DataDetails,
  Legend,
  TARGET_LABEL,
  TargetNote,
  targetUnavailableNote,
  toneColor,
  toneOpacity,
} from "./shared";
import type { SurveySample, SurveyStackedPart, SurveyStackedTarget } from "./types";

export interface SurveyStackedBarChartProps {
  title: string;
  parts: readonly SurveyStackedPart[];
  target?: SurveyStackedTarget | null;
  sample: SurveySample;
  note?: string;
  embedded?: boolean;
}

export function StackedBarSvg({
  title,
  parts,
}: {
  title: string;
  parts: readonly SurveyStackedPart[];
}) {
  const result = stackedSegments(parts);
  return (
    <svg
      viewBox="0 0 100 28"
      className="block h-auto w-full max-w-full"
      role="img"
      aria-label={`${title}: ${parts.map((part) => `${part.label} ${formatShare(part.share)}`).join(", ")}`}
    >
      <rect x="0" y="3" width="100" height="17" rx="2" fill="var(--surface)" />
      {result.segments.map((segment) => {
        const part = parts.find((candidate) => candidate.id === segment.id);
        const tone = segment.remainder ? "unknown" : part?.tone ?? "unknown";
        if (segment.length <= 0) return null;
        return (
          <g key={segment.id}>
            <rect
              x={segment.offset * 100}
              y="3"
              width={segment.length * 100}
              height="17"
              fill={toneColor(tone)}
              fillOpacity={segment.remainder ? 0.7 : toneOpacity(tone)}
            />
            <text
              x={(segment.offset + segment.length / 2) * 100}
              y="14"
              textAnchor="middle"
              dominantBaseline="middle"
              fill={segment.remainder || tone === "neutral" ? "var(--ink)" : "var(--canvas)"}
              fontSize={segment.length < 0.08 ? "2.8" : "4.2"}
              fontWeight="600"
            >
              {formatShare(segment.share)}
            </text>
          </g>
        );
      })}
      <line x1="0" x2="0" y1="23" y2="26" stroke="var(--hairline-strong)" strokeWidth="0.6" />
      <line x1="100" x2="100" y1="23" y2="26" stroke="var(--hairline-strong)" strokeWidth="0.6" />
      <text x="0" y="28" fill="var(--slate)" fontSize="3.2" textAnchor="start">100%</text>
      <text x="100" y="28" fill="var(--slate)" fontSize="3.2" textAnchor="end">100%</text>
    </svg>
  );
}

function StackedBody({ title, parts }: Pick<SurveyStackedBarChartProps, "title" | "parts">) {
  const result = stackedSegments(parts);
  return (
    <>
      <StackedBarSvg title={title} parts={parts} />
      <div className="mt-2 grid min-w-0 grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate">
        {result.segments.map((segment) => {
          const part = parts.find((candidate) => candidate.id === segment.id);
          const tone = segment.remainder ? "unknown" : part?.tone ?? "unknown";
          return (
            <span key={segment.id} className="inline-flex min-w-0 items-center gap-1.5">
              <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: toneColor(tone), opacity: toneOpacity(tone) }} aria-hidden="true" />
              <span className="min-w-0 break-words">{segment.label}: {formatShare(segment.share)}</span>
            </span>
          );
        })}
      </div>
    </>
  );
}

export function SurveyStackedBarChart({
  title,
  parts,
  target,
  sample,
  note,
  embedded = false,
}: SurveyStackedBarChartProps) {
  const targetNote = targetUnavailableNote(target);
  const targetRows = target?.parts ?? [];
  const targetById = new Map(targetRows.map((part) => [part.id, part]));
  const table = (
    <DataDetails
      headers={["Вариант", "Общая выборка", TARGET_LABEL]}
      rows={parts.map((part) => [
        part.label,
        formatShare(part.share),
        targetNote ? targetNote : formatShare(targetById.get(part.id)?.share ?? null),
      ])}
    />
  );

  if (embedded) {
    return (
      <div className="min-w-0">
        <p className="mb-1 break-words text-xs font-medium">{title}</p>
        <StackedBody title={title} parts={parts} />
        <div className="mt-2">{table}</div>
      </div>
    );
  }

  return (
    <ChartCard
      title={title}
      sample={sample}
      targetN={target?.n}
      legend={<Legend items={parts.map((part) => ({ label: part.label, tone: part.tone }))} />}
      note={targetNote ?? note ?? null}
      table={table}
    >
      <div className="min-w-0">
        <StackedBody title={title} parts={parts} />
        {target ? (
          <div className="mt-4 min-w-0 border-t border-hairline pt-3">
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span className="text-slate">{TARGET_LABEL}</span>
              <span className="tabular-nums">
                {targetNote ? "—" : formatShare(target.parts.reduce((sum, part) => sum + (part.share ?? 0), 0))}
              </span>
            </div>
            {targetNote ? <TargetNote>{targetNote}</TargetNote> : <StackedBody title={`${title}, ${TARGET_LABEL}`} parts={target.parts as SurveyStackedPart[]} />}
          </div>
        ) : null}
      </div>
    </ChartCard>
  );
}
