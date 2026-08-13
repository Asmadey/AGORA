"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { Chip } from "@/components/agora/Primitives";
import { cn } from "@/lib/utils";

/**
 * Одна запись корпуса: свёрнутая — шапка, развёрнутая — вся сессия.
 *
 * ─── Форма экрана повторяет форму данных ───────────────────────────────────
 * Главное, чего не было видно: запись — это не «один ответ человека», а целая
 * сессия. Внутри неё структурированные срезы, которыми пользуется код
 * (соцдем, пять базовых баллов, удержание), развёрнутые реплики — и полная
 * анкета: от 23 до 53 пар «вопрос → ответ», из которых эти срезы и извлечены.
 *
 * Поэтому анкета показана последней и целиком, а не пересказом: срезы выше —
 * это то, что система из неё вытащила, и рядом должно лежать то, из чего
 * вытаскивали. Иначе проверить дистилляцию нечем.
 *
 * ─── Почему раскрытие, а не отдельная страница ─────────────────────────────
 * Записи сравнивают между собой — «а что у соседнего сегмента». Переход на
 * отдельный адрес и обратно теряет место в списке на каждой второй записи.
 */

type Session = {
  respondent_id: string;
  source_file: string;
  content_under_test: { title: string; type: string; summary: string };
  experiment_metadata: {
    focus_group_city: string;
    target_audience_segment: string;
    transcript_source_file: string;
  };
  socio_demographics: Record<string, unknown>;
  psychographics_and_values: Record<string, unknown>;
  agora_core_scores_1_to_10: Record<string, number | null>;
  perception_and_retention: Record<string, unknown>;
  qualitative_verbatims: Record<string, unknown>;
  focus_group_verbatims?: unknown[] | null;
  all_survey_responses: Record<string, unknown>;
};

const SCORE_LABEL: Record<string, string> = {
  overall_impression: "Общее впечатление",
  plot: "Сюжет",
  acting: "Актёрская игра",
  music: "Музыка",
  cinematography: "Операторская работа",
};

/** Значение любой формы в читаемую строку. Пусто — прочерк, а не «0» и не «—». */
function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.map(show).join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Section({
  title,
  data,
  hint,
}: {
  title: string;
  data: Record<string, unknown>;
  hint?: string;
}) {
  const entries = Object.entries(data ?? {}).filter(([, v]) => show(v) !== "—");
  if (entries.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs uppercase tracking-wide text-stone">{title}</h4>
      {hint && <p className="mt-0.5 text-xs text-stone">{hint}</p>}
      <dl className="mt-2 space-y-1.5">
        {entries.map(([k, v]) => (
          <div key={k} className="grid gap-1 sm:grid-cols-[minmax(0,14rem)_1fr]">
            <dt className="text-xs text-slate">{k}</dt>
            <dd className="text-sm leading-relaxed">{show(v)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function RespondentCard({ session }: { session: Session }) {
  const [open, setOpen] = useState(false);

  const demo = session.socio_demographics ?? {};
  const answers = Object.entries(session.all_survey_responses ?? {});
  const focus = (session.focus_group_verbatims ?? []) as unknown[];

  return (
    <div className="rounded-xl border border-hairline bg-card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-4 p-5 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <span className="font-medium">{session.respondent_id}</span>
            <Chip tone="outline">{show(demo.gender)}</Chip>
            <Chip tone="outline">{show(demo.age)} лет</Chip>
            <Chip tone="outline">{show(demo.city)}</Chip>
          </div>
          <p className="mt-1.5 text-xs text-slate">
            {/* Число ответов — главное, что надо увидеть, не раскрывая: именно
                оно объясняет, что портрет сжимает, а не переписывает. */}
            {answers.length} ответов анкеты
            {focus.length > 0 && ` · ${focus.length} реплик в фокус-группе`} ·{" "}
            {session.content_under_test?.title}
          </p>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-slate transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div className="space-y-6 border-t border-hairline p-5">
          <div className="grid gap-6 lg:grid-cols-2">
            <Section
              title="Соцдем"
              hint="по этим полям считаются доли корпуса и калибруются персоны"
              data={demo}
            />
            <Section title="Психография и ценности" data={session.psychographics_and_values} />
          </div>

          <div>
            <h4 className="text-xs uppercase tracking-wide text-stone">
              Пять базовых баллов
            </h4>
            <p className="mt-0.5 text-xs text-stone">
              Ключи — часть контракта с данными: по ним посчитаны средние корпуса
            </p>
            <div className="mt-2 grid gap-2 sm:grid-cols-5">
              {Object.entries(session.agora_core_scores_1_to_10 ?? {}).map(([k, v]) => (
                <div key={k} className="rounded-lg border border-hairline px-3 py-2">
                  <div className="text-[11px] leading-tight text-slate">
                    {SCORE_LABEL[k] ?? k}
                  </div>
                  <div className="mt-0.5 text-lg font-semibold tabular-nums">
                    {v ?? "—"}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <Section title="Восприятие и удержание" data={session.perception_and_retention} />
          <Section title="Развёрнутые реплики" data={session.qualitative_verbatims} />

          {focus.length > 0 && (
            <div>
              <h4 className="text-xs uppercase tracking-wide text-stone">
                Фокус-группа
              </h4>
              <div className="mt-2 space-y-2">
                {focus.map((q, i) => (
                  <blockquote
                    key={i}
                    className="border-l-2 border-hairline-strong pl-3 text-sm leading-relaxed"
                  >
                    {show(q)}
                  </blockquote>
                ))}
              </div>
            </div>
          )}

          <div>
            <h4 className="text-xs uppercase tracking-wide text-stone">
              Анкета целиком — {answers.length} ответов
            </h4>
            <p className="mt-0.5 max-w-2xl text-xs leading-relaxed text-stone">
              Всё, что человек ответил. Секции выше — то, что система извлекла отсюда;
              портрет аудитории сжимает сотню таких анкет в несколько абзацев.
            </p>
            <dl className="mt-3 divide-y divide-hairline-soft rounded-lg border border-hairline">
              {answers.map(([q, a]) => (
                <div key={q} className="grid gap-1 p-3 sm:grid-cols-[minmax(0,22rem)_1fr]">
                  <dt className="text-xs leading-relaxed text-slate">{q}</dt>
                  <dd className="text-sm leading-relaxed">{show(a)}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}
