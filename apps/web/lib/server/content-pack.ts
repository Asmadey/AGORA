import "server-only";

import { collection, type SessionUser } from "./mongo";
import { createPresignedGetUrl } from "./s3";

/**
 * Чтение пакета материала прогона — таймлайн экрана исследования.
 *
 * ─── Почему это отдельно от отчёта ─────────────────────────────────────────
 * Отчёт читают при каждой загрузке экрана; пакет — только когда открывают
 * таймлайн, и на пятнадцатиминутном ролике он в разы больше самого отчёта. Та
 * же причина, по которой карточки персон живут отдельной коллекцией.
 *
 * ─── Изоляция ──────────────────────────────────────────────────────────────
 * tenant_id берётся из сессии и никогда не приходит аргументом: в MongoDB нет
 * RLS, и подставить чужой идентификатор смог бы вызывающий.
 */

/** Имя коллекции дублирует константу воркера (analytics/store.py). */
const CONTENT_PACKS = "content_packs";

export interface TimelineCell {
  start: number;
  end: number;
  /** Описание сцены от VLM. null — реплики до первой сцены. */
  scene: string | null;
  mood: string | null;
  /** Граница пришла от монтажной склейки, а не от нарезки длинной сцены. */
  isCut: boolean;
  /**
   * Подписанная ссылка на кадр сцены. null — прогон начат до того, как кадры
   * стали переживать контейнер, либо выгрузка не удалась.
   */
  screenshot: string | null;
  lines: { start: number; end: number; text: string; speaker: string | null }[];
}

export interface TimelineView {
  durationSec: number;
  stitched: boolean;
  cells: TimelineCell[];
  stats: {
    scenesTotal: number;
    speakers: number;
    words: number;
    linesTotal: number;
  };
}

function num(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

/**
 * Таймлайн прогона либо null, если пакет не сохранён.
 *
 * null — законное состояние, а не ошибка: так выглядят прогоны, начатые до
 * того, как пакет стал сохраняться, и прогоны, у которых Mongo была
 * недоступна в момент записи (причина тогда лежит в `degraded` отчёта).
 *
 * Ссылки на кадры подписываются здесь, а не хранятся в базе: подпись живёт
 * час, и записанная ссылка протухла бы к первому же открытию экрана.
 */
export async function loadTimeline(
  session: SessionUser,
  taskId: string,
): Promise<TimelineView | null> {
  const coll = await collection(CONTENT_PACKS);
  const doc = await coll.findOne(
    { tenant_id: session.tenantId, task_id: taskId },
    { projection: { _id: 0, tenant_id: 0 } },
  );
  const pack = doc?.pack as Record<string, unknown> | undefined;
  if (!pack) return null;

  const rawTimeline = Array.isArray(pack.timeline) ? pack.timeline : [];
  const stats = (pack.stats ?? {}) as Record<string, unknown>;

  const cells: TimelineCell[] = rawTimeline.map((raw) => {
    const cell = (raw ?? {}) as Record<string, unknown>;
    const key = str(cell.screenshot);
    const rawLines = Array.isArray(cell.lines) ? cell.lines : [];
    return {
      start: num(cell.start),
      end: num(cell.end),
      scene: str(cell.scene),
      mood: str(cell.mood),
      isCut: cell.is_cut !== false,
      // Подпись может не получиться, если S3 не настроен: таймлайн без картинок
      // полезнее отсутствующего таймлайна.
      screenshot: key ? safePresign(key) : null,
      lines: rawLines.map((rawLine) => {
        const line = (rawLine ?? {}) as Record<string, unknown>;
        return {
          start: num(line.start),
          end: num(line.end),
          text: String(line.text ?? ""),
          speaker: str(line.speaker),
        };
      }),
    };
  });

  return {
    durationSec: num(pack.duration_sec),
    stitched: pack.stitched === true,
    cells,
    stats: {
      scenesTotal: num(stats.scenes_total),
      speakers: num(stats.speakers),
      words: num(stats.words),
      linesTotal: num(stats.lines_total),
    },
  };
}

export function safePresign(key: string): string | null {
  try {
    return createPresignedGetUrl(key);
  } catch {
    return null;
  }
}
