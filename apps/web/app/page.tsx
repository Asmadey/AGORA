import Link from "next/link";
import { ArrowRight, Loader2, CheckCircle2, Clock, AlertTriangle, Film } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { EmptyState } from "@/components/agora/States";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listTasks } from "@/lib/server/tasks";

/**
 * Список прогонов (PRD §5.E).
 *
 * До этого экран читал MOCK_RUNS из lib/mock-data: показывал четыре
 * правдоподобных исследования на пустом аккаунте, и отличить работающий сервис
 * от неподключённого можно было только по коду.
 *
 * Экран намеренно тонкий. В таблице `tasks` лежит то, что нужно списку —
 * статус, режим, перекрытие, время; средний балл живёт в отчёте, в Mongo, и
 * дотягивать его сюда значило бы читать по документу на строку списка. Поэтому
 * оценки в строке нет: она видна в самом отчёте, куда строка и ведёт.
 */

export const dynamic = "force-dynamic";

type Status = "QUEUED" | "RUNNING" | "REPORT_READY" | "FAILED";

const BADGE: Record<Status, { label: string; icon: React.ElementType; cls: string }> = {
  QUEUED: { label: "В очереди", icon: Clock, cls: "text-muted-foreground" },
  RUNNING: { label: "Идёт прогон", icon: Loader2, cls: "text-sky-400" },
  REPORT_READY: { label: "Отчёт готов", icon: CheckCircle2, cls: "text-emerald-400" },
  FAILED: { label: "Ошибка", icon: AlertTriangle, cls: "text-rose-400" },
};

function StatusBadge({ status }: { status: string }) {
  // Неизвестный статус рисуется как есть, а не отбрасывается: воркер может
  // завести новый, и молча пропавшая подпись выглядела бы как «без статуса».
  const known = BADGE[status as Status];
  if (!known) {
    return <span className="text-xs text-muted-foreground">{status}</span>;
  }
  const { label, icon: Icon, cls } = known;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${cls}`}>
      <Icon className={`h-3.5 w-3.5 ${status === "RUNNING" ? "animate-spin" : ""}`} />
      {label}
    </span>
  );
}

/** «5 минут назад» — в списке это читается быстрее абсолютной даты. */
function ago(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "";
  const minutes = Math.round(ms / 60000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  return new Date(iso).toLocaleDateString("ru-RU");
}

export default async function RunsPage() {
  const { tenantId } = await requireSession();
  const tasks = await withTenant(tenantId, listTasks);

  return (
    <>
      <PageHeader
        title="Прогоны"
        subtitle="Исследования по вашим материалам. Отчёт появляется через несколько минут после запуска."
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
        {tasks.length === 0 ? (
          <EmptyState
            icon={<Film className="h-5 w-5" />}
            title="Прогонов пока нет"
            description="Исследование начинается с ролика: загрузите видео, соберите аудиторию персон и запустите прогон. Первый отчёт по минутному ролику готов за несколько минут."
            action={{ href: "/studies/new", label: "Запустить первое исследование" }}
          />
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => {
              const ready = task.status === "REPORT_READY";
              const href = ready ? `/runs/${task.id}` : `/runs/${task.id}/progress`;
              return (
                <Link
                  key={task.id}
                  href={href}
                  className="group flex items-center gap-6 rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5 transition-colors hover:border-muted-foreground/40"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                      <h2 className="truncate font-medium">
                        {task.videoRef ?? "Прогон без материала"}
                      </h2>
                      <StatusBadge status={task.status} />
                    </div>
                    <p className="mt-1 truncate text-sm text-muted-foreground">
                      {ago(task.createdAt)}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <Chip tone="outline">
                        {task.mode === "short" ? "Короткое" : "Длинное"} видео
                      </Chip>
                      {task.replicationCount > 1 && (
                        <Chip tone="outline">Перекрытие ×{task.replicationCount}</Chip>
                      )}
                    </div>
                  </div>

                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
