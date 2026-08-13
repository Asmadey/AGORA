import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { getPortraitWithHistory } from "@/lib/server/portraits";
import { PortraitEditor } from "./PortraitEditor";
import { DeletePortraitButton } from "./DeletePortraitButton";

/**
 * Карточка портрета аудитории: правка, история версий, удаление.
 *
 * Экрана не было вовсе, хотя `PUT /api/portraits/{id}` и таблица версий
 * существовали с задачи #24. Портрет можно было создать дистилляцией и нельзя
 * ни поправить, ни удалить: единственным способом изменить его оставался
 * прямой запрос к API.
 */

export const dynamic = "force-dynamic";

const SOURCE_LABEL: Record<string, string> = {
  distilled: "дистиллирован из корпуса",
  manual: "написан руками",
  context_file: "из файла контекста",
};

export default async function PortraitPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { tenantId } = await requireSession();

  const { portrait, history } = await withTenant(tenantId, (client) =>
    getPortraitWithHistory(client, id),
  );

  if (!portrait) notFound();

  return (
    <>
      <PageHeader
        title={portrait.name}
        subtitle={`${SOURCE_LABEL[portrait.source] ?? portrait.source} · обновлён ${new Date(
          portrait.updated_at,
        ).toLocaleDateString("ru-RU")}`}
        actions={
          <Link
            href="/portraits"
            className="inline-flex items-center gap-2 rounded-full border border-hairline px-4 py-2 text-sm transition-colors hover:bg-surface"
          >
            <ArrowLeft className="h-4 w-4" />К списку
          </Link>
        }
      />

      <div className="max-w-4xl space-y-8 p-8">
        <PortraitEditor
          portraitId={portrait.id}
          initialName={portrait.name}
          initialBody={portrait.body_md}
        />

        <section className="border-t border-hairline pt-8">
          <h2 className="text-sm font-semibold">История версий</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate">
            Портрет управляет генерацией всех последующих персон, поэтому каждая правка
            сохраняется отдельной версией: неудачное изменение меняет состав аудитории в
            прогонах, запущенных после него, и вернуться надо иметь куда.
          </p>

          {history.length === 0 ? (
            <p className="mt-4 text-sm text-slate">
              Правок ещё не было — портрет в том виде, в котором создан.
            </p>
          ) : (
            <ul className="mt-4 space-y-2">
              {history.map((v) => (
                <li
                  key={v.id}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-hairline bg-card px-4 py-3 text-sm"
                >
                  <Chip tone="outline">версия {v.version}</Chip>
                  <span className="text-slate">
                    {new Date(v.created_at).toLocaleString("ru-RU")}
                  </span>
                  <span className="text-stone">{v.editor}</span>
                  <span className="ml-auto text-xs text-stone">
                    {v.body_md.length.toLocaleString("ru-RU")} символов
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="border-t border-hairline pt-8">
          <h2 className="mb-1 text-sm font-semibold text-danger">Удалить портрет</h2>
          <p className="mb-3 max-w-xl text-xs leading-relaxed text-slate">
            Уйдут все {history.length} версий. Персоны, сгенерированные с этим портретом,
            останутся: их DNA самодостаточна, и терять аудиторию прогонов из-за уборки в
            портретах было бы дороже, чем хранить лишний текст.
          </p>
          <DeletePortraitButton portraitId={portrait.id} name={portrait.name} />
        </section>
      </div>
    </>
  );
}
