import Link from "next/link";
import { ChevronRight, FileWarning } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { PROMPT_REGISTRY } from "@/lib/prompt-registry";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listActivePromptsByStage, type PromptVersion } from "@/lib/server/prompts";

/**
 * Промпт-студия (задача #26). Список промптов по стадиям.
 *
 * Теперь читает из таблицы prompts через резолвер: активная версия арендатора
 * или дефолт. Редактирование, версии и dry-run — на странице промпта.
 *
 * Если сессии нет (до входа), страница не дойдёт до рендера — middleware
 * перенаправит на /login. Но если база недоступна, показываем дефолты из
 * реестра, чтобы интерфейс не падал.
 */

export const dynamic = "force-dynamic";

export default async function PromptsPage() {
  const stages = [...new Set(PROMPT_REGISTRY.map((p) => p.stage))];

  let byStage: Record<string, PromptVersion[]> = {};
  let hasDb = false;
  try {
    const { tenantId } = await requireSession();
    byStage = await withTenant(tenantId, async (client) => {
      return listActivePromptsByStage(client);
    });
    hasDb = true;
  } catch {
    // Без сессии или базы — показываем реестр как fallback.
    hasDb = false;
  }

  // Если база есть, показываем из неё; иначе — из реестра.
  if (hasDb && Object.keys(byStage).length > 0) {
    return (
      <>
        <PageHeader
          title="Промпт-студия"
          subtitle="Все промпты пайплайна редактируются здесь. Версии пиннингуются на прогон, поэтому правка промпта не ломает воспроизводимость прошлых отчётов."
        />
        <div className="space-y-8 p-8">
          {stages.map((stage) => {
            const prompts = byStage[stage] ?? [];
            if (prompts.length === 0) return null;
            return (
              <section key={stage}>
                <h2 className="mb-3 text-sm font-semibold">{stage}</h2>
                <div className="divide-y divide-border overflow-hidden rounded-lg border border-border">
                  {prompts.map((p) => (
                    <Link
                      key={p.key}
                      href={`/prompts/${p.key}`}
                      className="flex items-center gap-4 bg-[hsl(222_47%_7%)] px-5 py-4 transition-colors hover:bg-secondary/40"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-mono text-sm">{p.key}</p>
                        <p className="mt-0.5 truncate text-xs text-muted-foreground">
                          {PROMPT_REGISTRY.find((r) => r.key === p.key)?.desc ?? p.stage}
                        </p>
                      </div>
                      <Chip tone="outline">
                        {p.variables.length} переменных
                      </Chip>
                      <Chip>
                        {p.is_default ? "дефолт" : `v${p.version}`}
                      </Chip>
                      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                    </Link>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </>
    );
  }

  // Fallback: нет базы, показываем из реестра (только для разработки)
  const missing = PROMPT_REGISTRY.filter((p) => !p);
  return (
    <>
      <PageHeader
        title="Промпт-студия"
        subtitle="Все промпты пайплайна редактируются здесь. Версии пиннингуются на прогон, поэтому правка промпта не ломает воспроизводимость прошлых отчётов."
      />
      <div className="space-y-8 p-8">
        {missing.length > 0 && (
          <p className="flex gap-2 rounded-md border border-amber-500/25 bg-amber-500/5 p-3 text-xs leading-relaxed text-amber-200/80">
            <FileWarning className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            База недоступна — показывается реестр без версий и правки.
          </p>
        )}
        {stages.map((stage) => (
          <section key={stage}>
            <h2 className="mb-3 text-sm font-semibold">{stage}</h2>
            <div className="divide-y divide-border overflow-hidden rounded-lg border border-border">
              {PROMPT_REGISTRY.filter((p) => p.stage === stage).map((p) => (
                <Link
                  key={p.key}
                  href={`/prompts/${p.key}`}
                  className="flex items-center gap-4 bg-[hsl(222_47%_7%)] px-5 py-4 transition-colors hover:bg-secondary/40"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-sm">{p.key}</p>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">{p.desc}</p>
                  </div>
                  <Chip tone="outline">реестр</Chip>
                  <Chip>дефолт</Chip>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}