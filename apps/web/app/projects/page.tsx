import Link from "next/link";
import { FolderKanban } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { EmptyState } from "@/components/agora/States";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listProjects, type ProjectRun } from "@/lib/server/projects";

/**
 * Список проектов.
 *
 * До этой правки экран читал `db.projects.getAll()` — обёртку над localforage,
 * то есть IndexedDB одной вкладки. На скриншоте разницы не было никакой:
 * карточки рисовались, счётчик эпизодов считался, удаление удаляло. Разница
 * обнаруживалась у второго человека, открывшего тот же адрес, — он видел пустой
 * список и не имел способа понять, почему.
 *
 * Прототипный проект хранил в себе эпизоды, выбранную аудиторию, анкету и
 * статус. В схеме ничего этого нет: `projects` — это имя и время создания, а
 * всё остальное принадлежит прогону (`tasks`). Поэтому карточка проекта —
 * имя и его прогоны, а статус не хранится, а выводится: хранимый разошёлся бы
 * с прогонами при первом отказе воркера, и разошёлся бы молча.
 */

export const dynamic = "force-dynamic";

/**
 * Состояние проекта по его прогонам.
 *
 * Считается на экране, и это не нарушение правила «интерфейс не считает»:
 * правило про величины отчёта, которые обязаны совпадать с воркером. Здесь
 * никакой величины нет — есть подпись над списком статусов, лежащих рядом.
 */
function projectState(runs: ProjectRun[]): { label: string; tone: "muted" | "outline" | "solid" } {
  if (runs.length === 0) return { label: "Черновик", tone: "outline" };
  if (runs.some((r) => r.status === "RUNNING" || r.status === "QUEUED")) {
    return { label: "Идёт прогон", tone: "solid" };
  }
  if (runs.some((r) => r.status === "REPORT_READY")) return { label: "Есть отчёт", tone: "muted" };
  return { label: "Прогон не удался", tone: "outline" };
}

export default async function ProjectsPage() {
  const { tenantId } = await requireSession();
  const projects = await withTenant(tenantId, (client) => listProjects(client));

  return (
    <>
      <PageHeader
        title="Проекты"
        subtitle="Проект группирует прогоны по одному материалу: разные аудитории, разные анкеты, разные версии ролика — в одном месте."
        actions={
          <Link
            href="/projects/new"
            className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
          >
            Новый проект
          </Link>
        }
      />

      <div className="p-8">
        {projects.length === 0 ? (
          <EmptyState
            icon={<FolderKanban className="h-5 w-5" />}
            title="Проектов пока нет"
            description="Проект — это папка для прогонов по одному материалу. Создайте первый, чтобы запускать исследования и сравнивать их между собой."
            action={{ href: "/projects/new", label: "Создать проект" }}
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {projects.map((p) => {
              const state = projectState(p.runs);
              const ready = p.runs.filter((r) => r.status === "REPORT_READY").length;
              return (
                <Link
                  key={p.id}
                  href={`/projects/${p.id}`}
                  className="flex flex-col rounded-lg border border-hairline bg-card p-5 transition-colors hover:border-muted-foreground/40"
                >
                  <h2 className="truncate font-medium">{p.name}</h2>

                  <div className="mt-4 flex flex-wrap items-center gap-1.5">
                    <Chip tone={state.tone}>{state.label}</Chip>
                    <Chip tone="outline">
                      {p.runs.length === 0
                        ? "без прогонов"
                        : `${p.runs.length} ${plural(p.runs.length, "прогон", "прогона", "прогонов")}`}
                    </Chip>
                    {ready > 0 && <Chip tone="outline">{ready} с отчётом</Chip>}
                  </div>

                  <p className="mt-4 text-xs text-slate">
                    Создан {new Date(p.createdAt).toLocaleDateString("ru-RU")}
                  </p>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

/** Русское склонение по числу: «1 прогон», «2 прогона», «5 прогонов». */
function plural(n: number, one: string, few: string, many: string): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return many;
  const mod10 = n % 10;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}
