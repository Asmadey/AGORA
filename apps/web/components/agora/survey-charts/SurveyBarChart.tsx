import { barLengthPercent, formatShare, maxMeasuredShare } from "@/lib/survey-charts";

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
import type { SurveyBarRow, SurveyBarTarget, SurveySample } from "./types";

export interface SurveyBarChartProps {
  title: string;
  note?: string;
  rows: readonly SurveyBarRow[];
  target: SurveyBarTarget;
  sample: SurveySample;
}

function barValueLabel(row: { share: number | null; count?: number | null }): string {
  const share = formatShare(row.share);
  return row.count === undefined ? share : `${row.count ?? "—"} · ${share}`;
}

function BarValue({ row, max }: { row: SurveyBarRow; max: number }) {
  const width = row.share === null ? 0 : barLengthPercent(row.share, max);
  return (
    <div className="min-w-0">
      <div className="flex min-w-0 items-center gap-2">
        <div className="h-5 min-w-0 flex-1 overflow-hidden rounded-sm bg-surface" aria-hidden="true">
          {row.share !== null ? (
            <span
              className="block h-full rounded-sm"
              style={{
                width: `${width}%`,
                backgroundColor: toneColor(row.service ? "unknown" : row.tone === "key" ? "key" : "bar"),
                opacity: toneOpacity(row.service ? "unknown" : row.tone === "key" ? "key" : "bar"),
              }}
            />
          ) : null}
        </div>
        <span className="w-20 shrink-0 text-right text-xs tabular-nums">{barValueLabel(row)}</span>
      </div>
    </div>
  );
}

export function SurveyBarChart({ title, note, rows, target, sample }: SurveyBarChartProps) {
  const overallMax = maxMeasuredShare(rows.map((row) => row.share));
  const targetMax = maxMeasuredShare(target.rows.map((row) => row.share));
  const targetNote = targetUnavailableNote(target);
  const targetById = new Map(target.rows.map((row) => [row.id, row]));

  return (
    <ChartCard
      title={title}
      sample={sample}
      targetN={target.n}
      legend={<Legend items={[{ label: "Общая выборка", tone: "bar" }, { label: "Ключевой вариант", tone: "key" }, { label: TARGET_LABEL, tone: "slice" }]} />}
      note={targetNote ?? note ?? null}
      table={(
        <DataDetails
          headers={["Вариант", "Общая выборка", TARGET_LABEL]}
          rows={rows.map((row) => [
            row.label,
            barValueLabel(row),
            targetNote ? targetNote : barValueLabel(targetById.get(row.id) ?? { share: null }),
          ])}
        />
      )}
    >
      <div className={`grid min-w-0 gap-x-3 gap-y-2 ${targetNote ? "grid-cols-[minmax(0,1fr)_minmax(8rem,32%)]" : "grid-cols-[minmax(0,1fr)_minmax(8rem,32%)]"}`}>
        <div className="text-[10px] uppercase tracking-wide text-slate">Вариант</div>
        <div className="text-[10px] uppercase tracking-wide text-slate">Общая / ЦА</div>
        {rows.map((row) => {
          const targetRow = targetById.get(row.id);
          return (
            <div key={row.id} className="contents">
              <div className={`min-w-0 self-center break-words text-xs leading-snug ${row.service ? "text-slate" : ""}`}>{row.label}</div>
              <div className="min-w-0 space-y-1">
                <BarValue row={row} max={overallMax} />
                {targetNote ? (
                  <TargetNote>{targetNote}</TargetNote>
                ) : (
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-sm bg-surface" aria-hidden="true">
                      {targetRow?.share !== null && targetRow?.share !== undefined ? (
                        <span
                          className="block h-full rounded-sm bg-brand-teal"
                          style={{ width: `${barLengthPercent(targetRow.share, targetMax)}%` }}
                        />
                      ) : null}
                    </div>
                    <span className="w-20 shrink-0 text-right text-[11px] tabular-nums">
                      {barValueLabel(targetRow ?? { share: null })}
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </ChartCard>
  );
}
