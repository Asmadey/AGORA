import "server-only";

import { permanentRedirect } from "next/navigation";

import { parseRunSlug, runSlug } from "@/lib/run-slug";
import { withTenant } from "@/lib/server/db";
import { getTask, getTaskBySeqNo } from "@/lib/server/tasks";

/**
 * Разрешение адреса прогона: `/runs/0050` и `/runs/<uuid>` ведут в одно место.
 *
 * ─── Почему одна функция на три страницы ──────────────────────────────────
 * Отчёт, прогресс и чат живут в трёх файлах и получают один и тот же параметр.
 * Разрешение, написанное в каждом заново, разошлось бы: одна страница понимала
 * бы номер, другая нет, и владелец получил бы 404 при переходе между вкладками
 * одного и того же прогона.
 *
 * ─── Почему перенаправление постоянное ────────────────────────────────────
 * Ссылки на UUID уже разошлись по переписке. `permanentRedirect` даёт 308:
 * браузер запоминает и в следующий раз идёт сразу на номер, закладка
 * обновляется сама. Временное перенаправление оставило бы старый адрес жить
 * вечно, и оба вида ходили бы по продукту параллельно.
 *
 * ─── Что отдаётся наружу ──────────────────────────────────────────────────
 * ВСЕГДА UUID. Клиентские компоненты зовут `/api/tasks/<id>/…`, и маршруты API
 * работают по идентификатору. Номер живёт только в адресной строке; подменив
 * одно другим, мы получили бы 404 из середины уже открытой страницы.
 */
export interface ResolvedRun {
  /** Идентификатор для запросов и для API. Всегда UUID. */
  id: string;
  /** Человеческий номер или null у прогонов старше миграции 28. */
  seqNo: number | null;
}

/**
 * @param slug       то, что стоит в адресе
 * @param tenantId   арендатор сессии — RLS ограничит выборку им
 * @param canonicalPath хвост адреса для перенаправления: "" | "/progress" | "/chat"
 * @returns null — адрес непригоден или прогон не найден; вызывающий отвечает 404
 */
export async function resolveRun(
  slug: string,
  tenantId: string,
  canonicalPath = "",
): Promise<ResolvedRun | null> {
  const ref = parseRunSlug(slug);
  // Непригодную строку отвергаем ДО обращения к базе: она пришла из адреса, то
  // есть от кого угодно, и «сначала спросим, потом проверим» — лишний повод
  // ошибиться там, где ошибка стоит утечки между арендаторами.
  if (!ref) return null;

  if (ref.kind === "number") {
    const task = await withTenant(tenantId, (client) =>
      getTaskBySeqNo(client, ref.seqNo),
    );
    return task ? { id: task.id, seqNo: task.seqNo } : null;
  }

  const task = await withTenant(tenantId, (client) => getTask(client, ref.id));
  if (!task) return null;

  // Прогон с номером обязан жить по номеру. Перенаправление стоит здесь, а не в
  // middleware: там нет ни сессии, ни доступа к базе, и превратить UUID в номер
  // было бы нечем.
  if (task.seqNo !== null) {
    permanentRedirect(`/runs/${runSlug(task.seqNo)}${canonicalPath}`);
  }

  // Номера нет — прогон старше миграции 28. Живёт по UUID и дальше: выдумывать
  // ему номер значило бы сдвинуть нумерацию остальных.
  return { id: task.id, seqNo: null };
}
