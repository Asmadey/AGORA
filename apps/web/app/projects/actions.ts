"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { withTenant } from "@/lib/server/db";
import { requireSession } from "@/lib/server/guard";
import {
  createProject,
  deleteProject,
  renameProject,
} from "@/lib/server/projects";

/**
 * Действия над проектами из серверных компонентов.
 *
 * Формы отправляются сюда, а не в `/api/projects`: серверное действие уже
 * выполняется на сервере, и виток через собственный HTTP-маршрут добавил бы
 * запрос, сериализацию и второй способ ошибиться. Маршрут остаётся для внешних
 * клиентов и сквозной проверки — у них своей страницы нет.
 *
 * Сессия перечитывается в каждом действии. Форма отправляется из браузера
 * пользователя, и `tenantId`, полученный при отрисовке страницы, к моменту
 * отправки уже не доказательство: вкладка могла быть открыта до выхода из
 * учётной записи.
 */

const MAX_NAME = 200;

function readName(form: FormData): string {
  const name = String(form.get("name") ?? "").trim();
  if (!name) throw new Error("Название проекта не может быть пустым");
  if (name.length > MAX_NAME) {
    throw new Error(`Название длиннее ${MAX_NAME} символов`);
  }
  return name;
}

export async function createProjectAction(form: FormData): Promise<void> {
  const { tenantId, userId } = await requireSession();
  const name = readName(form);

  const project = await withTenant(tenantId, (client) =>
    createProject(client, { name, createdBy: userId }),
  );

  // redirect бросает исключение управления потоком, поэтому стоит после всех
  // обращений к базе, а не внутри withTenant: изнутри он выглядел бы отказом
  // транзакции и откатил бы вставку.
  revalidatePath("/projects");
  redirect(`/projects/${project.id}`);
}

export async function renameProjectAction(form: FormData): Promise<void> {
  const { tenantId } = await requireSession();
  const id = String(form.get("id") ?? "");
  const name = readName(form);

  await withTenant(tenantId, (client) => renameProject(client, id, name));
  revalidatePath("/projects");
  revalidatePath(`/projects/${id}`);
}

export async function deleteProjectAction(form: FormData): Promise<void> {
  const { tenantId } = await requireSession();
  const id = String(form.get("id") ?? "");

  await withTenant(tenantId, (client) => deleteProject(client, id));
  revalidatePath("/projects");
  redirect("/projects");
}
