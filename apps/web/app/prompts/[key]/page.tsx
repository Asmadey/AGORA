import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { PROMPT_REGISTRY, findPrompt } from "@/lib/prompt-registry";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { getPromptWithHistory, type PromptVersion } from "@/lib/server/prompts";
import { PromptEditor } from "@/components/agora/PromptEditor";

/**
 * Промпт-студия (задача #26) — страница одного промпта.
 *
 * Теперь показывает редактор с валидацией, панелью версий, кнопками
 * «Сделать активной» и «Вернуть дефолт», предпросмотром подстановки.
 * Редактирование — действие owner, но проверка идёт в API, не в компоненте.
 */

export const dynamic = "force-dynamic";

export function generateStaticParams() {
  return PROMPT_REGISTRY.map((p) => ({ key: p.key }));
}

export default async function PromptDetailPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  const decodedKey = decodeURIComponent(key);
  const meta = findPrompt(decodedKey);
  if (!meta) {
    notFound();
    return null;
  }

  let active: PromptVersion | null = null;
  let history: PromptVersion[] = [];
  let hasDb = false;

  try {
    const { tenantId } = await requireSession();
    const data = await withTenant(tenantId, async (client) => {
      return getPromptWithHistory(client, decodedKey);
    });
    active = data.active;
    history = data.history;
    hasDb = true;
  } catch {
    // Без сессии/базы — страница просто не покажет редактор.
    hasDb = false;
  }

  return (
    <>
      <PageHeader
        title={meta.key}
        subtitle={meta.desc}
        actions={
          <Link
            href="/prompts"
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary"
          >
            <ChevronLeft className="h-4 w-4" />
            К списку
          </Link>
        }
      />

      <div className="max-w-4xl p-8">
        {hasDb && active ? (
          <PromptEditor
            promptKey={meta.key}
            stage={meta.stage}
            desc={meta.desc}
            initialActive={active}
            initialHistory={history}
          />
        ) : (
          <div className="space-y-4">
            <p className="rounded-md border border-amber-500/25 bg-amber-500/5 p-4 text-sm text-amber-200/80">
              {hasDb
                ? "Промпт не найден в базе. Возможно, миграция засева (07_prompts_seed.sql) не применена."
                : "Требуется вход. Войдите, чтобы увидеть редактор промпта."}
            </p>
            <p className="text-xs text-muted-foreground">
              Стадия: {meta.stage}. Описание: {meta.desc}.
            </p>
          </div>
        )}
      </div>
    </>
  );
}