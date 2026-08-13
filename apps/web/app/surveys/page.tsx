import Link from "next/link";
import { ClipboardList } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Chip } from "@/components/agora/Primitives";
import { EmptyState } from "@/components/agora/States";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { listSurveys } from "@/lib/server/surveys";

/**
 * Список анкет.
 *
 * До этой правки экран читал localforage и умел заводить «стандартную анкету
 * Агора» из девяти вопросов типов `rating`, `emotions`, `values`, `nps`, `open`.
 * Валидатор не принимает ни `rating`, ни `values`, ни `nps` — то есть ни одна
 * анкета, созданная на этом экране, не могла быть сохранена в базу и не могла
 * участвовать в прогоне. Экран при этом показывал её в списке и открывал в
 * редакторе.
 *
 * Теперь список читается из таблицы `surveys`, а редактор — тот же
 * `SurveyBuilder`, что стоит в визарде: один конструктор, один набор типов,
 * одна валидация.
 */

export const dynamic = "force-dynamic";

export default async function SurveysPage() {
  const { tenantId } = await requireSession();
  const surveys = await withTenant(tenantId, (client) => listSurveys(client));

  return (
    <>
      <PageHeader
        title="Анкеты"
        subtitle="Что спрашивают у персон после просмотра. Пять базовых критериев обязательны — по ним посчитаны средние в корпусе, и без них результат не с чем сравнивать."
        actions={
          <Link
            href="/surveys/new"
            className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
          >
            Новая анкета
          </Link>
        }
      />

      <div className="p-8">
        {surveys.length === 0 ? (
          <EmptyState
            icon={<ClipboardList className="h-5 w-5" />}
            title="Анкет пока нет"
            description="Новая анкета заводится сразу с пятью базовыми критериями и вопросом о доле просмотра — остальное добавляется поверх."
            action={{ href: "/surveys/new", label: "Создать анкету" }}
          />
        ) : (
          <div className="space-y-2">
            {surveys.map((s) => {
              const custom = s.questions.filter((q) => !q.baseKey).length;
              const hasWatchedShare = s.questions.some((q) => q.type === "watched_share");
              return (
                <Link
                  key={s.id}
                  href={`/surveys/${s.id}`}
                  className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-hairline bg-card p-5 transition-colors hover:border-muted-foreground/40"
                >
                  <span className="min-w-0 flex-1 truncate font-medium">{s.name}</span>

                  <Chip tone="outline">{s.questions.length} вопросов</Chip>
                  {custom > 0 && <Chip tone="outline">{custom} своих</Chip>}
                  {/* Отсутствие вопроса о доле просмотра — не ошибка, но
                      последствие видно только в отчёте, где секция «Досмотрено»
                      останется пустой. Поэтому оно названо здесь, а не там. */}
                  {!hasWatchedShare && (
                    <Chip tone="outline">без доли просмотра</Chip>
                  )}

                  <span className="text-xs text-slate">
                    {new Date(s.createdAt).toLocaleDateString("ru-RU")}
                  </span>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
