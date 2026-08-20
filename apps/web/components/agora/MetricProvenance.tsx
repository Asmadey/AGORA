import { TimecodeRef } from "./Primitives";
import type { Provenance } from "@/lib/provenance";

/**
 * Откуда взялось число: список ответов, из которых оно посчитано.
 *
 * ─── Почему `<details>`, а не диалог ──────────────────────────────────────
 * Последний шаг цепочки — «нажимаете таймкод, плеер перематывается туда».
 * Плеер стоит на этой же странице выше. Диалог перекрыл бы его собой: человек
 * нажал бы на момент и не увидел, что произошло, — то есть ровно тот шаг, ради
 * которого вся цепочка и строится, оказался бы не виден.
 *
 * Раскрытие на месте оставляет плеер доступным, а разметка остаётся серверной:
 * ни состояния, ни клиентского кода здесь не нужно.
 *
 * ─── Почему список бывает короче аудитории ────────────────────────────────
 * Экран показывает первую страницу карточек (50), а число посчитано по всем
 * выжившим ответам. При аудитории больше пятидесяти совпадения не будет, и
 * молчать об этом нельзя: расхождение читается как ошибка расчёта. Поэтому
 * посчитанное здесь сверяется с показанным в шапке, и несовпадение называется
 * вслух вместе с причиной.
 */
export function MetricProvenance({
  provenance,
  reported,
  total,
}: {
  provenance: Provenance;
  /** Число из шапки отчёта — то, что должно получиться. */
  reported: number | null;
  /** Сколько ответов всего у прогона: список может покрывать не все. */
  total: number;
}) {
  const { rows, computed, formula, excluded, silent } = provenance;

  if (rows.length === 0) {
    return (
      <p className="mt-2 border-t border-hairline pt-2 text-xs text-slate">
        Показывать нечего: {formula}.
      </p>
    );
  }

  const mismatch =
    reported !== null && computed !== null && Math.abs(reported - computed) > 0.05;

  return (
    <details className="mt-2 border-t border-hairline pt-2">
      <summary className="cursor-pointer text-xs text-slate hover:text-foreground">
        Откуда это число — {rows.length}{" "}
        {rows.length === 1 ? "ответ" : rows.length < 5 ? "ответа" : "ответов"}
      </summary>

      <p className="mt-2 text-xs leading-relaxed text-foreground/80">{formula}.</p>

      {(excluded > 0 || silent > 0) && (
        <p className="mt-1 text-xs text-slate">
          {excluded > 0 && `${excluded} исключено проверкой QA`}
          {excluded > 0 && silent > 0 && " · "}
          {silent > 0 && `${silent} эту величину не назвали`}
        </p>
      )}

      {mismatch && (
        <p className="mt-1 text-xs text-amber-400">
          По этим {rows.length} ответам получается {computed}, а в шапке {reported}: на
          экране первая страница карточек, а число посчитано по всем {total} ответам
          прогона.
        </p>
      )}

      <ul className="mt-3 space-y-2">
        {rows.map((row) => (
          <li
            key={`${row.personaId}-${row.value}`}
            className="rounded-md border border-hairline bg-secondary/30 p-2.5"
          >
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-xs font-medium">
                {row.personaName}
                {row.segmentLabel && (
                  <span className="ml-1.5 font-normal text-slate">{row.segmentLabel}</span>
                )}
              </span>
              <span className="shrink-0 font-mono text-xs tabular-nums">
                {row.display}
                {row.group && <span className="ml-1.5 text-slate">{row.group}</span>}
              </span>
            </div>

            {row.verbatim && (
              <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-foreground/75">
                {row.verbatim}
              </p>
            )}

            {row.refs.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {row.refs.map((ref) => (
                  <TimecodeRef
                    key={`${ref.timecode}-${ref.note}`}
                    timecode={ref.timecode}
                    note={ref.note}
                  />
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
