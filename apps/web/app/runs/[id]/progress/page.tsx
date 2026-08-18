import { notFound } from "next/navigation";

import { PageHeader } from "@/components/AppShell";
import { ProgressView } from "@/components/agora/ProgressView";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { loadRunTiming } from "@/lib/server/tasks";

/**
 * Страница прогресса прогона (задача #12).
 *
 * До этой задачи здесь стояла витрина: список узлов двигался по таймеру
 * независимо от того, что происходит на воркере. Опасность такой заглушки не в
 * том, что она врёт, а в том, что врёт правдоподобно — от рабочего экрана она
 * неотличима до первого настоящего отказа, который она покажет как успех.
 *
 * Режим (short | long) читается на сервере и передаётся в клиентский компонент:
 * от него зависит, есть ли в шкале узел нарезки на фрагменты. Спрашивать режим
 * у SSE-потока нельзя — до первого события шкала уже нарисована, и она мигала
 * бы, перестраиваясь на четырнадцать пунктов из тринадцати.
 */

export const dynamic = "force-dynamic";

export default async function ProgressPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { tenantId } = await requireSession();

  // started_at/finished_at нужны таймеру. Без них он считал бы от загрузки
  // страницы: обновление на десятой минуте показывало бы «0:03», а открытая со
  // вчера вкладка — сутки прогона, которого давно нет.
  const row = await withTenant(tenantId, async (client) => {
    const { rows } = await client.query<{
      mode: string;
      status: string;
      started_at: Date | null;
      finished_at: Date | null;
    }>(
      "SELECT mode, status, started_at, finished_at FROM tasks WHERE id = $1::uuid",
      [id],
    );
    return rows[0] ?? null;
  });

  // Длительности шагов лежат в progress.timings — их пишет воркер в конце
  // прогона. На идущем прогоне словарь пуст, и ProgressView считает текущий шаг
  // сам по времени события.
  const timing = await withTenant(tenantId, (client) => loadRunTiming(client, id));
  const durations = Object.fromEntries(
    timing.nodes.flatMap((n) => (n.durationSec === null ? [] : [[n.node, n.durationSec]])),
  );

  // RLS уже отрезал чужих арендаторов: строки просто нет. «Не ваш прогон» и
  // «нет такого» отвечают одинаково намеренно — разные ответы сами по себе
  // сообщали бы о существовании чужого прогона.
  if (!row) {
    notFound();
    return null;
  }

  return (
    <>
      <PageHeader title="Прогресс исследования" subtitle={`Прогон ${id}`} />
      <div className="p-8">
        <ProgressView
          taskId={id}
          mode={row.mode === "long" ? "long" : "short"}
          startedAt={row.started_at?.toISOString() ?? null}
          finishedAt={row.finished_at?.toISOString() ?? null}
          durations={durations}
        />
      </div>
    </>
  );
}
