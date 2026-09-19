import { formatShare } from "@/lib/survey-charts";

import { ChartCard, DataDetails, Legend, TARGET_LABEL, TargetNote, targetUnavailableNote } from "./shared";
import { SurveyStackedBarChart } from "./SurveyStackedBarChart";
import type { SurveyMatrixGroup, SurveySample } from "./types";

export interface SurveyMatrixChartProps {
  title: string;
  groups: readonly SurveyMatrixGroup[];
  sample: SurveySample;
}

export function SurveyMatrixChart({ title, groups, sample }: SurveyMatrixChartProps) {
  const rows = groups.flatMap((group) => group.rows);
  return (
    <ChartCard
      title={title}
      sample={sample}
      legend={<Legend items={[{ label: "Общая выборка", tone: "positive" }, { label: TARGET_LABEL, tone: "slice" }]} />}
      table={(
        <DataDetails
          headers={["Показатель", "Общая выборка", TARGET_LABEL]}
          rows={rows.map((row) => [
            row.label,
            row.parts.map((part) => `${part.label}: ${formatShare(part.share)}`).join(" · "),
            targetUnavailableNote(row.target) ?? `${row.target.count ?? "—"} / ${formatShare(row.target.share)}`,
          ])}
        />
      )}
    >
      <div className="min-w-0 space-y-4">
        {groups.map((group) => (
          <section key={group.id} className="min-w-0">
            <h3 className="mb-2 break-words rounded-md bg-surface px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate">
              {group.title}
            </h3>
            <div className="min-w-0 space-y-3">
              {group.rows.map((row) => {
                const targetNote = targetUnavailableNote(row.target);
                return (
                  <div key={row.id} className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(7rem,31%)] gap-3 border-b border-hairline-soft pb-3 last:border-b-0 last:pb-0">
                    <SurveyStackedBarChart
                      embedded
                      title={row.label}
                      parts={row.parts}
                      sample={sample}
                    />
                    <aside className="min-w-0 border-l border-hairline pl-3">
                      <p className="text-[11px] text-slate">{TARGET_LABEL}</p>
                      {targetNote ? (
                        <TargetNote>{targetNote}</TargetNote>
                      ) : (
                        <p className="mt-1 break-words text-xs font-semibold tabular-nums">
                          {row.target.count ?? "—"} / {formatShare(row.target.share)}
                        </p>
                      )}
                    </aside>
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </ChartCard>
  );
}
