import {
  formatMean,
  formatShare,
  scaleFillPercent,
  sharePercent,
} from "@/lib/survey-charts";

import {
  ChartCard,
  DataDetails,
  Legend,
  TARGET_LABEL,
  TargetLabel,
  TargetNote,
  targetUnavailableNote,
  toneColor,
} from "./shared";
import type { SurveySample, SurveyScaleTarget } from "./types";

export interface SurveyScaleChartProps {
  title: string;
  mean: number | null;
  min: number;
  max: number;
  topBox: number | null;
  minLabel: string;
  maxLabel: string;
  target: SurveyScaleTarget;
  sample: SurveySample;
}

export function SurveyScaleChart({
  title,
  mean,
  min,
  max,
  topBox,
  minLabel,
  maxLabel,
  target,
  sample,
}: SurveyScaleChartProps) {
  const fill = scaleFillPercent(mean, min, max);
  const targetNote = targetUnavailableNote(target);
  const topBoxFill = sharePercent(topBox);
  const ticks = Array.from({ length: 6 }, (_, index) => index * 20);

  return (
    <ChartCard
      title={title}
      sample={sample}
      legend={<Legend items={[{ label: "Общая выборка", tone: "scale" }, { label: TARGET_LABEL, tone: "slice" }]} />}
      note={targetNote}
      table={(
        <DataDetails
          headers={["Показатель", "Общая выборка", TARGET_LABEL]}
          rows={[
            ["Среднее", formatMean(mean), targetNote ? targetNote : formatMean(target.mean)],
            ["Доля 8-10", formatShare(topBox), targetNote ? targetNote : formatShare(target.topBox)],
          ]}
        />
      )}
    >
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(6.5rem,30%)] items-start gap-4">
        <div className="min-w-0">
          <svg
            viewBox="0 0 100 36"
            className="block h-auto w-full max-w-full"
            role="img"
            aria-label={`${title}: среднее ${formatMean(mean)} по шкале от ${min} до ${max}`}
          >
            <rect x="0" y="10" width="100" height="12" rx="2" fill="var(--surface)" />
            {fill !== null && fill > 0 ? (
              <rect x="0" y="10" width={fill} height="12" rx="2" fill={toneColor("scale")} />
            ) : null}
            {ticks.map((tick) => (
              <line
                key={tick}
                x1={tick}
                x2={tick}
                y1="25"
                y2="29"
                stroke="var(--hairline-strong)"
                strokeWidth="0.6"
              />
            ))}
            <text
              x={fill === null ? 2 : Math.max(2, Math.min(98, fill - (fill > 14 ? 2 : -2)))}
              y="18.5"
              textAnchor={fill !== null && fill > 14 ? "end" : "start"}
              dominantBaseline="middle"
              fill={fill !== null && fill > 14 ? "var(--canvas)" : "var(--ink)"}
              fontSize="5"
              fontWeight="700"
            >
              {formatMean(mean)}
            </text>
            <text x="0" y="34" fill="var(--slate)" fontSize="3.5" textAnchor="start">
              {min}
            </text>
            <text x="100" y="34" fill="var(--slate)" fontSize="3.5" textAnchor="end">
              {max}
            </text>
          </svg>
          <div className="mt-1 flex min-w-0 justify-between gap-2 text-[10px] leading-tight text-slate">
            <span className="min-w-0 break-words">{minLabel}</span>
            <span className="min-w-0 break-words text-right">{maxLabel}</span>
          </div>
          <div className="mt-4 min-w-0">
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span className="break-words">Доля 8-10</span>
              <span className="shrink-0 tabular-nums">{formatShare(topBox)}</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-surface" aria-hidden="true">
              {topBoxFill !== null ? (
                <span className="block h-full rounded-full bg-success" style={{ width: `${topBoxFill}%` }} />
              ) : null}
            </div>
          </div>
        </div>
        <aside className="min-w-0 border-l border-hairline pl-3">
          <TargetLabel>Показатель в ЦА</TargetLabel>
          <p className="mt-1 break-words text-sm font-semibold tabular-nums">
            {targetNote ? "—" : formatMean(target.mean)}
          </p>
          <p className="mt-1 break-words text-[11px] leading-relaxed text-slate">{TARGET_LABEL}</p>
          {targetNote ? <TargetNote>{targetNote}</TargetNote> : null}
        </aside>
      </div>
    </ChartCard>
  );
}
