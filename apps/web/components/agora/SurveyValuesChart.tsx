import { optionRows } from "@/lib/report-survey";
import type { SurveyQuestionView } from "@/lib/report-view";

/**
 * Вопрос 8 столбиками — на месте прежнего графика ценностей аудитории.
 *
 * ─── Почему замена, а не соседство ────────────────────────────────────────
 * Решение владельца 17.09.2026. Прежняя плитка «Ценности ВЦИОМ» показывала,
 * какие ценности несут СГЕНЕРИРОВАННЫЕ персоны, — свойство аудитории, а не
 * результат исследования. Вопрос 8 спрашивает, какие ценности аудитория
 * УВИДЕЛА в материале, и это ответ про материал. Две похожие плитки рядом
 * читались бы как одна и та же величина, посчитанная дважды.
 *
 * Сам `ValuesChart` не удалён: состав ценностей аудитории остаётся свойством
 * набора персон и нужен реестру аудитории.
 *
 * ─── Почему доля от максимума ─────────────────────────────────────────────
 * Персона называет до трёх ценностей, поэтому сумма долей больше единицы, и
 * длина столбика как доли от суммы не значила бы ничего. Число на строке —
 * настоящая доля «в % от ответивших», длина — только способ сравнить строки
 * между собой.
 */
export function SurveyValuesChart({ question }: { question: SurveyQuestionView }) {
  const rows = optionRows(question, question.total);
  const max = Math.max(...rows.map((r) => r.share ?? 0), 0);

  return (
    <div className="rounded-lg border border-hairline bg-card p-4">
      <p className="flex items-baseline justify-between gap-2 text-xs uppercase tracking-wide text-slate">
        <span>Донесённые ценности</span>
        <span className="shrink-0 text-[10px] normal-case tracking-normal text-slate/70">
          вопрос 8 · ответили {question.total.n}
          {question.total.base === null ? "" : ` из ${question.total.base}`}
        </span>
      </p>
      <ol className="space-y-[2px]">
        {rows.map((row) => (
          <li key={row.id} className="relative h-[13px] overflow-hidden rounded-sm">
            <span className="absolute inset-0 bg-secondary" aria-hidden />
            <span
              className="absolute inset-y-0 left-0 bg-brand-blue/25"
              style={{ width: max > 0 ? `${Math.round(((row.share ?? 0) / max) * 100)}%` : "0%" }}
              aria-hidden
            />
            <span className="relative flex h-full items-center justify-between gap-2 px-1.5">
              {/*
                Обрезанная подпись читается наведением: перенос на вторую строку
                сломал бы высоту всех девятнадцати строк, а плитка обязана быть
                в высоту соседних.
              */}
              <span className="truncate text-[10px] leading-none" title={row.label}>
                {row.label}
              </span>
              <span
                className={`shrink-0 text-[10px] leading-none tabular-nums ${
                  row.share ? "font-medium" : "text-slate"
                }`}
              >
                {row.share === null ? "—" : `${Math.round(row.share * 100)}%`}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
