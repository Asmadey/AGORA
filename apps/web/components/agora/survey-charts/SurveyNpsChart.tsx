import { formatMean, formatShare, npsPoints, sharePercent } from "@/lib/survey-charts";

import {
  ChartCard,
  DataDetails,
  Legend,
  TARGET_LABEL,
  TargetNote,
  npsLabel,
  targetUnavailableNote,
  toneColor,
  toneOpacity,
} from "./shared";
import type { SurveyNpsTarget, SurveyNpsValues, SurveySample } from "./types";

export interface SurveyNpsChartProps {
  title: string;
  values: SurveyNpsValues;
  mean?: number | null;
  topBox?: number | null;
  target: SurveyNpsTarget;
  sample: SurveySample;
}

const NPS_PARTS = [
  { id: "promoters", label: "Промоутеры", tone: "positive" as const },
  { id: "neutral", label: "Нейтралы", tone: "neutral" as const },
  { id: "detractors", label: "Детракторы", tone: "negative" as const },
];

function Ring({ values, title }: { values: SurveyNpsValues; title: string }) {
  const parts = [
    { share: values.promoters, tone: "positive" as const },
    { share: values.neutral, tone: "neutral" as const },
    { share: values.detractors, tone: "negative" as const },
  ];
  let offset = 0;
  return (
    <svg
      viewBox="0 0 100 100"
      className="block h-auto w-full max-w-[11rem]"
      role="img"
      aria-label={`${title}: промоутеры ${formatShare(values.promoters)}, нейтралы ${formatShare(values.neutral)}, детракторы ${formatShare(values.detractors)}`}
    >
      <circle cx="50" cy="50" r="36" pathLength="100" fill="none" stroke="var(--surface)" strokeWidth="15" />
      {parts.map((part, index) => {
        const length = sharePercent(part.share) ?? 0;
        const circle = length > 0 ? (
          <circle
            key={NPS_PARTS[index]?.id}
            cx="50"
            cy="50"
            r="36"
            pathLength="100"
            fill="none"
            stroke={toneColor(part.tone)}
            strokeOpacity={toneOpacity(part.tone)}
            strokeWidth="15"
            strokeDasharray={`${length} ${100 - length}`}
            strokeDashoffset={-offset}
            transform="rotate(-90 50 50)"
          />
        ) : null;
        offset += length;
        return circle;
      })}
      <text x="50" y="49" textAnchor="middle" fill="var(--ink)" fontSize="14" fontWeight="700">
        {npsLabel(npsPoints(values.promoters, values.detractors))}
      </text>
      <text x="50" y="59" textAnchor="middle" fill="var(--slate)" fontSize="4.5">NPS</text>
    </svg>
  );
}

export function SurveyNpsChart({ title, values, mean = null, topBox = null, target, sample }: SurveyNpsChartProps) {
  const targetNote = targetUnavailableNote(target);
  const overallNps = npsPoints(values.promoters, values.detractors);
  const targetNps = npsPoints(target.values.promoters, target.values.detractors);

  return (
    <ChartCard
      title={title}
      sample={sample}
      targetN={target.n}
      legend={<Legend items={NPS_PARTS.map(({ label, tone }) => ({ label, tone }))} />}
      note={targetNote}
      table={(
        <DataDetails
          headers={["Показатель", "Общая выборка", TARGET_LABEL]}
          rows={[
            ["NPS", npsLabel(overallNps), targetNote ? targetNote : npsLabel(targetNps)],
            ["Среднее", formatMean(mean), targetNote ? targetNote : formatMean(target.mean ?? null)],
            ["Доля 9-10", formatShare(topBox), targetNote ? targetNote : formatShare(target.topBox ?? null)],
            ...NPS_PARTS.map((part) => [
              part.label,
              formatShare(values[part.id as keyof SurveyNpsValues]),
              targetNote ? targetNote : formatShare(target.values[part.id as keyof SurveyNpsValues]),
            ]),
          ]}
        />
      )}
    >
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(10rem,44%)] items-center gap-4">
        <div className="min-w-0">
          <p className="text-xs text-slate">Индекс готовности рекомендовать</p>
          <p className="mt-1 break-words text-3xl font-bold tabular-nums">{npsLabel(overallNps)}</p>
          <p className="mt-1 text-[11px] text-slate">в процентных пунктах</p>
          <dl className="mt-4 space-y-1 text-xs">
            <div className="flex justify-between gap-3">
              <dt className="text-slate">Среднее</dt>
              <dd className="tabular-nums">{formatMean(mean)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-slate">Доля 9-10</dt>
              <dd className="tabular-nums">{formatShare(topBox)}</dd>
            </div>
          </dl>
        </div>
        <div className="min-w-0">
          <Ring values={values} title={title} />
          <div className="mt-2 grid min-w-0 grid-cols-3 gap-1 text-center">
            {NPS_PARTS.map((part) => (
              <div key={part.id} className="min-w-0">
                <span className="mx-auto block size-2 rounded-full" style={{ backgroundColor: toneColor(part.tone) }} aria-hidden="true" />
                <p className="mt-1 break-words text-[10px] text-slate">{part.label}</p>
                <p className="text-xs font-semibold tabular-nums">{formatShare(values[part.id as keyof SurveyNpsValues])}</p>
                <p className="text-[10px] text-slate">{targetNote ? "—" : formatShare(target.values[part.id as keyof SurveyNpsValues])} ЦА</p>
              </div>
            ))}
          </div>
          {targetNote ? <TargetNote>{targetNote}</TargetNote> : null}
        </div>
      </div>
    </ChartCard>
  );
}
