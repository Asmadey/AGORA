import Link from "next/link";
import { notFound } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Film,
  Loader2,
} from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { ProjectTitle } from "@/components/agora/ProjectTitle";
import { EmptyState } from "@/components/agora/States";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { getProject, type ProjectRun } from "@/lib/server/projects";
import { deleteProjectAction, renameProjectAction } from "../actions";

/**
 * Карточка проекта: имя, прогоны, запуск нового.
 *
 * Заменяет 672 строки прототипа. Прежний экран делал вид, что проводит
 * исследование: выбирал аудиторию, «опрашивал» её через `/api/simulate`, строил
 * отчёт через `/api/report` и давал чат по результатам — всё на Gemini, всё
 * мимо воркера, всё в localforage. Настоящий прогон идёт другим путём:
 * `POST /api/tasks` → очередь Valkey → воркер → отчёт в Mongo, и занимает
 * десятки минут вместо секунд.
 *
 * Два контура, дающие «отчёт» по одному ролику, — это не запасной вариант, а
 * ловушка: у их результатов разное происхождение и одинаковый вид, и узнать,
 * какой открыт, по экрану нельзя.
 *
 * ─── 404, а не 403 ─────────────────────────────────────────────────────────
 * Чужой проект под RLS не находится, и это тот же ответ, что на
 * несуществующий идентификатор. `notFound()` — ровно то, что означает такой
 * результат: «не существует или принадлежит другой команде».
 */

export const dynamic = "force-dynamic";

type Status = ProjectRun["status"];

const BADGE: Record<Status, { label: string; icon: React.ElementType; cls: string }> = {
  QUEUED: { label: "В очереди", icon: Clock, cls: "text-slate" },
  RUNNING: { label: "Идёт прогон", icon: Loader2, cls: "text-brand-blue" },
  REPORT_READY: { label: "Отчёт готов", icon: CheckCircle2, cls: "text-success" },
  FAILED: { label: "Ошибка", icon: AlertTriangle, cls: "text-danger" },
};

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { tenantId } = await requireSession();
  const project = await withTenant(tenantId, (client) => getProject(client, id));

  if (!project) notFound();

  return (
    <>
      <PageHeader
        title={
          <ProjectTitle id={project.id} name={project.name} action={renameProjectAction} />
        }
        subtitle={`Создан ${new Date(project.createdAt).toLocaleDateString("ru-RU")}`}
        actions={
          <Link
            href={`/studies/new?project=${project.id}`}
            className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
          >
            Запустить исследование
          </Link>
        }
      />

      <div className="space-y-8 p-8">
        <section>
          <h2 className="mb-4 text-sm font-semibold">Прогоны</h2>

          {project.runs.length === 0 ? (
            <EmptyState
              icon={<Film className="h-5 w-5" />}
              title="Прогонов ещё не было"
              description="Визард запуска спросит ролик, аудиторию и анкету, а затем поставит задачу в очередь. Разбор идёт десятки минут — за ним можно следить на экране прогресса."
              action={{ href: `/studies/new?project=${project.id}`, label: "Запустить исследование" }}
            />
          ) : (
            <div className="space-y-2">
              {project.runs.map((run) => {
                const badge = BADGE[run.status];
                const Icon = badge?.icon ?? Clock;
                // Отчёт открывается только когда он есть; до этого строка ведёт
                // на прогресс. Ссылка на пустой отчёт выглядела бы как потерянный
                // результат, хотя прогон просто ещё идёт.
                const href =
                  run.status === "REPORT_READY" ? `/runs/${run.id}` : `/runs/${run.id}/progress`;
                return (
                  <Link
                    key={run.id}
                    href={href}
                    className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-hairline bg-card p-4 transition-colors hover:border-muted-foreground/40"
                  >
                    <span
                      className={`flex shrink-0 items-center gap-1.5 text-sm ${badge?.cls ?? "text-slate"}`}
                    >
                      <Icon
                        className={`h-4 w-4 ${run.status === "RUNNING" ? "animate-spin" : ""}`}
                      />
                      {badge?.label ?? run.status}
                    </span>

                    <span className="flex flex-wrap items-center gap-1.5">
                      <Chip tone="outline">{run.mode === "long" ? "длинный" : "короткий"}</Chip>
                      {run.replicationCount > 1 && (
                        <Chip tone="outline">перекрытие ×{run.replicationCount}</Chip>
                      )}
                    </span>

                    <span className="text-xs text-slate">
                      {new Date(run.createdAt).toLocaleString("ru-RU")}
                    </span>

                    {/* Причина отказа показывается в строке, а не прячется за
                        переходом: без неё «Ошибка» означает только то, что
                        что-то не вышло, и следующий шаг пользователю неизвестен. */}
                    {run.error && (
                      <span className="w-full break-words font-mono text-xs text-danger">
                        {run.error}
                      </span>
                    )}

                    <ArrowRight className="ml-auto h-4 w-4 shrink-0 text-slate" />
                  </Link>
                );
              })}
            </div>
          )}
        </section>

        <section className="max-w-xl space-y-6 border-t border-hairline pt-8">
          <div>
            <h2 className="mb-1 text-sm font-semibold text-danger">Удалить проект</h2>
            <p className="mb-3 text-xs leading-relaxed text-slate">
              Вместе с проектом уйдут все его прогоны — {project.runs.length}. Отменить нельзя.
            </p>
            <form action={deleteProjectAction}>
              <input type="hidden" name="id" value={project.id} />
              <button
                type="submit"
                className="rounded-md border border-danger/40 px-4 py-2 text-sm text-danger transition-colors hover:bg-danger-soft"
              >
                Удалить
              </button>
            </form>
          </div>
        </section>
      </div>
    </>
  );
}
