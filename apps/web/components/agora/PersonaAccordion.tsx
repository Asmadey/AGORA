"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, MessageCircle, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { CRITERIA, CRITERIA_LABELS } from "@/lib/agora-types";
import type { AnswerView } from "@/lib/report-view";
import { PersonaDialog } from "./PersonaDialog";
import { TimecodeRef } from "./Primitives";

/**
 * Аккордеон по персонам (PRD §5.E, §6).
 *
 * Свёрнутая строка показывает то, по чему принимают решение: балл и намерение
 * досмотреть. Развёрнутая — обоснование с таймкодами. Смысл в том, чтобы
 * средний балл всегда можно было раскрыть до конкретной реплики конкретной
 * персоны — иначе агрегат ничем не отличается от догадки.
 *
 * Компонент получает разобранные карточки отчёта, а не персон из реестра.
 * Персону могли отредактировать или удалить после прогона, а отчёт обязан
 * показывать ту аудиторию, на которой посчитан.
 *
 * Ключ строки — персона И номер повтора: при перекрытии ×3 одна персона даёт
 * три карточки, и ключ по одному persona_id схлопнул бы их в одну строку.
 */
export function PersonaAccordion({
  answers,
  runId,
}: {
  answers: AnswerView[];
  runId: string;
}) {
  const [openKey, setOpenKey] = useState<string | null>(null);

  if (answers.length === 0) {
    return (
      <p className="rounded-lg border border-hairline p-5 text-sm text-slate">
        Ответов нет. Если прогон завершён, смотрите причины на экране прогресса —
        пустой отчёт при успешном прогоне означает, что все ответы забракованы QA.
      </p>
    );
  }

  return (
    <div className="divide-y divide-border overflow-hidden rounded-lg border border-hairline">
      {answers.map((a) => {
        const key = `${a.personaId}#${a.replication}`;
        const open = openKey === key;

        return (
          <div key={key} className="bg-card">
            {/*
              Строка — контейнер, а не одна кнопка: «О персоне» стоит рядом с
              именем, а кнопка внутри кнопки — невалидная разметка, которую
              браузеры чинят каждый по-своему. Поэтому раскрытие повешено на два
              явных элемента: блок с именем слева и шеврон справа.
            */}
            <div className="flex w-full items-center gap-4 px-5 py-4 transition-colors hover:bg-secondary/40">
              <button
                onClick={() => setOpenKey(open ? null : key)}
                className="flex min-w-0 items-center gap-4 text-left"
                aria-expanded={open}
              >
                <div
                  className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-xs font-semibold"
                  style={{
                    backgroundColor: `hsl(${a.avatarHue} 45% 22%)`,
                    color: `hsl(${a.avatarHue} 70% 78%)`,
                  }}
                >
                  {a.initials}
                </div>

                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {a.personaName}
                    {a.replication > 0 && (
                      <span className="ml-2 text-xs text-slate">
                        повтор {a.replication + 1}
                      </span>
                    )}
                  </p>
                  <p className="truncate text-xs text-slate">
                    {a.segmentLabel ?? "срез не записан"}
                  </p>
                </div>
              </button>

              <PersonaDialog personaId={a.personaId} personaName={a.personaName} />

              {/* Распорка: всё, что правее, прижато к краю строки. */}
              <div className="flex-1" />

              {a.qaFlags.length > 0 && (
                <span
                  title={`QA: ${a.qaFlags.join("; ")}`}
                  className="hidden items-center gap-1 text-xs text-amber-400 sm:inline-flex"
                >
                  <AlertTriangle className="h-3.5 w-3.5" />
                  QA
                </span>
              )}

              <div className="hidden w-32 shrink-0 text-right sm:block">
                <p className="text-xs text-slate">Досмотрит</p>
                <p className="truncate text-sm">
                  {a.watchedShare !== null
                    ? `${a.watchedShare}%`
                    : (a.retentionIntent ?? "—")}
                </p>
              </div>

              <div className="w-14 shrink-0 text-right">
                <p
                  className={cn(
                    "text-xl font-semibold tabular-nums",
                    a.overall === null
                      ? "text-slate"
                      : a.overall >= 8
                        ? "text-success"
                        : a.overall >= 6.5
                          ? ""
                          : "text-amber-400",
                  )}
                >
                  {a.overall === null ? "—" : a.overall.toFixed(1)}
                </p>
              </div>

              <button
                onClick={() => setOpenKey(open ? null : key)}
                className="shrink-0 rounded-md p-1 text-slate transition-colors hover:text-foreground"
                aria-expanded={open}
                aria-label={open ? "Свернуть ответ" : "Раскрыть ответ"}
              >
                <ChevronDown
                  className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
                />
              </button>
            </div>

            {open && (
              <div className="border-t border-hairline/60 px-5 py-5">
                <div className="grid gap-4 sm:grid-cols-5">
                  {CRITERIA.map((c) => (
                    <div key={c}>
                      <p className="text-xs text-slate">{CRITERIA_LABELS[c]}</p>
                      <p className="mt-0.5 text-lg font-semibold tabular-nums">
                        {a.scores[c] ?? "—"}
                      </p>
                    </div>
                  ))}
                </div>

                {a.verbatim && (
                  <blockquote className="mt-5 border-l-2 border-hairline pl-4 text-sm leading-relaxed">
                    «{a.verbatim}»
                  </blockquote>
                )}

                {a.groundingRefs.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {a.groundingRefs.map((r) => (
                      <TimecodeRef key={`${r.timecode}${r.note}`} timecode={r.timecode} note={r.note} />
                    ))}
                  </div>
                )}

                {a.qaFlags.length > 0 && (
                  <ul className="mt-4 space-y-1 text-xs text-amber-400">
                    {a.qaFlags.map((f) => (
                      <li key={f}>— {f}</li>
                    ))}
                  </ul>
                )}

                <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate">
                  {a.nps !== null && <span>Порекомендует: {a.nps} из 10</span>}
                  {a.emotions.length > 0 && <span>Эмоции: {a.emotions.join(", ")}</span>}
                  {/* Ссылки «Карточка персоны» здесь больше нет: она лежала
                      внутри раскрытого ответа, то есть увидеть её можно было,
                      только раскрыв ответ. Вопрос «кто это сказал» задают
                      раньше — кнопка «О персоне» стоит в свёрнутой строке. */}
                  <Link
                    href={`/runs/${runId}/chat?persona=${a.personaId}`}
                    className="inline-flex items-center gap-1.5 underline-offset-4 hover:text-foreground hover:underline"
                  >
                    <MessageCircle className="h-3.5 w-3.5" />
                    Спросить персону
                  </Link>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
