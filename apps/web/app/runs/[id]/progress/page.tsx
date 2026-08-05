import { notFound } from "next/navigation";

import { PageHeader } from "@/components/AppShell";
import { ProgressView } from "@/components/agora/ProgressView";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";

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

  const row = await withTenant(tenantId, async (client) => {
    const { rows } = await client.query<{ mode: string; status: string }>(
      "SELECT mode, status FROM tasks WHERE id = $1::uuid",
      [id],
    );
    return rows[0] ?? null;
  });

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
        <ProgressView taskId={id} mode={row.mode === "long" ? "long" : "short"} />
      </div>
    </>
  );
}
