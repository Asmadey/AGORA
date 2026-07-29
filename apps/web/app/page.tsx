import Link from "next/link";
import { ArrowRight, Loader2, CheckCircle2, Clock, AlertTriangle } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { MOCK_RUNS } from "@/lib/mock-data";
import type { TaskStatus } from "@/lib/agora-types";

function StatusBadge({ status }: { status: TaskStatus }) {
  const map: Record<TaskStatus, { label: string; icon: React.ElementType; cls: string }> = {
    QUEUED: { label: "В очереди", icon: Clock, cls: "text-muted-foreground" },
    RUNNING: { label: "Идёт прогон", icon: Loader2, cls: "text-sky-400" },
    REPORT_READY: { label: "Отчёт готов", icon: CheckCircle2, cls: "text-emerald-400" },
    FAILED: { label: "Ошибка", icon: AlertTriangle, cls: "text-rose-400" },
  };
  const { label, icon: Icon, cls } = map[status];
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${cls}`}>
      <Icon className={`h-3.5 w-3.5 ${status === "RUNNING" ? "animate-spin" : ""}`} />
      {label}
    </span>
  );
}

function formatDuration(sec: number) {
  const m = Math.round(sec / 60);
  return m >= 60 ? `${Math.floor(m / 60)} ч ${m % 60} мин` : `${m} мин`;
}

export default function ProjectsPage() {
  return (
    <>
      <PageHeader
        title="Проекты"
        subtitle="Прогоны исследований по вашим материалам. Отчёт появляется через несколько минут после запуска."
        actions={
          <Link
            href="/studies/new"
            className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
          >
            Новое исследование
          </Link>
        }
      />

      <div className="p-8">
        <div className="space-y-3">
          {MOCK_RUNS.map((run) => {
            const ready = run.status === "REPORT_READY";
            const href = ready ? `/runs/${run.id}` : `/runs/${run.id}/progress`;
            return (
              <Link
                key={run.id}
                href={href}
                className="group flex items-center gap-6 rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5 transition-colors hover:border-muted-foreground/40"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                    <h2 className="truncate font-medium">{run.projectName}</h2>
                    <StatusBadge status={run.status} />
                  </div>
                  <p className="mt-1 truncate text-sm text-muted-foreground">
                    {run.contentTitle} · {formatDuration(run.durationSec)}
                  </p>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Chip tone="outline">{run.audienceSize} персон</Chip>
                    <Chip tone="outline">Перекрытие {run.replicationCount}</Chip>
                    <Chip tone="outline">
                      {run.mode === "short" ? "Короткое" : "Длинное"} видео
                    </Chip>
                  </div>
                </div>

                {ready && run.aggregate && (
                  <div className="hidden shrink-0 text-right sm:block">
                    <p className="text-xs text-muted-foreground">Общее впечатление</p>
                    <p className="text-3xl font-semibold tabular-nums">
                      {run.aggregate.scores.overall_impression.toFixed(1)}
                    </p>
                  </div>
                )}

                <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </Link>
            );
          })}
        </div>
      </div>
    </>
  );
}
