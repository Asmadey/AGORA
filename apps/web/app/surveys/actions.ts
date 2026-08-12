"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { deleteSurvey } from "@/lib/server/surveys";

/**
 * Удаление анкеты.
 *
 * Отдельно от `PUT /api/surveys`, потому что удаление ничего не валидирует, а
 * форма на серверном компоненте не должна ради этого идти через fetch.
 *
 * Прогоны, ссылавшиеся на анкету, не удаляются: `tasks.survey_id` объявлен
 * `ON DELETE SET NULL`. Отчёт уже посчитан, и терять его из-за уборки в списке
 * анкет — потеря результата ради порядка.
 */
export async function deleteSurveyAction(form: FormData): Promise<void> {
  const { tenantId } = await requireSession();
  const id = String(form.get("id") ?? "");

  await withTenant(tenantId, (client) => deleteSurvey(client, id));
  revalidatePath("/surveys");
  redirect("/surveys");
}
