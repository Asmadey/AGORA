import type { CSSProperties, ReactNode } from "react";

import {
  formatShare,
} from "@/lib/survey-charts";

import type { SurveySample, SurveyTone } from "./types";

export { targetUnavailableNote } from "@/lib/survey-charts";

export const TARGET_LABEL = "14-35";

export const printSafeStyle: CSSProperties = {
  printColorAdjust: "exact",
  WebkitPrintColorAdjust: "exact",
};

const TONE_COLORS: Record<SurveyTone, string> = {
  positive: "var(--success)",
  "positive-soft": "var(--success)",
  negative: "var(--danger)",
  "negative-soft": "var(--brand-coral)",
  neutral: "var(--brand-yellow)",
  unknown: "var(--stone)",
  scale: "var(--success)",
  bar: "var(--brand-blue)",
  key: "var(--brand-blue)",
  slice: "var(--brand-teal)",
};

const TONE_OPACITY: Record<SurveyTone, number> = {
  positive: 1,
  "positive-soft": 0.45,
  negative: 1,
  "negative-soft": 1,
  neutral: 1,
  unknown: 1,
  scale: 1,
  bar: 0.3,
  key: 1,
  slice: 1,
};

export function toneColor(tone: SurveyTone): string {
  return TONE_COLORS[tone];
}

export function toneOpacity(tone: SurveyTone): number {
  return TONE_OPACITY[tone];
}

export function toneStyle(tone: SurveyTone): CSSProperties {
  return { backgroundColor: toneColor(tone), opacity: toneOpacity(tone) };
}

export function sampleText(sample: SurveySample): string {
  if (sample.notAsked) return "вопрос не задавался";
  const answered = sample.answered === null ? "—" : String(sample.answered);
  const surveyed = sample.surveyed === null ? "—" : String(sample.surveyed);
  const excluded = sample.excluded === null || sample.excluded === 0
    ? ""
    : ` · исключено ${sample.excluded}`;
  return `ответили ${answered} из ${surveyed}${excluded}`;
}

export function ChartCard({
  title,
  sample,
  children,
  legend,
  note,
  table,
  targetN,
}: {
  title: string;
  sample: SurveySample;
  children: ReactNode;
  legend?: ReactNode;
  note?: string | null;
  table: ReactNode;
  targetN?: number | null;
}) {
  return (
    <article
      className="min-w-0 max-w-full overflow-hidden rounded-lg border border-hairline bg-card p-4 text-ink"
      style={printSafeStyle}
    >
      <header className="min-w-0">
        <h2 className="break-words text-sm font-semibold leading-snug">{title}</h2>
        <p className="mt-1 text-[11px] uppercase tracking-wide text-slate">
          в % от опрошенных · {sampleText(sample)}
          {targetN !== undefined ? " · " + TARGET_LABEL + ": n=" + (targetN ?? "—") : ""}
        </p>
      </header>
      <div className="mt-4 min-w-0">{children}</div>
      {legend ? <div className="mt-3 min-w-0">{legend}</div> : null}
      {note ? (
        <p className="mt-3 break-words rounded-md border border-warning/30 bg-warning-soft/60 px-3 py-2 text-xs leading-relaxed text-warning">
          {note}
        </p>
      ) : null}
      <div className="mt-3 min-w-0">{table}</div>
    </article>
  );
}

export function Legend({
  items,
}: {
  items: readonly { label: string; tone: SurveyTone }[];
}) {
  return (
    <div className="flex min-w-0 flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate" aria-label="Легенда">
      {items.map((item) => (
        <span key={item.label} className="inline-flex min-w-0 items-center gap-1.5">
          <span className="size-2.5 shrink-0 rounded-full" style={toneStyle(item.tone)} aria-hidden="true" />
          <span className="break-words">{item.label}</span>
        </span>
      ))}
    </div>
  );
}

export function DataDetails({
  caption = "Таблица данных",
  headers,
  rows,
}: {
  caption?: string;
  headers: readonly string[];
  rows: readonly (readonly ReactNode[])[];
}) {
  return (
    <details className="min-w-0 text-xs">
      <summary className="cursor-pointer text-slate underline decoration-hairline-strong underline-offset-2">
        {caption}
      </summary>
      <div className="mt-2 max-w-full overflow-x-auto">
        <table className="w-full min-w-0 border-collapse text-left">
          <thead>
            <tr>
              {headers.map((header) => (
                <th key={header} className="border-b border-hairline px-2 py-1 font-medium text-slate">
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="border-b border-hairline-soft px-2 py-1 align-top tabular-nums">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export function TargetLabel({ children }: { children: ReactNode }) {
  return <span className="text-[11px] text-slate">{children}</span>;
}

export function TargetNote({ children }: { children: ReactNode }) {
  return <p className="break-words text-xs leading-relaxed text-slate">{children}</p>;
}

export function npsLabel(value: number | null): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : ""}${value} п.п.`;
}

export function targetShareLabel(share: number | null): string {
  return formatShare(share);
}
