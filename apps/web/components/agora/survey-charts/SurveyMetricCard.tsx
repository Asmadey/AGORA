import { formatShare } from "@/lib/survey-charts";

import {
  ChartCard,
  DataDetails,
  Legend,
  TARGET_LABEL,
  TargetNote,
  targetUnavailableNote,
} from "./shared";
import type { SurveySample, SurveyTargetBase } from "./types";

export interface SurveyMetricCardProps {
  title: string;
  value: number | null;
  caption: string;
  target: SurveyTargetBase & { value: number | null };
  sample: SurveySample;
  note?: string;
}

export function SurveyMetricCard({ title, value, caption, target, sample, note }: SurveyMetricCardProps) {
  const targetNote = targetUnavailableNote(target);
  return (
    <ChartCard
      title={title}
      sample={sample}
      targetN={target.n}
      legend={<Legend items={[{ label: "Общая выборка", tone: "positive" }, { label: TARGET_LABEL, tone: "slice" }]} />}
      note={targetNote ?? note ?? null}
      table={(
        <DataDetails
          headers={["Показатель", "Общая выборка", TARGET_LABEL]}
          rows={[[caption, formatShare(value), targetNote ? targetNote : formatShare(target.value)]]}
        />
      )}
    >
      <div className="min-w-0">
        <p className="break-words text-4xl font-bold tabular-nums">{formatShare(value)}</p>
        <p className="mt-1 max-w-prose break-words text-sm leading-relaxed">{caption}</p>
        <div className="mt-4 border-t border-hairline pt-3">
          <p className="text-xs text-slate">Показатель среди {TARGET_LABEL}</p>
          {targetNote ? (
            <TargetNote>{targetNote}</TargetNote>
          ) : (
            <p className="mt-1 break-words text-xl font-semibold tabular-nums">{formatShare(target.value)}</p>
          )}
        </div>
      </div>
    </ChartCard>
  );
}
