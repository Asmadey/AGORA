"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, Loader2, Circle } from "lucide-react";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/AppShell";
import type { PipelineNode } from "@/lib/agora-types";

/**
 * Экран прогресса (задача #12).
 *
 * Показываем узлы пайплайна поимённо, а не абстрактный процент. Прогон идёт минуты,
 * и пользователю важно понимать, на чём именно он стоит: транскрипция длинного видео
 * на CPU выглядит как «зависло», если не написать, что сейчас происходит.
 *
 * В проде состояние приходит по SSE из Valkey; здесь имитация для витрины.
 */

const NODES: PipelineNode[] = [
  { key: "extract_audio", label: "Извлечение аудио", status: "done" },
  { key: "transcribe", label: "Транскрипция и диаризация", status: "done", detail: "faster-whisper large-v3" },
  { key: "sample_frames", label: "Выборка кадров", status: "done", detail: "PySceneDetect, 38 сцен" },
  { key: "analyze_chunks", label: "Разбор сцен", status: "running", detail: "панель 14 из 38" },
  { key: "stitch", label: "Склейка понимания видео", status: "pending" },
  { key: "evaluate_personas", label: "Оценка персонами", status: "pending", detail: "20 персон × перекрытие 1" },
  { key: "qa", label: "QA-проверка ответов", status: "pending" },
  { key: "analytics", label: "Сборка отчёта", status: "pending" },
];

export default function ProgressPage() {
  const [nodes, setNodes] = useState(NODES);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, []);

  // Имитация продвижения по узлам — вместо SSE-подписки на витрине.
  useEffect(() => {
    const t = setInterval(() => {
      setNodes((prev) => {
        const i = prev.findIndex((n) => n.status === "running");
        if (i === -1 || i === prev.length - 1) return prev;
        const next = [...prev];
        next[i] = { ...next[i], status: "done", detail: undefined };
        next[i + 1] = { ...next[i + 1], status: "running" };
        return next;
      });
    }, 6000);
    return () => clearInterval(t);
  }, []);

  const doneCount = nodes.filter((n) => n.status === "done").length;
  const pct = Math.round((doneCount / nodes.length) * 100);

  return (
    <>
      <PageHeader
        title="Промо-ролик «Константинополь»"
        subtitle="Тизер 60 сек · 20 персон · перекрытие 1"
      />

      <div className="mx-auto max-w-2xl p-8">
        <div className="mb-8">
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-sm text-muted-foreground">
              Шаг {Math.min(doneCount + 1, nodes.length)} из {nodes.length}
            </span>
            <span className="text-sm tabular-nums text-muted-foreground">
              {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-foreground transition-all duration-700"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        <ol className="space-y-1">
          {nodes.map((n) => (
            <li
              key={n.key}
              className={cn(
                "flex items-start gap-3 rounded-md px-3 py-3",
                n.status === "running" && "bg-secondary/50",
              )}
            >
              <span className="mt-0.5 shrink-0">
                {n.status === "done" && <Check className="h-4 w-4 text-emerald-400" />}
                {n.status === "running" && <Loader2 className="h-4 w-4 animate-spin text-sky-400" />}
                {n.status === "pending" && <Circle className="h-4 w-4 text-muted-foreground/40" />}
                {n.status === "failed" && <Circle className="h-4 w-4 text-rose-400" />}
              </span>
              <span className="min-w-0 flex-1">
                <span
                  className={cn(
                    "block text-sm",
                    n.status === "pending" && "text-muted-foreground",
                  )}
                >
                  {n.label}
                </span>
                {n.detail && (
                  <span className="mt-0.5 block text-xs text-muted-foreground">{n.detail}</span>
                )}
              </span>
            </li>
          ))}
        </ol>

        <p className="mt-8 text-xs leading-relaxed text-muted-foreground">
          Страницу можно закрыть — прогон продолжится на сервере. Разбор сцен и оценка
          персонами выполняются параллельно, поэтому время до отчёта растёт медленнее,
          чем размер аудитории.
        </p>

        <Link
          href="/"
          className="mt-6 inline-block text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Вернуться к проектам
        </Link>
      </div>
    </>
  );
}
