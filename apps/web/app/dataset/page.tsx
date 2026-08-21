import { PageHeader } from "@/components/AppShell";
import { CorpusBrowser } from "@/components/agora/CorpusBrowser";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listDatasets } from "@/lib/server/corpus-db";

/**
 * Раздел «Датасет» (этап Е): датасеты, записи, правка.
 *
 * ─── Зачем раздел ──────────────────────────────────────────────────────────
 * Датасет — 165 сессий реальных респондентов — определяет всю выдачу продукта:
 * из него считаются доли по возрасту, гео, полу и ценностям, и по этим долям
 * сэмплируются персоны. До этого он лежал файлом в репозитории, то есть
 * принадлежал разработчику, а не исследователю: правка означала коммит и
 * пересборку образа воркера.
 *
 * ─── Почему правка не ломает прежние исследования ──────────────────────────
 * Каждая аудитория снимает слепок корпуса в момент создания, и генератор
 * сэмплирует по слепку. Правка меняет будущие аудитории и не трогает прошлые.
 * Без этого правка ломала бы воспроизводимость молча: тот же seed по
 * изменившемуся корпусу даёт другую аудиторию, а выглядит она так же
 * правдоподобно.
 */

export const dynamic = "force-dynamic";

export default async function CorpusPage() {
  const { tenantId } = await requireSession();
  const datasets = await withTenant(tenantId, (client) => listDatasets(client));

  return (
    <>
      <PageHeader
        title="Датасет"
        subtitle={
          datasets.length === 0
            ? "Пока пуст"
            : `${datasets.length} ${datasets.length === 1 ? "датасет" : "датасета"} · ` +
              `${datasets.reduce((sum, d) => sum + d.recordsCount, 0)} записей`
        }
      />
      <div className="p-8">
        {datasets.length === 0 ? (
          <div className="max-w-2xl space-y-3 text-sm text-slate">
            <p>
              Датасет в базе пуст. Пока он пуст, персоны собираются по файлу из
              образа воркера — это работает, но версия корпуса у таких аудиторий
              остаётся неизвестной, и воспроизвести их по seed нельзя.
            </p>
            <p>Засеять из файла исследования:</p>
            <pre className="overflow-x-auto rounded-md border border-hairline bg-secondary p-3 text-xs">
              node apps/web/scripts/seed-corpus.mjs --team-id {tenantId}
            </pre>
          </div>
        ) : (
          <CorpusBrowser datasets={datasets} />
        )}
      </div>
    </>
  );
}
