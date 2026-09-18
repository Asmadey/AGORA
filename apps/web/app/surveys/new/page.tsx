import { ArrowLeft } from "lucide-react";
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
        subtitle="Пятнадцать обязательных вопросов заказчика подставлены заранее и не редактируются. Свои вопросы добавляются поверх."
        back={
          <Link
            href="/surveys"
            aria-label="К списку анкет"
            className="grid h-8 w-8 place-items-center rounded-full border border-hairline text-slate transition-colors hover:border-ink hover:text-ink"
          >
            <ArrowLeft className="h-4 w-4" />
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
