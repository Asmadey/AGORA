"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, MessageCircle, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { CRITERIA, CRITERIA_LABELS, type PersonaAnswer, type Persona } from "@/lib/agora-types";
import { TimecodeRef } from "./Primitives";

/**
 * Аккордеон по персонам (PRD §5.E, §6).
 *
 * Свёрнутая строка показывает то, по чему принимают решение: балл и досмотр.
 * Развёрнутая — обоснование с таймкодами. Смысл в том, чтобы средний балл всегда
 * можно было раскрыть до конкретной реплики конкретной персоны — иначе агрегат
 * ничем не отличается от догадки.
 */
export function PersonaAccordion({
  personas,
  answers,
  runId,
}: {
  personas: Persona[];
  answers: PersonaAnswer[];
  runId: string;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="divide-y divide-border overflow-hidden rounded-lg border border-border">
      {answers.map((a) => {
        const persona = personas.find((p) => p.id === a.personaId);
        if (!persona) return null;
        const open = openId === a.personaId;
        const overall = a.scores.overall_impression;

        return (
          <div key={a.personaId} className="bg-[hsl(222_47%_7%)]">
            <button
              onClick={() => setOpenId(open ? null : a.personaId)}
              className="flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-secondary/40"
              aria-expanded={open}
            >
              <div
                className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-xs font-semibold"
                style={{
                  backgroundColor: `hsl(${persona.avatarHue} 45% 22%)`,
                  color: `hsl(${persona.avatarHue} 70% 78%)`,
                }}
              >
                {persona.name.split(" ").map((w) => w[0]).join("")}
              </div>

              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">
                  {persona.name.split(" ")[0]}, {persona.dna.demographics.age}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {persona.jobTitle} · {persona.location}
                </p>
              </div>

              {a.qaFlags.length > 0 && (
                <span
                  title={`QA-флаги: ${a.qaFlags.join(", ")}`}
                  className="hidden items-center gap-1 text-xs text-amber-400 sm:inline-flex"
                >
                  <AlertTriangle className="h-3.5 w-3.5" />
                  QA
                </span>
              )}

              <div className="hidden w-24 shrink-0 text-right sm:block">
                <p className="text-xs text-muted-foreground">Досмотр</p>
                <p className="text-sm tabular-nums">{a.watchedUntil}%</p>
              </div>

              <div className="w-14 shrink-0 text-right">
                <p
                  className={cn(
                    "text-xl font-semibold tabular-nums",
                    overall >= 8 ? "text-emerald-400" : overall >= 6.5 ? "" : "text-amber-400",
                  )}
                >
                  {overall.toFixed(1)}
                </p>
              </div>

              <ChevronDown
                className={cn(
                  "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
                  open && "rotate-180",
                )}
              />
            </button>

            {open && (
              <div className="border-t border-border/60 px-5 py-5">
                <div className="grid gap-4 sm:grid-cols-5">
                  {CRITERIA.map((c) => (
                    <div key={c}>
                      <p className="text-xs text-muted-foreground">{CRITERIA_LABELS[c]}</p>
                      <p className="mt-0.5 text-lg font-semibold tabular-nums">{a.scores[c]}</p>
                    </div>
                  ))}
                </div>

                <blockquote className="mt-5 border-l-2 border-border pl-4 text-sm leading-relaxed">
                  «{a.verbatim}»
                </blockquote>

                <div className="mt-4 flex flex-wrap gap-2">
                  {a.groundingRefs.map((r) => (
                    <TimecodeRef key={r.timecode} timecode={r.timecode} note={r.note} />
                  ))}
                </div>

                <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
                  <span>Порекомендует: {a.wouldRecommend ? "да" : "нет"}</span>
                  <span>Эмоции: {a.emotions.join(", ")}</span>
                  <Link
                    href={`/personas/${persona.id}`}
                    className="underline-offset-4 hover:text-foreground hover:underline"
                  >
                    Карточка персоны
                  </Link>
                  <Link
                    href={`/runs/${runId}/chat?persona=${persona.id}`}
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
