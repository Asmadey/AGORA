import Link from "next/link";

import { PageHeader } from "@/components/AppShell";
import { requireSession } from "@/lib/server/guard";
import { createProjectAction } from "../actions";

/**
 * Создание проекта.
 *
 * Форма из одного поля, и это сокращение с 247 строк прототипа — намеренное.
 * Прежний экран собирал здесь эпизоды, выбор аудитории, выбор анкеты и загрузку
 * ролика, то есть повторял визард запуска, но складывал результат в localforage
 * и в схему, которой нет. Два места, где заводится одно и то же, расходятся
 * молча — и разошлись: типы вопросов в конструкторе анкет прототипа
 * (`rating`, `values`, `nps`, `matrix`, `slogan`) не совпадают ни с одним из
 * шести типов, которые принимает валидатор.
 *
 * Всё, что относится к прогону, спрашивает визард `/studies/new` — он
 * единственный, кто умеет довести это до `POST /api/tasks`.
 */

export const dynamic = "force-dynamic";

export default async function NewProjectPage() {
  // Сессия спрашивается до отрисовки формы: экран, показанный без сессии,
  // предложил бы заполнить поле и отказал бы уже после отправки.
  await requireSession();

  return (
    <>
      <PageHeader
        title="Новый проект"
        subtitle="Проект — папка для прогонов по одному материалу. Ролик, аудиторию и анкету выбирает визард запуска: они относятся к прогону, а не к проекту."
      />

      <div className="p-8">
        <form action={createProjectAction} className="max-w-xl space-y-5">
          <div className="space-y-2">
            <label htmlFor="name" className="block text-sm font-medium">
              Название
            </label>
            <input
              id="name"
              name="name"
              required
              maxLength={200}
              autoFocus
              placeholder="Например: «Константинополь», первый сезон"
              className="w-full rounded-md border border-hairline bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-muted-foreground/60"
            />
            <p className="text-xs text-slate">
              По названию проект ищут в списке — оно должно отличать его от соседних.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="submit"
              className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
            >
              Создать
            </button>
            <Link
              href="/projects"
              className="rounded-md border border-hairline px-4 py-2 text-sm transition-colors hover:bg-secondary"
            >
              Отмена
            </Link>
          </div>
        </form>
      </div>
    </>
  );
}
