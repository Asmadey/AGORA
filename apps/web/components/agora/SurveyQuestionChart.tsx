import {
  SurveyBarChart,
  SurveyMatrixChart,
  SurveyNpsChart,
  SurveyScaleChart,
  SurveyStackedBarChart,
} from "./survey-charts";
import type { SurveyQuestionChart } from "@/lib/report-survey-charts";

function questionTitle(chart: SurveyQuestionChart): string {
  return chart.number === null ? chart.title : `${chart.number}. ${chart.title}`;
}

function OpenQuestionBlock({ chart }: { chart: Extract<SurveyQuestionChart, { kind: "open" }> }) {
  return (
    <article className="rounded-lg border border-hairline bg-card p-4">
      <h4 className="text-sm font-medium">{questionTitle(chart)}</h4>
      <p className="mt-1 text-[11px] text-slate">
        Ответили: {chart.sample.answered ?? "—"} из {chart.sample.surveyed ?? "—"} · в срезе: {chart.target.n ?? "—"}
      </p>
      {chart.texts.length > 0 ? (
        <ul className="mt-3 space-y-2 text-sm leading-relaxed">
          {chart.texts.map((text, index) => <li key={`${index}-${text}`}>«{text}»</li>)}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-slate">Текстовых ответов нет.</p>
      )}
      <div className="mt-4 border-t border-hairline pt-3">
        <p className="text-[11px] uppercase tracking-wide text-slate">Ответы в срезе</p>
        {chart.targetTexts === null ? (
          <p className="mt-1 text-sm text-slate">Тексты по срезу не считались.</p>
        ) : chart.targetTexts.length > 0 ? (
          <ul className="mt-2 space-y-2 text-sm leading-relaxed">
            {chart.targetTexts.map((text, index) => <li key={String(index) + text}>«{text}»</li>)}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-slate">Текстовых ответов нет.</p>
        )}
      </div>
    </article>
  );
}

export function SurveyQuestionChart({ chart }: { chart: SurveyQuestionChart }) {
  if (chart.kind === "open") return <OpenQuestionBlock chart={chart} />;
  if (chart.kind === "unsupported") {
    return (
      <article className="rounded-lg border border-dashed border-hairline bg-card p-4 text-sm text-slate">
        <h4 className="font-medium text-ink">{questionTitle(chart)}</h4>
        <p className="mt-2">{chart.reason}</p>
      </article>
    );
  }

  const title = questionTitle(chart);
  if (chart.kind === "bar") {
    return <SurveyBarChart title={title} rows={chart.rows} target={chart.target} sample={chart.sample} />;
  }
  if (chart.kind === "stacked") {
    return <SurveyStackedBarChart title={title} parts={chart.parts} target={chart.target} sample={chart.sample} />;
  }
  if (chart.kind === "matrix") {
    return <SurveyMatrixChart title={title} groups={chart.groups} targetN={chart.targetN} sample={chart.sample} />;
  }
  if (chart.kind === "nps") {
    return (
      <SurveyNpsChart
        title={title}
        values={chart.values}
        mean={chart.mean}
        topBox={chart.topBox}
        target={chart.target}
        sample={chart.sample}
      />
    );
  }
  return (
    <SurveyScaleChart
      title={title}
      mean={chart.mean}
      min={chart.min}
      max={chart.max}
      topBox={chart.topBox}
      minLabel={chart.minLabel}
      maxLabel={chart.maxLabel}
      groups={chart.groups}
      target={chart.target}
      sample={chart.sample}
    />
  );
}
