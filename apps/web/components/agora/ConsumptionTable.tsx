"use client";

import { useCallback, useEffect, useState } from "react";

import {
  MODEL_LABELS,
  formatDateRu,
  presetRange,
  type DayRow,
  type Preset,
  type Totals,
} from "@/lib/consumption";

/**
 * Таблица потребления и расходов (раздел «Статистика»).
 *
 * ─── Почему итоги считает сервер, а не эта таблица ────────────────────────
 * Суммы приходят вместе со строками и посчитаны ПО ТЕМ ЖЕ строкам. Считать их
 * здесь заново значит завести вторую арифметику: при первом же расхождении
 * (округление, фильтр, пропущенная строка) экран покажет две правды и не
 * скажет, какая из них верна.
 *
 * ─── Что делает фильтр по модели ──────────────────────────────────────────
 * Прячет колонки и пересчитывает «Итого» по видимым — то есть отвечает на
 * вопрос «сколько стоила вот эта модель». Он НЕ фильтрует данные на сервере:
 * период один и тот же, меняется только то, что показано.
 */

type ModelFilter = "all" | "vision" | "text";

const NUMBER = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const TOKENS = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});

const rub = (v: number) => `${NUMBER.format(v)} ₽`;

export function ConsumptionTable() {
  const initial = presetRange("month");
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  /**
   * Что выбрано в списке справа: готовый период или «Период» с датами.
   *
   * Датапикеры показываются ТОЛЬКО в режиме «Период». В готовых режимах они
   * показывали бы даты, которых человек не выбирал, и правка любой из них молча
   * противоречила бы подписи в списке.
   */
  const [range, setRange] = useState<Preset | "custom">("month");
  const [filter, setFilter] = useState<ModelFilter>("all");
  const [rows, setRows] = useState<DayRow[] | null>(null);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (a: string, b: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/consumption?from=${a}&to=${b}`);
      const data = (await res.json()) as {
        rows?: DayRow[];
        totals?: Totals;
        error?: string;
      };
      if (!res.ok) {
        setError(data.error ?? "не удалось получить расходы");
        setRows(null);
        return;
      }
      setRows(data.rows ?? []);
      setTotals(data.totals ?? null);
    } catch {
      setError("сервер не ответил");
      setRows(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(from, to);
  }, [from, to, load]);

  const applyPreset = (preset: Preset) => {
    const r = presetRange(preset);
    setFrom(r.from);
    setTo(r.to);
  };

  const showVision = filter === "all" || filter === "vision";
  const showText = filter === "all" || filter === "text";

  /** «Итого» строки — по ВИДИМЫМ колонкам, иначе фильтр ничего не отвечает. */
  const rowTotal = (r: DayRow) =>
    (showVision ? r.vision.rub : 0) + (showText ? r.text.rub : 0) + (filter === "all" ? r.other.rub : 0);

  const sumTotal = totals
    ? (showVision ? totals.vision.rub : 0) +
      (showText ? totals.text.rub : 0) +
      (filter === "all" ? totals.other.rub : 0)
    : 0;
  const sumTotalNoVat = totals
    ? (showVision ? totals.vision.rubNoVat : 0) +
      (showText ? totals.text.rubNoVat : 0) +
      (filter === "all" ? totals.other.rubNoVat : 0)
    : 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {(
            [
              { v: "all", t: "Обе модели" },
              { v: "vision", t: "Только vision" },
              { v: "text", t: "Только текстовая" },
            ] as const
          ).map((o) => (
            <button
              key={o.v}
              onClick={() => setFilter(o.v)}
              className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${
                filter === o.v ? "border-ink bg-secondary" : "border-hairline hover:bg-secondary"
              }`}
            >
              {o.t}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-end gap-2">
          {/* Датапикеры СЛЕВА от списка и только в режиме «Период». */}
          {range === "custom" && (
            <>
              <label className="text-xs text-slate">
                с
                <input
                  type="date"
                  value={from}
                  max={to}
                  onChange={(e) => setFrom(e.target.value)}
                  className="ml-1.5 rounded-md border border-hairline bg-card px-2 py-1.5 text-sm text-foreground"
                />
              </label>
              <label className="text-xs text-slate">
                по
                <input
                  type="date"
                  value={to}
                  min={from}
                  onChange={(e) => setTo(e.target.value)}
                  className="ml-1.5 rounded-md border border-hairline bg-card px-2 py-1.5 text-sm text-foreground"
                />
              </label>
            </>
          )}

          <select
            value={range}
            onChange={(e) => {
              const value = e.target.value as Preset | "custom";
              setRange(value);
              // При переходе в «Период» границы остаются теми, что показаны:
              // человек уточняет видимый период, а не начинает с пустого места.
              if (value !== "custom") applyPreset(value);
            }}
            className="rounded-md border border-hairline bg-card px-3 py-1.5 text-sm"
            aria-label="Период"
          >
            <option value="7d">Последние 7 дней</option>
            <option value="month">Текущий месяц</option>
            <option value="custom">Период</option>
          </select>
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-warning/30 bg-warning-soft/60 p-3 text-sm text-warning">
          {error}
        </p>
      )}

      {loading && !rows && <p className="text-sm text-slate">Считаю расходы…</p>}

      {rows && rows.length === 0 && !error && (
        <p className="text-sm text-slate">За выбранный период расходов нет.</p>
      )}

      {rows && rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-hairline">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-secondary/60 text-left text-xs uppercase tracking-wide text-slate">
                <th className="px-4 py-3 font-medium">Дата</th>
                {showVision && (
                  <>
                    <th className="px-4 py-3 text-right font-medium">
                      Vision Model<span className="block font-normal normal-case">объём, млн токенов</span>
                    </th>
                    <th className="px-4 py-3 text-right font-medium">
                      Vision Model<span className="block font-normal normal-case">с НДС, ₽</span>
                    </th>
                  </>
                )}
                {showText && (
                  <>
                    <th className="px-4 py-3 text-right font-medium">
                      LLM text<span className="block font-normal normal-case">объём, млн токенов</span>
                    </th>
                    <th className="px-4 py-3 text-right font-medium">
                      LLM text<span className="block font-normal normal-case">с НДС, ₽</span>
                    </th>
                  </>
                )}
                <th className="px-4 py-3 text-right font-medium">Итого</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.date} className="border-t border-hairline">
                  <td className="px-4 py-2.5 font-mono text-xs tabular-nums">{formatDateRu(r.date)}</td>
                  {showVision && (
                    <>
                      <td className="px-4 py-2.5 text-right tabular-nums">{TOKENS.format(r.vision.tokens)}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{rub(r.vision.rub)}</td>
                    </>
                  )}
                  {showText && (
                    <>
                      <td className="px-4 py-2.5 text-right tabular-nums">{TOKENS.format(r.text.tokens)}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{rub(r.text.rub)}</td>
                    </>
                  )}
                  <td className="px-4 py-2.5 text-right font-semibold tabular-nums">{rub(rowTotal(r))}</td>
                </tr>
              ))}
            </tbody>
            {totals && (
              <tfoot>
                <tr className="border-t-2 border-hairline-strong bg-secondary/40 font-semibold">
                  <td className="px-4 py-3">ИТОГО</td>
                  {showVision && (
                    <>
                      <td className="px-4 py-3 text-right tabular-nums">{TOKENS.format(totals.vision.tokens)}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{rub(totals.vision.rub)}</td>
                    </>
                  )}
                  {showText && (
                    <>
                      <td className="px-4 py-3 text-right tabular-nums">{TOKENS.format(totals.text.tokens)}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{rub(totals.text.rub)}</td>
                    </>
                  )}
                  <td className="px-4 py-3 text-right tabular-nums">{rub(sumTotal)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}

      {totals && rows && rows.length > 0 && (
        <section className="rounded-lg border border-hairline bg-card p-5 text-sm leading-relaxed">
          <h2 className="text-sm font-semibold">Резюме за период</h2>
          <ul className="mt-2 space-y-1.5">
            {showVision && (
              <li>
                {MODEL_LABELS.vision}: всего{" "}
                <strong className="tabular-nums">{TOKENS.format(totals.vision.tokens)} млн токенов</strong> на
                сумму <strong className="tabular-nums">{rub(totals.vision.rub)}</strong> (с НДС).
              </li>
            )}
            {showText && (
              <li>
                {MODEL_LABELS.text}: всего{" "}
                <strong className="tabular-nums">{TOKENS.format(totals.text.tokens)} млн токенов</strong> на
                сумму <strong className="tabular-nums">{rub(totals.text.rub)}</strong> (с НДС).
              </li>
            )}
            {filter === "all" && totals.other.rub > 0 && (
              <li className="text-warning">
                {MODEL_LABELS.other}: <strong className="tabular-nums">{rub(totals.other.rub)}</strong> — строки,
                которые не удалось отнести ни к одной модели продукта. В «Итого» они входят.
              </li>
            )}
            <li>
              Общие расходы за период с {formatDateRu(from)} по {formatDateRu(to)}:{" "}
              <strong className="tabular-nums">{rub(sumTotal)}</strong> с НДС (
              <span className="tabular-nums">{rub(sumTotalNoVat)}</span> без НДС).
            </li>
          </ul>
        </section>
      )}
    </div>
  );
}
