"use client";

import Link from "next/link";
import { useState } from "react";

/**
 * Наборы персон над реестром: три свежих, остальные — по кнопке.
 *
 * ─── Зачем сворачивать ─────────────────────────────────────────────────────
 * Наборы копятся: каждый прогон, каждая проба фильтров, каждая правка датасета
 * оставляют свой. Через месяц работы их десятки, и все они лежали одним ковром
 * из плашек, который отжимал реестр персон на второй экран. При этом ответ на
 * вопрос «на ком я проверял ролик вчера» лежит в первых трёх: список уже
 * отсортирован свежими вперёд (`ORDER BY ps.created_at DESC`).
 *
 * ─── Почему не «показать 10» и не пагинация ────────────────────────────────
 * Промежуточные порции здесь ничего не дают: либо человеку нужен последний
 * набор — и он в первой тройке, — либо он ищет конкретный старый, и тогда ему
 * нужен весь список сразу, чтобы пробежать глазами.
 */

export interface PersonaSetChip {
  id: string;
  name: string;
  size: number;
  personaCount: number;
  seed: number | null;
}

/** Сколько показываем свёрнутыми. Три — ровно один ряд на типовой ширине. */
const COLLAPSED = 3;

export function PersonaSetChips({ sets }: { sets: PersonaSetChip[] }) {
  const [expanded, setExpanded] = useState(false);
  const hidden = sets.length - COLLAPSED;
  const visible = expanded ? sets : sets.slice(0, COLLAPSED);

  return (
    <div className="mb-6 space-y-1.5">
      <p className="text-xs uppercase tracking-wide text-slate">Наборы</p>
      {/* Наборы кликабельны: «на ком я буду проверять ролик» — вопрос,
          который задают перед запуском, а реестр показывает всех персон
          арендатора вперемешку и ответа не даёт. */}
      <div className="flex flex-wrap items-center gap-2">
        {visible.map((s) => (
          <Link
            key={s.id}
            href={`/personas/sets/${s.id}`}
            className="rounded-full border border-hairline px-3.5 py-1.5 text-sm text-slate transition-colors hover:border-hairline-strong hover:bg-surface hover:text-ink"
          >
            {s.name} · {s.personaCount} из {s.size}
            {s.seed !== null && ` · seed ${s.seed}`}
          </Link>
        ))}

        {hidden > 0 && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="rounded-full border border-dashed border-hairline px-3.5 py-1.5 text-sm text-slate transition-colors hover:border-hairline-strong hover:text-ink"
          >
            {expanded ? "Свернуть" : `Больше · ещё ${hidden}`}
          </button>
        )}
      </div>
    </div>
  );
}
