import Link from "next/link";
import { notFound } from "next/navigation";

import { PageHeader } from "@/components/AppShell";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { getSurvey } from "@/lib/server/surveys";
import { SurveyEditorForm } from "../SurveyEditorForm";
import { deleteSurveyAction } from "../actions";

/**
 * Редактор существующей анкеты.
 *
 * Страница серверная и делает ровно одно: читает анкету под сессией и отдаёт её
 * конструктору. Прототип на этом месте держал собственный конструктор на 235
 * строк — со своими типами вопросов, своим сохранением в localforage и своим
 * представлением о том, что такое шкала.
 *
 * Анкеты, которой нет, — 404, а не пустая форма. Прототип в этом случае молча
 * заводил новую с тем же идентификатором: опечатка в адресе выглядела как
 * «анкета опустела».
 */

export const dynamic = "force-dynamic";

export default async function SurveyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { tenantId } = await requireSession();
  const survey = await withTenant(tenantId, (client) => getSurvey(client, id));

  if (!survey) notFound();

  return (
    <>
      <PageHeader
        title={survey.name}
        subtitle={`Создана ${new Date(survey.createdAt).toLocaleDateString("ru-RU")} · ${survey.questions.length} вопросов`}
        actions={
          <Link
            href="/surveys"
            className="rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary"
          >
            К списку
          </Link>
        }
      />

      <div className="space-y-8 p-8">
        <SurveyEditorForm
          surveyId={survey.id}
          initialName={survey.name}
          initialQuestions={survey.questions}
        />

        <div className="max-w-xl border-t border-border pt-8">
          <h2 className="mb-1 text-sm font-semibold text-rose-300">Удалить анкету</h2>
          <p className="mb-3 text-xs leading-relaxed text-muted-foreground">
            Прогоны, сделанные по этой анкете, останутся вместе с отчётами — ссылка на
            анкету у них просто опустеет.
          </p>
          <form action={deleteSurveyAction}>
            <input type="hidden" name="id" value={survey.id} />
            <button
              type="submit"
              className="rounded-md border border-rose-500/30 px-4 py-2 text-sm text-rose-300 transition-colors hover:bg-rose-500/10"
            >
              Удалить
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
