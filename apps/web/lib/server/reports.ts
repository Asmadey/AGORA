import "server-only";

import { collection, type SessionUser } from "./mongo";

/**
 * Чтение отчёта прогона (задача #21).
 *
 * Отчёт кладёт воркер (`agent_core/analytics/store.py`) в две коллекции, и
 * разделение здесь не архитектурная аккуратность, а замер:
 *
 *     100 персон × 1 повтор:  агрегат   1.2 КБ | с карточками персон  132 КБ
 *     500 персон × 1 повтор:  агрегат   1.2 КБ | с карточками персон  654 КБ
 *     500 персон × 3 повтора: агрегат 178.5 КБ | с карточками персон  2.1 МБ
 *
 * Первый экран показывает пять чисел в шапке и нарратив; тянуть ради них два
 * мегабайта карточек незачем. Поэтому `loadReport` читает отчёт целиком, а
 * `loadReportPersonas` отдаёт карточки страницами — их разворачивает аккордеон.
 *
 * ─── Изоляция ──────────────────────────────────────────────────────────────
 * tenant_id берётся из сессии и никогда не приходит аргументом: в MongoDB нет
 * RLS, и подставить чужой идентификатор смог бы вызывающий. Это то же правило,
 * что в `mongo.ts` для черновиков визарда, и нарушение любой его половины
 * означает чужие данные.
 */

/** Имена коллекций дублируют константы воркера (analytics/store.py). */
const REPORTS = "reports";
const REPORT_PERSONAS = "report_personas";

/**
 * Потолок страницы карточек.
 *
 * Не «сколько влезет», а сколько имеет смысл рисовать: аккордеон на 500
 * закрытых строк — это 500 узлов DOM, которые никто не раскроет. Запрос с
 * бо́льшим limit не отвергается, а урезается: отвергнуть значило бы сломать
 * вызывающего, который просто просил «всё».
 */
export const PERSONA_PAGE_MAX = 200;

export interface ReportEnvelope {
  taskId: string;
  audienceSize: number;
  updatedAt: string | null;
  report: Record<string, unknown>;
}

export interface PersonaCard {
  personaId: string;
  personaName: string | null;
  replication: number;
  answer: Record<string, unknown>;
  qaFlags: Record<string, unknown>[];
}

/** Отчёт прогона либо null, если его ещё нет. tenant_id — из сессии. */
export async function loadReport(
  session: SessionUser,
  taskId: string,
): Promise<ReportEnvelope | null> {
  const coll = await collection(REPORTS);
  const doc = await coll.findOne(
    { tenant_id: session.tenantId, task_id: taskId },
    { projection: { _id: 0, tenant_id: 0 } },
  );
  if (!doc) return null;

  return {
    taskId,
    audienceSize: typeof doc.audience_size === "number" ? doc.audience_size : 0,
    updatedAt: doc.updated_at instanceof Date ? doc.updated_at.toISOString() : null,
    report: (doc.report ?? {}) as Record<string, unknown>,
  };
}

/**
 * Карточки персон страницей. Порядок устойчивый — иначе пагинация повторяет
 * и пропускает записи: без сортировки Mongo не обещает один и тот же порядок
 * между двумя запросами, и на второй странице появились бы те же персоны.
 */
export async function loadReportPersonas(
  session: SessionUser,
  taskId: string,
  options: { limit?: number; skip?: number } = {},
): Promise<{ items: PersonaCard[]; total: number }> {
  const limit = Math.min(Math.max(options.limit ?? 50, 1), PERSONA_PAGE_MAX);
  const skip = Math.max(options.skip ?? 0, 0);

  const coll = await collection(REPORT_PERSONAS);
  const filter = { tenant_id: session.tenantId, task_id: taskId };

  const total = await coll.countDocuments(filter);
  const docs = await coll
    .find(filter, { projection: { _id: 0, tenant_id: 0, task_id: 0 } })
    .sort({ persona_id: 1, replication: 1 })
    .skip(skip)
    .limit(limit)
    .toArray();

  return {
    total,
    items: docs.map((d) => ({
      personaId: String(d.persona_id ?? ""),
      personaName: typeof d.persona_name === "string" ? d.persona_name : null,
      replication: typeof d.replication === "number" ? d.replication : 0,
      answer: (d.answer ?? {}) as Record<string, unknown>,
      qaFlags: Array.isArray(d.qa_flags) ? (d.qa_flags as Record<string, unknown>[]) : [],
    })),
  };
}
