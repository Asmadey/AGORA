import {
  TRADITIONAL_VALUES,
  valueChartRows,
  valueComparison,
  VCIOM_VALUES_SOURCE,
  type PersonaValuesInput,
  type ValuesByAgeSource,
} from "@/lib/values-chart";

interface ValuesChartProps {
  /** Старый режим для потребителей, которым нужен только список счётчиков. */
  counts?: Record<string, number>;
  /** Новый режим: DNA персон набора сравнивается с возрастным источником. */
  personas?: readonly PersonaValuesInput[];
  source?: ValuesByAgeSource;
  minSampleSize?: number;
}

function percent(value: number): string {
  return `${Math.round(value)}%`;
}

function bar(value: number, color: string) {
  return (
    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-secondary" aria-hidden="true">
      <span
        className={`block h-full rounded-full ${color}`}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}

function LegacyValuesChart({ counts }: { counts: Record<string, number> }) {
  const rows = valueChartRows(counts);

  return (
    <div className="rounded-lg border border-hairline bg-card p-4">
      <p className="flex items-baseline justify-between gap-2 text-xs uppercase tracking-wide text-slate">
        <span>Ценности ВЦИОМ</span>
        <span className="shrink-0 text-[10px] normal-case tracking-normal text-slate/70">
          персон аудитории · из 17
        </span>
      </p>
      <ol className="space-y-[2px]">
        {rows.map((row) => (
          <li key={row.value} className="relative h-[13px] overflow-hidden rounded-sm">
            <span className="absolute inset-0 bg-secondary" aria-hidden="true" />
            <span
              className="absolute inset-y-0 left-0 bg-brand-blue/25"
              style={{ width: `${Math.round(row.share * 100)}%` }}
              aria-hidden="true"
            />
            <span className="relative flex h-full items-center justify-between gap-2 px-1.5">
              <span className="truncate text-[10px] leading-none" title={row.value}>
                {row.value}
              </span>
              <span
                className={`shrink-0 text-[10px] leading-none tabular-nums ${row.count === 0 ? "text-slate" : "font-medium"}`}
              >
                {row.count}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function ComparisonValuesChart({
  personas,
  source,
  minSampleSize,
}: {
  personas: readonly PersonaValuesInput[];
  source: ValuesByAgeSource;
  minSampleSize?: number;
}) {
  const comparison = valueComparison(personas, source, minSampleSize);

  return (
    <div className="rounded-lg border border-hairline bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Ценности аудитории</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate">
            ДНК персон против долей ВЦИОМ, взвешенных по возрастному составу набора.
            Небольшое расхождение ожидаемо: это разные выборки, а не ошибка.
          </p>
        </div>
        <span className="shrink-0 text-xs tabular-nums text-slate">{comparison.sampleSize} персон</span>
      </div>

      {comparison.sampleMessage && (
        <p
          className="mt-3 rounded-md border border-warning/30 bg-warning-soft/60 px-3 py-2 text-xs leading-relaxed text-warning"
          role="status"
        >
          {comparison.sampleMessage}
        </p>
      )}

      {comparison.sampleSize > 0 && (
        <>
          <div className="mt-4 grid grid-cols-[minmax(0,1fr)_minmax(4.5rem,1fr)_minmax(4.5rem,1fr)] gap-x-2 text-[10px] uppercase tracking-wide text-slate">
            <span>Ценность</span>
            <span>В наборе</span>
            <span>В источнике</span>
          </div>
          <ol className="mt-1 space-y-2">
            {comparison.rows.map((row) => (
              <li
                key={row.value}
                className="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(4.5rem,1fr)_minmax(4.5rem,1fr)] gap-x-2"
              >
                <span className="min-w-0 truncate self-end text-xs" title={row.value}>
                  {row.value}
                </span>
                <div className="min-w-0 text-right text-xs tabular-nums">
                  <span>{percent(row.audiencePercent)}</span>
                  {bar(row.audiencePercent, "bg-brand-blue")}
                </div>
                <div className="min-w-0 text-right text-xs tabular-nums">
                  <span>{percent(row.sourcePercent)}</span>
                  {bar(row.sourcePercent, "bg-slate/60")}
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
      <p className="mt-3 text-[11px] leading-relaxed text-slate">
        Источник: {source.source}, {source.respondents} респондентов; возрастной столбец набора: {comparison.sourceBasis}.
        {comparison.outsideListCount > 0
          ? ` Не из канонического списка: ${comparison.outsideListCount} назначений.`
          : ""}
      </p>
    </div>
  );
}

/** Один компонент для набора персон и отчёта; counts оставлен для прежних вызовов. */
export function ValuesChart({
  counts,
  personas,
  source = VCIOM_VALUES_SOURCE,
  minSampleSize,
}: ValuesChartProps) {
  if (personas) {
    return <ComparisonValuesChart personas={personas} source={source} minSampleSize={minSampleSize} />;
  }

  return (
    <LegacyValuesChart
      counts={counts ?? Object.fromEntries(TRADITIONAL_VALUES.map((value) => [value, 0]))}
    />
  );
}
