import Link from "next/link";
import { Loader2, CheckCircle2, Clock, AlertTriangle, Ban, Film } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { EmptyState } from "@/components/agora/States";
import { DeleteRunButton } from "@/components/agora/DeleteRunButton";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listTasks, taskNumber } from "@/lib/server/tasks";
import { safePresign } from "@/lib/server/content-pack";
import { InlineRename } from "@/components/agora/InlineRename";
import { researchTitle } from "@/lib/research-title";
import { renameResearchAction } from "./actions";

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

type Status = "QUEUED" | "RUNNING" | "REPORT_READY" | "FAILED" | "CANCELLED";

const BADGE: Record<Status, { label: string; icon: React.ElementType; cls: string }> = {
  QUEUED: { label: "В очереди", icon: Clock, cls: "text-slate" },
  RUNNING: { label: "Идёт прогон", icon: Loader2, cls: "text-brand-blue" },
  REPORT_READY: { label: "Отчёт готов", icon: CheckCircle2, cls: "text-success" },
  FAILED: { label: "Ошибка", icon: AlertTriangle, cls: "text-danger" },
  // Отдельно от «Ошибки»: отменённый прогон — не отказ системы, и в
  // списке они не должны выглядеть одинаково.
  CANCELLED: { label: "Отменён", icon: Ban, cls: "text-stone" },
};

function StatusBadge({ status }: { status: string }) {
  // Неизвестный статус рисуется как есть, а не отбрасывается: воркер может
  // завести новый, и молча пропавшая подпись выглядела бы как «без статуса».
  const known = BADGE[status as Status];
  if (!known) {
    return <span className="text-xs text-slate">{status}</span>;
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
  // Подписи живут час и потому считаются на каждый показ, а не хранятся.
  const posters = Object.fromEntries(
    tasks.flatMap((t) => {
      const url = t.posterRef ? safePresign(t.posterRef) : null;
      return url ? [[t.id, url] as const] : [];
    }),
  );

  return (
    <>
      <PageHeader
        title="Исследования"
        subtitle="Исследования по вашим материалам. Отчёт появляется через несколько минут после запуска."
      />

      <div className="p-8">
        {tasks.length === 0 ? (
          <EmptyState
            icon={<Film className="h-5 w-5" />}
            title="Исследований пока нет"
            description="Исследование начинается с ролика: загрузите видео, соберите аудиторию персон и запустите прогон. Первый отчёт по минутному ролику готов за несколько минут."
            action={{ href: "/studies/new", label: "Запустить первое исследование" }}
          />
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => {
              const ready = task.status === "REPORT_READY";
              const href = ready ? `/runs/${task.id}` : `/runs/${task.id}/progress`;
              return (
                /*
                  Ссылка — накладкой поверх карточки, а не обёрткой вокруг неё.
                  Причина не в вёрстке: рядом с заголовком появилось
                  переименование, а форма с полем ввода внутри <a> — это и
                  недопустимая разметка, и сломанное поведение: Enter в поле
                  одновременно отправляет форму и переходит по ссылке.

                  Накладка решает обе задачи разом: кликом по любому свободному
                  месту карточка по-прежнему открывается, а интерактивные
                  элементы лежат выше неё по z-index и получают свои клики.
                */
                <div
                  key={task.id}
                  className="group relative flex items-center gap-6 rounded-xl border border-hairline bg-card p-5 pr-14 transition-colors hover:border-hairline-strong"
                >
                  <Link href={href} className="absolute inset-0 z-0 rounded-xl">
                    <span className="sr-only">Открыть исследование</span>
                  </Link>
                  {/*
                    Заставка слева, до всего текста. Ключ лежит в самой задаче
                    (`tasks.poster_ref`), а не достаётся из пакета в Mongo: сто
                    прогонов означали бы сто запросов ради картинки в углу.
                  */}
                  {posters[task.id] ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                      src={posters[task.id]!}
                      alt=""
                      className="h-16 w-28 shrink-0 rounded-md object-cover"
                    />
                  ) : (
                    <span className="h-16 w-28 shrink-0 rounded-md bg-secondary" />
                  )}

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                      {taskNumber(task.seqNo) && (
                        <span className="shrink-0 font-mono text-sm tabular-nums text-slate">
                          {taskNumber(task.seqNo)}
                        </span>
                      )}
                      {/*
                        Название исследования: своё, если задано, иначе имя
                        файла. Раньше здесь стоял ключ S3 — узнать в нём свой
                        ролик нельзя, а именно по заголовку исследование и ищут
                        глазами.

                        `z-10` обязателен: под заголовком лежит накладная
                        ссылка, и без подъёма карандаш ловил бы её клик вместо
                        своего.
                      */}
                      <h2 className="relative z-10 min-w-0 font-medium">
                        <InlineRename
                          id={task.id}
                          name={researchTitle(task)}
                          action={renameResearchAction}
                          label="Название исследования"
                          required={false}
                          inputClassName="text-base"
                        />
                      </h2>
                      <StatusBadge status={task.status} />
                    </div>
                    <p className="mt-1 truncate text-sm text-slate">
                      {ago(task.createdAt)}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <Chip tone="outline">
                        {task.mode === "short" ? "Короткое" : "Длинное"} видео
                      </Chip>
                      {task.replicationCount > 1 && (
                        <Chip tone="outline">Перекрытие ×{task.replicationCount}</Chip>
                      )}
                      {/* Автор писался в базу с самого начала и не читался ни
                          одним SELECT: в команде из нескольких человек понять,
                          чей это прогон, было нельзя. */}
                      {task.author && <Chip tone="outline">Автор: {task.author}</Chip>}
                    </div>
                  </div>

                  {/* Крестик справа вверху, поверх карточки: в потоке он бы
                      сдвигал содержимое, когда превращается в подтверждение. */}
                  <DeleteRunButton runId={task.id} className="absolute right-3 top-3 z-10" />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
