"use server";

import { revalidatePath } from "next/cache";

import { normalizeTitle } from "@/lib/research-title";
import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import { renameTask } from "@/lib/server/tasks";

/**
 * Действия над исследованиями из серверных компонентов.
 *
 * Сессия перечитывается в каждом действии, а не берётся из отрисовки страницы.
 * Форма отправляется из браузера, и `tenantId`, полученный при рендере, к
 * моменту отправки уже не доказательство: вкладка могла быть открыта до выхода
 * из учётной записи.
 */
export async function renameResearchAction(form: FormData): Promise<void> {
  const { tenantId } = await requireSession();
  const id = String(form.get("id") ?? "");

  // Пустое значение — законное: означает «убрать своё название», и заголовок
  // возвращается к имени файла. Отвергать его значило бы запирать человека в
  // названии, которое он передумал давать.
  const title = normalizeTitle(form.get("name"));

  await withTenant(tenantId, (client) => renameTask(client, id, title));

  revalidatePath("/researches");
  revalidatePath(`/runs/${id}`);
}
