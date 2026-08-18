"use client";

import { useEffect, useMemo, useState } from "react";
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
  startedAt = null,
  finishedAt = null,
  durations = {},
}: {
  taskId: string;
  mode?: "short" | "long";
  /**
   * Сколько секунд занял каждый шаг: `{ имя узла: секунды }`.
   *
   * Приходит из `progress.timings`, которые воркер записывает В КОНЦЕ прогона
   * (`_save_timings`). Поэтому на идущем прогоне словарь пуст, и длительность
   * текущего шага считается здесь по времени события — иначе экран, ради
   * которого всё затевалось, был бы пустым ровно тогда, когда на него смотрят.
   */
  durations?: Record<string, number>;
  /**
   * Когда воркер взял задачу — `tasks.started_at`, момент первого перехода в
   * RUNNING, то есть начало шага «Разбор файла». null — задача ещё в очереди.
   */
  startedAt?: string | null;
  /** Когда закончился последний шаг — `tasks.finished_at`. */
  finishedAt?: string | null;
}) {
  const [event, setEvent] = useState<ProgressEvent | null>(null);
  const [connected, setConnected] = useState(false);
  /**
   * Отсчёт ведётся от начала прогона, а не от открытия страницы.
   *
   * Прежний счётчик стартовал с нуля на каждом монтировании компонента, и это
   * ломало его в обе стороны: обновив вкладку на десятой минуте, читатель видел
   * «0:03», а вкладка, открытая со вчера, показывала сутки прогона, который
   * давно закончился. Число выглядело осмысленным в обоих случаях — тем оно и
   * было плохо.
   *
   * `null` означает «считать не от чего»: задача стоит в очереди, воркер её ещё
   * не взял, и любое число здесь было бы выдуманным.
   */
  const [elapsed, setElapsed] = useState<number | null>(null);
  /**
   * Запасное начало отсчёта для страницы, открытой ДО того, как воркер взял
   * задачу. `startedAt` отрисован на сервере один раз и в такой вкладке
   * навсегда останется null — а прогон тем временем идёт. Первое событие
   * прогресса несёт `at` (epoch-секунды `time.time()` воркера) и годится
   * началом: расхождение с настоящим `started_at` — доли секунды, которые в
   * счётчике минут не видны.
   */
  const [firstEventAt, setFirstEventAt] = useState<number | null>(null);
  // useMemo, а не useRef: инициализатор ref вычисляется один раз за жизнь
  // компонента и на смену mode не реагирует — на длинном прогоне шкала осталась
  // бы со списком этапов короткого режима. Вдобавок чтение ref во время
  // отрисовки React не отслеживает, поэтому перерисовки от него не будет.
  const nodes = useMemo<PipelineNode[]>(() => nodesForMode(mode), [mode]);

  useEffect(() => {
    const source = new EventSource(`/api/tasks/${taskId}/progress`);

    source.addEventListener("open", () => setConnected(true));
    source.addEventListener("error", () => setConnected(false));
    source.addEventListener("progress", (e) => {
      setConnected(true);
      try {
        const parsed = JSON.parse((e as MessageEvent).data) as ProgressEvent;
        setEvent(parsed);
        setFirstEventAt((seen) =>
          seen ?? (typeof parsed.at === "number" ? parsed.at * 1000 : null),
        );
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
    const fromServer = startedAt ? Date.parse(startedAt) : NaN;
    const start = Number.isNaN(fromServer) ? (firstEventAt ?? NaN) : fromServer;
    if (Number.isNaN(start)) {
      setElapsed(null);
      return;
    }

    // Прогон уже закончился к моменту открытия страницы — показываем итоговую
    // длительность и не тикаем: она больше не меняется.
    const end = finishedAt ? Date.parse(finishedAt) : NaN;
    if (!Number.isNaN(end)) {
      setElapsed(Math.max(0, Math.round((end - start) / 1000)));
      return;
    }

    const tick = () => setElapsed(Math.max(0, Math.round((Date.now() - start) / 1000)));
    tick(); // сразу, чтобы первая секунда не была пустой
    if (finished || failed) return;
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [startedAt, finishedAt, firstEventAt, finished, failed]);

  // Когда начался текущий шаг: по времени события, которое о нём сообщило.
  // Событие приходит на КАЖДУЮ смену узла, поэтому отсчёт начинается заново
  // вместе с шагом, а не тянется от старта прогона.
  const [stepStartedAt, setStepStartedAt] = useState<number | null>(null);
  const [stepElapsed, setStepElapsed] = useState<number | null>(null);
  const currentNode = event?.node ?? null;

  useEffect(() => {
    setStepStartedAt(event?.at ? event.at * 1000 : Date.now());
  }, [currentNode]);

  useEffect(() => {
    if (stepStartedAt === null || finished || failed) {
      setStepElapsed(null);
      return;
    }
    const tick = () => setStepElapsed(Math.max(0, Math.round((Date.now() - stepStartedAt) / 1000)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [stepStartedAt, finished, failed]);

  /** «(30 сек)» рядом с названием шага. Пусто — длительности пока нет. */
  function stepTime(node: PipelineNode, state: NodeState): string {
    const known = durations[node.name];
    if (typeof known === "number") return ` (${Math.round(known)} сек)`;
    if (state === "running" && stepElapsed !== null) return ` (${stepElapsed} сек)`;
    return "";
  }

  const currentIndex = nodes.findIndex((n) => n.name === event?.node);
  const doneCount = finished
    ? nodes.length
    : Math.max(currentIndex, 0) + (event?.status === "DONE" ? 1 : 0);
  const pct = Math.round((doneCount / nodes.length) * 100);

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
          <span className="text-sm text-slate">
            {finished
              ? "Прогон завершён"
              : failed
                ? "Прогон остановлен"
                : `Шаг ${Math.min(Math.max(currentIndex + 1, 1), nodes.length)} из ${nodes.length}`}
          </span>
          <span className="text-sm tabular-nums text-slate">
            {!connected && !finished && !failed
              ? "переподключение…"
              : elapsed === null
                ? "в очереди"
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
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-danger" />
          <div className="space-y-1">
            <p className="text-sm font-medium">Прогон остановлен</p>
            <p className="text-sm text-slate">
              {event?.error || "причина не передана — это дефект воркера, а не прогона"}
            </p>
          </div>
        </div>
      )}

      {!!event?.degraded?.length && (
        <div className="rounded-md border border-hairline bg-secondary/40 p-4">
          <p className="text-sm font-medium">Этапы, отработавшие не полностью</p>
          <ul className="mt-1 space-y-0.5 text-sm text-slate">
            {event.degraded.map((line) => (
              <li key={line}>· {line}</li>
            ))}
          </ul>
        </div>
      )}

      <ol className="space-y-1">
        {nodes.map((node, i) => {
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
                {state === "done" && <Check className="h-4 w-4 text-success" />}
                {state === "running" && <Loader2 className="h-4 w-4 animate-spin text-brand-blue" />}
                {state === "failed" && <AlertTriangle className="h-4 w-4 text-danger" />}
                {state === "waiting" && <Circle className="h-4 w-4 text-slate/40" />}
              </span>
              <span className="min-w-0 flex-1">
                <span
                  className={cn("block text-sm", state === "waiting" && "text-slate")}
                >
                  {node.label}
                  <span className="tabular-nums text-slate">{stepTime(node, state)}</span>
                </span>
                <span className="mt-0.5 block text-xs text-slate">
                  {state === "running" && event?.detail ? event.detail : node.detail}
                </span>
              </span>
            </li>
          );
        })}
      </ol>

      <p className="text-xs leading-relaxed text-slate">
        Страницу можно закрыть — прогон продолжится на сервере, а при следующем открытии
        экран покажет текущее состояние, а не начнёт с нуля.
      </p>

      {finished && (
        <Link
          href={`/runs/${taskId}`}
          className="inline-flex rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary"
        >
          Открыть отчёт
        </Link>
      )}
    </div>
  );
}
