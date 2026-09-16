"use client";

import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { qaKindLabel } from "@/lib/report-view";
import type { QaFlagView } from "@/lib/report-view";
import { useDismissable } from "./Hint";

/**
 * Замечания QA по одному ответу персоны.
 *
 * ─── Что здесь было ───────────────────────────────────────────────────────
 * Неподвижный значок «QA» с нативным `title`. В `title` уезжало поле `verdict`,
 * потому что читатель отчёта спрашивал у флага несуществующее поле `reason`, а
 * запасной путь подставлял вердикт. У всех забракованных ответов вердикт один
 * и тот же, так что на прогоне 0091 во всех 25 подсказках стояло
 * «QA: regenerate» — слово, объясняющее решение системы вместо причины.
 *
 * ─── Почему панель, а не `title` ──────────────────────────────────────────
 * Причины пишет судья, и они длинные: на 0091 медиана 377 знаков, девятый
 * дециль 589, самая длинная — 2988. Нативная подсказка показала бы это одной
 * строкой и оборвала. Панель — со своей полосой прокрутки и потолком по высоте.
 *
 * ─── Почему открывается тремя способами ───────────────────────────────────
 * Владелец просил «навести или нажать». Наведения одного мало: на сенсорном
 * экране наводить нечем, с клавиатуры до подсказки не добраться. Нажатие при
 * этом ЗАКРЕПЛЯЕТ панель: причину в две тысячи знаков читают дольше, чем
 * держат курсор, и уход мыши не должен её отнимать.
 */
export function QaFlags({ flags }: { flags: QaFlagView[] }) {
  const [open, setOpen] = useState(false);
  // Закреплено нажатием: уход мыши такую панель не закрывает.
  const [pinned, setPinned] = useState(false);
  const box = useDismissable<HTMLDivElement>(open, () => {
    setOpen(false);
    setPinned(false);
  });

  if (flags.length === 0) return null;

  return (
    <span
      className="relative inline-flex shrink-0 align-middle"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => !pinned && setOpen(false)}
      // Вся строка аккордеона — role=button, раскрывающий карточку. Без этих
      // двух перехватов нажатие на значок раскрывало бы карточку вместо показа
      // причин, то есть кнопка делала бы не то, что обещает.
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        aria-label={`Замечания QA: ${flags.length}`}
        aria-expanded={open}
        onClick={() => {
          // Нажатие закрепляет и открывает, повторное — отпускает и закрывает.
          // Наведение при этом остаётся: закреплять, чтобы просто взглянуть,
          // никто не обязан.
          setPinned(!pinned);
          setOpen(!pinned);
        }}
        onFocus={() => setOpen(true)}
        className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-amber-400 transition-colors hover:bg-amber-400/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400"
      >
        <AlertTriangle className="h-3.5 w-3.5" />
        QA
      </button>

      {open && (
        <div
          ref={box}
          role="tooltip"
          // Вправо панель не уходит: значок стоит в середине строки, и
          // выравнивание по левому краю выбросило бы её за экран на телефоне.
          className="absolute right-0 top-7 z-50 max-h-[60vh] w-[min(34rem,calc(100vw-2rem))] cursor-default overflow-y-auto rounded-xl border border-hairline bg-card p-4 text-left shadow-lg"
        >
          <QaFlagList flags={flags} />
        </div>
      )}
    </span>
  );
}

/**
 * Список замечаний: вид проверки, уверенность, причины словами.
 *
 * Уверенность показана рядом с видом, а не спрятана: на 0091 она идёт от 0.70
 * до 0.95, и придирку судьи с 0.70 стоит читать иначе, чем ошибку таймкода с
 * 0.95. Без неё все замечания выглядят одинаково обязательными.
 */
export function QaFlagList({ flags }: { flags: QaFlagView[] }) {
  return (
    <ul className="space-y-3">
      {flags.map((f, i) => (
        <li key={`${f.kind}${i}`}>
          <p className="text-xs font-semibold text-amber-400">
            {qaKindLabel(f.kind)}
            {f.confidence !== null && (
              <span className="ml-2 font-normal tabular-nums text-slate">
                уверенность {f.confidence.toFixed(2)}
              </span>
            )}
          </p>
          {f.reasons.length > 0 ? (
            f.reasons.map((r, j) => (
              <p key={j} className="mt-1 text-xs leading-relaxed text-slate">
                {r}
              </p>
            ))
          ) : (
            // Флаг без причин — не то же самое, что отсутствие флага. Ответ
            // забракован и в агрегат не попал; молча спрятать это значило бы
            // разойтись с числом «исключено QA» в шапке отчёта.
            <p className="mt-1 text-xs leading-relaxed text-slate/60">
              Причина не записана: проверка забраковала ответ, не объяснив.
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
