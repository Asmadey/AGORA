"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Check, Circle, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { nodesForMode, type PipelineNode } from "@/lib/pipeline-nodes";

/**
 * Экран прогресса прогона (задача #12).
 *
 * Заменяет витринную имитацию, которая двигала шкалу по таймеру. Внешне разница
 * невелика — и в этом была опасность: экран, показывающий правдоподобное
 * движение независимо от того, что происходит на воркере, не отличим от
 * рабочего до первого настоящего отказа.
 *
 * ─── Почему видны все узлы, а не только текущий ────────────────────────────
 * «Идёт распознавание речи» без остального списка не отвечает на вопрос,
 * который у пользователя на самом деле есть: сколько ещё ждать. Пятнадцать
 * минут на одном этапе выглядят зависанием ровно до тех пор, пока не видно,
 * что этот этап — четвёртый из четырнадцати и самый долгий.
 *
 * ─── Почему переподключение не написано руками ─────────────────────────────
 * EventSource переподключается сам, с нарастающей паузой. Свой цикл поверх
 * этого дал бы два независимых механизма, которые при обрыве откроют два потока.
 *
 * Состояние при этом не теряется, потому что сервер первым же событием отдаёт
 * снимок из Valkey (см. app/api/tasks/[id]/progress/route.ts). Экрану не нужно
 * ничего запоминать между подключениями — и это правильное разделение: браузер
 * не источник истины о прогоне.
 */

export interface ProgressEvent {
  task_id: string;
  node: string;
  status: string;
  at: number;
  detail?: string;
  error?: string;
  degraded?: string[];
}

type NodeState = "waiting" | "running" | "done" | "failed";

export function ProgressView({
  taskId,
  mode = "short",
}: {
  taskId: string;
  mode?: "short" | "long";
}) {
  const [event, setEvent] = useState<ProgressEvent | null>(null);
  const [connected, setConnected] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const nodes = useRef<PipelineNode[]>(nodesForMode(mode));

  useEffect(() => {
    const source = new EventSource(`/api/tasks/${taskId}/progress`);

    source.addEventListener("open", () => setConnected(true));
    source.addEventListener("error", () => setConnected(false));
    source.addEventListener("progress", (e) => {
      setConnected(true);
      try {
        setEvent(JSON.parse((e as MessageEvent).data) as ProgressEvent);
      } catch {
        // Битое событие пропускаем: следующее придёт целым, а рушить экран
        // идущего исследования из-за одной строки нельзя.
      }
    });

    return () => source.close();
  }, [taskId]);

  const failed = event?.status === "FAILED";
  const finished = event?.status === "REPORT_READY";

  useEffect(() => {
    if (finished || failed) return;
    const timer = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(timer);
  }, [finished, failed]);

  const currentIndex = nodes.current.findIndex((n) => n.name === event?.node);
  const doneCount = finished
    ? nodes.current.length
    : Math.max(currentIndex, 0) + (event?.status === "DONE" ? 1 : 0);
  const pct = Math.round((doneCount / nodes.current.length) * 100);

  function stateOf(index: number): NodeState {
    if (finished) return "done";
    if (currentIndex < 0) return "waiting";
    if (index < currentIndex) return "done";
    if (index > currentIndex) return "waiting";
    if (failed) return "failed";
    return event?.status === "DONE" ? "done" : "running";
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <div className="mb-2 flex items-baseline justify-between gap-4">
          <span className="text-sm text-muted-foreground">
            {finished
              ? "Прогон завершён"
              : failed
                ? "Прогон остановлен"
                : `Шаг ${Math.min(Math.max(currentIndex + 1, 1), nodes.current.length)} из ${nodes.current.length}`}
          </span>
          <span className="text-sm tabular-nums text-muted-foreground">
            {!connected && !finished && !failed
              ? "переподключение…"
              : `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`}
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-700",
              failed ? "bg-rose-400" : "bg-foreground",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/*
        Причина отказа показывается текстом, а не кодом статуса. FAILED без
        объяснения отправляет пользователя читать логи воркера, к которым у него
        нет и не будет доступа.
      */}
      {failed && (
        <div className="flex gap-3 rounded-md border border-rose-400/40 bg-rose-400/5 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
          <div className="space-y-1">
            <p className="text-sm font-medium">Прогон остановлен</p>
            <p className="text-sm text-muted-foreground">
              {event?.error || "причина не передана — это дефект воркера, а не прогона"}
            </p>
          </div>
        </div>
      )}

      {!!event?.degraded?.length && (
        <div className="rounded-md border border-border bg-secondary/40 p-4">
          <p className="text-sm font-medium">Этапы, отработавшие не полностью</p>
          <ul className="mt-1 space-y-0.5 text-sm text-muted-foreground">
            {event.degraded.map((line) => (
              <li key={line}>· {line}</li>
            ))}
          </ul>
        </div>
      )}

      <ol className="space-y-1">
        {nodes.current.map((node, i) => {
          const state = stateOf(i);
          return (
            <li
              key={node.name}
              className={cn(
                "flex items-start gap-3 rounded-md px-3 py-3",
                state === "running" && "bg-secondary/50",
              )}
            >
              <span className="mt-0.5 shrink-0">
                {state === "done" && <Check className="h-4 w-4 text-emerald-400" />}
                {state === "running" && <Loader2 className="h-4 w-4 animate-spin text-sky-400" />}
                {state === "failed" && <AlertTriangle className="h-4 w-4 text-rose-400" />}
                {state === "waiting" && <Circle className="h-4 w-4 text-muted-foreground/40" />}
              </span>
              <span className="min-w-0 flex-1">
                <span
                  className={cn("block text-sm", state === "waiting" && "text-muted-foreground")}
                >
                  {node.label}
                </span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  {state === "running" && event?.detail ? event.detail : node.detail}
                </span>
              </span>
            </li>
          );
        })}
      </ol>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Страницу можно закрыть — прогон продолжится на сервере, а при следующем открытии
        экран покажет текущее состояние, а не начнёт с нуля.
      </p>

      {finished && (
        <Link
          href={`/runs/${taskId}`}
          className="inline-flex rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary"
        >
          Открыть отчёт
        </Link>
      )}
    </div>
  );
}
