import Link from "next/link";

import { PageHeader } from "@/components/AppShell";
import { requireSession } from "@/lib/server/guard";
import { SurveyEditorForm } from "../SurveyEditorForm";

/**
 * Новая анкета.
 *
 * Отдельный статический маршрут, а не `/surveys/<новый uuid>`: прототип
 * генерировал идентификатор в браузере и открывал редактор по нему, поэтому
 * адрес несохранённой анкеты нельзя было отличить от адреса существующей —
 * и по опечатке в идентификаторе открывалась пустая форма вместо 404.
 *
 * Идентификатор теперь выдаёт база при первом сохранении.
 */

export const dynamic = "force-dynamic";

export default async function NewSurveyPage() {
  await requireSession();

  return (
    <>
      <PageHeader
        title="Новая анкета"
        subtitle="Пять базовых критериев и вопрос о доле просмотра подставлены заранее — их можно править, но последствия правки конструктор показывает сразу."
        actions={
          <Link
            href="/surveys"
            className="rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary"
          >
            К списку
          </Link>
        }
      />

      <div className="p-8">
        <SurveyEditorForm
          initialName={`Анкета от ${new Date().toLocaleDateString("ru-RU")}`}
        />
      </div>
    </>
  );
}
