import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { EmptyState } from "@/components/agora/States";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listPortraits } from "@/lib/server/portraits";
import { ScrollText } from "lucide-react";

/**
 * Портреты аудиторий (задача #24).
 *
 * До этого экран рисовал жёстко зашитый список из четырёх портретов: выглядел
 * наполненным на пустом арендаторе и не обращался к базе вовсе, хотя
 * `lib/server/portraits.ts` и маршруты были написаны.
 *
 * Витрина остаётся витриной: редактор и авто-дистилляция живут на своих
 * маршрутах, здесь только список и то, чем портрет узнаётся.
 */

export const dynamic = "force-dynamic";

const SOURCE_LABEL: Record<string, string> = {
  distilled: "дистиллирован из корпуса",
  manual: "написан руками",
  context_file: "из файла контекста",
};

/**
 * Первый абзац портрета — без markdown-разметки заголовков и списков.
 *
 * Полный текст в карточке списка не нужен, а рисовать сырой markdown значило бы
 * показывать решётки и звёздочки как содержание.
 */
function excerpt(bodyMd: string, limit = 220): string {
  const firstParagraph = bodyMd
    .split(/\n{2,}/)
    .map((block) => block.replace(/^[#>\s*-]+/, "").trim())
    .find((block) => block.length > 0);

  if (!firstParagraph) return "";
  return firstParagraph.length > limit
    ? `${firstParagraph.slice(0, limit).trimEnd()}…`
    : firstParagraph;
}

function updatedAt(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("ru-RU");
}

export default async function PortraitsPage() {
  const { tenantId } = await requireSession();
  const portraits = await withTenant(tenantId, listPortraits);

  return (
    <>
      <PageHeader
        title="Портреты аудиторий"
        subtitle="Описания сегментов, которые подмешиваются в генерацию персон. Портрет уточняет персон, но не переопределяет заземление на корпус."
      />

      <div className="p-8">
        {portraits.length === 0 ? (
          <EmptyState
            icon={<ScrollText className="h-5 w-5" />}
            title="Портретов пока нет"
            description="Портрет — это описание сегмента, которое уточняет генерацию персон: как сегмент смотрит, по чему принимает решение, что его отталкивает. Его можно написать руками или дистиллировать из grounding-корпуса."
            action={{ href: "/personas", label: "К реестру персон" }}
          />
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {portraits.map((p) => {
              const preview = excerpt(p.body_md);
              return (
                <article
                  key={p.id}
                  className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5 transition-colors hover:border-muted-foreground/40"
                >
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="font-medium">{p.name}</h2>
                    <Chip tone="outline">{SOURCE_LABEL[p.source] ?? p.source}</Chip>
                  </div>
                  {preview ? (
                    <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                      {preview}
                    </p>
                  ) : (
                    // Пустой портрет показывается как пустой, а не пропускается:
                    // исчезнувшая из списка запись читается как потерянная.
                    <p className="mt-3 text-sm italic text-muted-foreground">
                      Текст портрета пуст — на генерацию персон он не повлияет.
                    </p>
                  )}
                  <p className="mt-4 text-xs text-muted-foreground">
                    Обновлён {updatedAt(p.updated_at)}
                  </p>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
