import { donutSegments, formatShare } from "@/lib/survey-charts";

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
import type { SurveyDonutTarget, SurveyPart, SurveySample, SurveySecondaryMetric } from "./types";

export interface SurveyDonutChartProps {
  title: string;
  parts: readonly SurveyPart[];
  center: { share: number | null; caption: string };
  secondary?: SurveySecondaryMetric;
  target: SurveyDonutTarget;
  sample: SurveySample;
}

function DonutSvg({
  title,
  parts,
  center,
  secondary,
}: Pick<SurveyDonutChartProps, "title" | "parts" | "center" | "secondary">) {
  const result = donutSegments(parts);
  return (
    <svg
      viewBox="0 0 100 100"
      className="block h-auto w-full max-w-[12rem]"
      role="img"
      aria-label={`${title}: ${formatShare(center.share)} ${center.caption}`}
    >
      <circle cx="50" cy="50" r="36" pathLength="100" fill="none" stroke="var(--surface)" strokeWidth="15" />
      {result.segments.map((segment) => {
        const part = parts.find((candidate) => candidate.id === segment.id);
        if (!part || segment.missing || segment.length <= 0) return null;
        return (
          <circle
            key={segment.id}
            cx="50"
            cy="50"
            r="36"
            pathLength="100"
            fill="none"
            stroke={toneColor(part.tone)}
            strokeOpacity={toneOpacity(part.tone)}
            strokeWidth="15"
            strokeDasharray={`${segment.length} ${100 - segment.length}`}
            strokeDashoffset={-segment.offset}
            transform="rotate(-90 50 50)"
          />
        );
      })}
      <text x="50" y="47" textAnchor="middle" fill="var(--ink)" fontSize="15" fontWeight="700">
        {formatShare(center.share)}
      </text>
      <text x="50" y="57" textAnchor="middle" fill="var(--slate)" fontSize="4.2">
        {center.caption}
      </text>
      {secondary ? (
        <text x="50" y="66" textAnchor="middle" fill="var(--slate)" fontSize="4.8" fontWeight="600">
          {formatShare(secondary.share)} {secondary.caption}
        </text>
      ) : null}
    </svg>
  );
}

function PartStrip({ parts }: { parts: readonly SurveyPart[] }) {
  const result = donutSegments(parts);
  return (
    <div className="mt-3 flex h-2 w-full overflow-hidden rounded-full bg-surface" aria-hidden="true">
      {result.segments.map((segment) => {
        const part = parts.find((candidate) => candidate.id === segment.id);
        return part && !segment.missing && segment.length > 0 ? (
          <span
            key={segment.id}
            className="block h-full"
            style={{ width: `${segment.length}%`, backgroundColor: toneColor(part.tone), opacity: toneOpacity(part.tone) }}
          />
        ) : null;
      })}
    </div>
  );
}

export function SurveyDonutChart({
  title,
  parts,
  center,
  secondary,
  target,
  sample,
}: SurveyDonutChartProps) {
  const result = donutSegments(parts);
  const targetNote = targetUnavailableNote(target);
  const dataNote = result.exceedsTotal
    ? `Доли кольца составляют ${formatShare(result.totalShare)} и были нормированы для отрисовки.`
    : result.hasGap
      ? `Доли кольца составляют ${formatShare(result.totalShare)}; остаток не был распределён между ответами.`
      : null;

  return (
    <ChartCard
      title={title}
      sample={sample}
      targetN={target.n}
      legend={<Legend items={parts.map((part) => ({ label: part.label, tone: part.tone }))} />}
      note={targetNote ?? dataNote}
      table={(
        <DataDetails
          headers={["Вариант", "Общая выборка", TARGET_LABEL]}
          rows={parts.map((part) => {
            const targetPart = target.parts.find((candidate) => candidate.id === part.id);
            return [part.label, formatShare(part.share), targetNote ? targetNote : formatShare(targetPart?.share ?? null)];
          })}
        />
      )}
    >
      <div className="grid min-w-0 grid-cols-[minmax(0,12rem)_minmax(0,1fr)] items-center gap-4">
        <div className="min-w-0">
          <DonutSvg title={title} parts={parts} center={center} secondary={secondary} />
          <PartStrip parts={targetNote ? parts.map((part) => ({ ...part, share: null })) : target.parts} />
          <p className="mt-1 text-center text-[10px] text-slate">{TARGET_LABEL}</p>
        </div>
        <div className="min-w-0 space-y-2">
          {parts.map((part) => (
            <div key={part.id} className="flex min-w-0 items-start gap-2 text-xs">
              <span className="mt-1 size-2.5 shrink-0 rounded-full" style={{ backgroundColor: toneColor(part.tone), opacity: toneOpacity(part.tone) }} aria-hidden="true" />
              <span className="min-w-0 flex-1 break-words">{part.label}</span>
              <span className="shrink-0 tabular-nums">{formatShare(part.share)}</span>
            </div>
          ))}
          <div className="border-t border-hairline pt-2 text-xs">
            <span className="text-slate">{center.caption}: </span>
            <span className="font-semibold tabular-nums">{formatShare(center.share)}</span>
            {secondary ? <span className="ml-2 text-slate">{secondary.caption}: {formatShare(secondary.share)}</span> : null}
          </div>
          {targetNote ? <TargetNote>{targetNote}</TargetNote> : null}
        </div>
      </div>
    </ChartCard>
  );
}
