import { notFound } from "next/navigation";

import { PageHeader } from "@/components/AppShell";
import { ProgressView } from "@/components/agora/ProgressView";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { resolveRun } from "@/lib/server/run-ref";
import { loadRunTiming } from "@/lib/server/tasks";
import { audienceStage } from "@/lib/audience-stage";

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
  const { id: slug } = await params;
  const { tenantId } = await requireSession();

  // Тот же разбор, что у отчёта: страницы обязаны понимать одинаковые адреса,
  // иначе переход между вкладками одного прогона даёт 404.
  const run = await resolveRun(slug, tenantId, "/progress");
  if (!run) notFound();
  const id = run.id;

  // started_at/finished_at нужны таймеру. Без них он считал бы от загрузки
  // страницы: обновление на десятой минуте показывало бы «0:03», а открытая со
  // вчера вкладка — сутки прогона, которого давно нет.
  // Набор персон читается тем же запросом, что и сам прогон.
  //
  // Создание персон — отдельная задача Celery над отдельной строкой, и в графе
  // воркера его нет. Но воркер один, и прогон, запущенный сразу после выбора
  // «создать 100 персон», честно стоит в очереди за своей же аудиторией. Без
  // этой строки экран показывал «Разбор файла» и ноль секунд на нём — то есть
  // выглядел зависшим ровно тогда, когда всё работало.
  //
  // `LEFT JOIN`: ссылка объявлена `ON DELETE SET NULL`, и у старого прогона её
  // может не быть. Тогда этап просто не рисуется — см. `audienceStage`.
  const row = await withTenant(tenantId, async (client) => {
    const { rows } = await client.query<{
      mode: string;
      status: string;
      started_at: Date | null;
      finished_at: Date | null;
      set_name: string | null;
      set_status: string | null;
      set_size: number | null;
      set_generated: number | null;
      set_error: string | null;
    }>(
      `SELECT t.mode, t.status, t.started_at, t.finished_at,
              ps.name AS set_name, ps.status AS set_status, ps.size AS set_size,
              ps.generated_count AS set_generated, ps.error AS set_error
         FROM tasks t
         LEFT JOIN persona_sets ps ON ps.id = t.persona_set_id
        WHERE t.id = $1::uuid`,
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
          taskStatus={row.status}
          audience={audienceStage(
            row.set_status === null
              ? null
              : {
                  name: row.set_name ?? "Аудитория",
                  status: row.set_status,
                  size: Number(row.set_size ?? 0),
                  generatedCount: Number(row.set_generated ?? 0),
                  error: row.set_error,
                },
          )}
        />
      </div>
    </>
  );
}
