"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

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
  const router = useRouter();
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hidden = sets.length - COLLAPSED;
  const visible = expanded ? sets : sets.slice(0, COLLAPSED);
  const ids = useMemo(() => [...selected], [selected]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setError(null);
  };

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/audience", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "не удалось удалить");
        return;
      }
      // Отказ по занятым наборам — не ошибка запроса, а его результат, и
      // сказать о нём надо теми же словами, что и об успехе: сколько удалено и
      // почему остальные остались.
      const blocked = (data.blocked ?? []) as { name: string; runs: number }[];
      if (blocked.length > 0) {
        setError(
          `удалено ${data.deleted}; остались наборы, на которых стоят исследования: ` +
            blocked.map((b) => `${b.name} (${b.runs})`).join(", ") +
            ". Удалите сначала эти исследования — иначе отчёт потеряет ссылку на аудиторию",
        );
      }
      setSelected(new Set());
      router.refresh();
    } catch {
      setError("сервер недоступен");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-6 space-y-1.5">
      <div className="flex items-center gap-3">
        <p className="text-xs uppercase tracking-wide text-slate">Аудитории</p>
        {/* Кнопка появляется только при выборе: постоянная красная кнопка рядом
            со списком читается как приглашение, а удаление здесь необратимо. */}
        {selected.size > 0 && (
          <button
            type="button"
            onClick={remove}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-md bg-danger px-3 py-1 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            Удалить {selected.size}
          </button>
        )}
      </div>

      {error && (
        <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>
      )}

      {/* Наборы кликабельны: «на ком я буду проверять ролик» — вопрос,
          который задают перед запуском, а реестр показывает всех персон
          арендатора вперемешку и ответа не даёт. */}
      <div className="flex flex-wrap items-center gap-2">
        {visible.map((s) => {
          const checked = selected.has(s.id);
          return (
            <span
              key={s.id}
              className={`inline-flex items-center gap-2 rounded-full border py-1.5 pl-3 pr-3.5 text-sm transition-colors ${
                checked
                  ? "border-brand-blue bg-surface-yellow text-ink"
                  : "border-hairline text-slate hover:border-hairline-strong hover:bg-surface hover:text-ink"
              }`}
            >
              {/*
                Чекбокс отдельным элементом, а не обёрткой вокруг ссылки: кнопка
                внутри ссылки — невалидная разметка, и клик по ней уводил бы со
                страницы вместо выбора.
              */}
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(s.id)}
                aria-label={`Выбрать набор ${s.name}`}
                className="h-3.5 w-3.5 shrink-0 accent-foreground"
              />
              <Link href={`/personas/sets/${s.id}`} className="min-w-0">
                {s.name} · {s.personaCount} из {s.size}
                {s.seed !== null && ` · seed ${s.seed}`}
              </Link>
            </span>
          );
        })}

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
