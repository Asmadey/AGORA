import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft, Lock } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { PROMPT_REGISTRY, findPrompt, loadPromptSource } from "@/lib/prompt-registry";

/**
 * Просмотр одного промпта (задача #26).
 *
 * Показывает текст ровно как он лежит в seed-файле, включая {{плейсхолдеры}} —
 * подсвеченные, но не подставленные. Подставлять сюда примерные значения было бы
 * вредно: человек, который правит промпт, должен видеть шаблон, а не один из его
 * возможных результатов.
 */

export const dynamic = "force-dynamic";

export function generateStaticParams() {
  return PROMPT_REGISTRY.map((p) => ({ key: p.key }));
}

/** Разбивает текст на куски, помечая плейсхолдеры, чтобы подсветить их в разметке. */
function segment(text: string): { text: string; isVar: boolean }[] {
  const parts: { text: string; isVar: boolean }[] = [];
  const re = /\{\{\s*[a-zA-Z0-9_.]+\s*\}\}/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    const at = m.index ?? 0;
    if (at > last) parts.push({ text: text.slice(last, at), isVar: false });
    parts.push({ text: m[0], isVar: true });
    last = at + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), isVar: false });
  return parts;
}

export default async function PromptDetailPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  const meta = findPrompt(decodeURIComponent(key));
  if (!meta) {
    notFound();
    return null;
  }

  const source = await loadPromptSource(meta.key);

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

      <div className="max-w-4xl space-y-6 p-8">
        <div className="flex flex-wrap gap-2">
          <Chip tone="outline">стадия: {meta.stage}</Chip>
          <Chip tone="outline">версия: seed</Chip>
          <Chip>активна</Chip>
        </div>

        {!source ? (
          <p className="rounded-md border border-rose-500/25 bg-rose-500/5 p-4 text-sm text-rose-200/80">
            Файл prompts/{meta.key}.md не найден. Реестр знает про этот промпт, но текста
            для него на диске нет — пайплайн упадёт на этой стадии.
          </p>
        ) : (
          <>
            <section>
              <h2 className="text-sm font-semibold">Переменные</h2>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Извлечены из самого шаблона. После переезда реестра в БД валидатор будет
                отвергать промпт, где встретилась переменная, не объявленная в контракте
                стадии — сейчас это просто список того, что фактически используется.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {source.variables.length === 0 ? (
                  <span className="text-sm text-muted-foreground">
                    Плейсхолдеров нет — шаблон статический.
                  </span>
                ) : (
                  source.variables.map((v) => (
                    <code
                      key={v}
                      className="rounded border border-sky-500/30 bg-sky-500/10 px-2 py-1 font-mono text-xs text-sky-200"
                    >
                      {v}
                    </code>
                  ))
                )}
              </div>
            </section>

            {source.header && (
              <section>
                <h2 className="text-sm font-semibold">Заметка к промпту</h2>
                <p className="mt-2 whitespace-pre-wrap rounded-md border border-border bg-[hsl(222_47%_7%)] p-4 text-sm leading-relaxed text-muted-foreground">
                  {source.header}
                </p>
              </section>
            )}

            <section>
              <h2 className="text-sm font-semibold">Шаблон</h2>
              <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-md border border-border bg-[hsl(222_47%_7%)] p-4 font-mono text-[13px] leading-relaxed">
                {segment(source.template).map((part, i) =>
                  part.isVar ? (
                    <span key={i} className="rounded bg-sky-500/15 px-1 text-sky-200">
                      {part.text}
                    </span>
                  ) : (
                    <span key={i}>{part.text}</span>
                  ),
                )}
              </pre>
            </section>
          </>
        )}

        <p className="flex gap-2 rounded-md border border-border p-4 text-xs leading-relaxed text-muted-foreground">
          <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            Только чтение. Редактирование, версии, переключение активной версии и dry-run
            требуют таблицы prompts с историей — иначе правка меняла бы seed-дефолт сразу
            для всех арендаторов и без возможности отката. Это задача #26, она ждёт #2 и #3.
          </span>
        </p>
      </div>
    </>
  );
}
