import Link from "next/link";
import { ChevronRight, FileWarning } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { PROMPT_REGISTRY, loadVariableCounts } from "@/lib/prompt-registry";

/**
 * Промпт-студия (задача #26). Список 13 seed-промптов по стадиям.
 *
 * Число переменных считается из настоящих файлов, а не задано в коде: если
 * шаблон и подпись под ним разойдутся, это должно быть видно сразу, а не в тот
 * момент, когда модель получит незаполненный плейсхолдер.
 *
 * Редактор с валидацией, версиями и dry-run появится вместе с таблицей prompts.
 */

export const dynamic = "force-dynamic";

export default async function PromptsPage() {
  const counts = await loadVariableCounts();
  const stages = [...new Set(PROMPT_REGISTRY.map((p) => p.stage))];
  const missing = PROMPT_REGISTRY.filter((p) => counts[p.key] === null);

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
            Не найдены файлы для {missing.length} промптов: {missing.map((p) => p.key).join(", ")}.
            Реестр ожидает их в каталоге prompts/ в корне монорепо.
          </p>
        )}

        {stages.map((stage) => (
          <section key={stage}>
            <h2 className="mb-3 text-sm font-semibold">{stage}</h2>
            <div className="divide-y divide-border overflow-hidden rounded-lg border border-border">
              {PROMPT_REGISTRY.filter((p) => p.stage === stage).map((p) => {
                const count = counts[p.key];
                return (
                  <Link
                    key={p.key}
                    href={`/prompts/${p.key}`}
                    className="flex items-center gap-4 bg-[hsl(222_47%_7%)] px-5 py-4 transition-colors hover:bg-secondary/40"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-mono text-sm">{p.key}</p>
                      <p className="mt-0.5 truncate text-xs text-muted-foreground">{p.desc}</p>
                    </div>
                    <Chip tone="outline">
                      {count === null ? "файл не найден" : `${count} переменных`}
                    </Chip>
                    <Chip>дефолт</Chip>
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
