import { loadTimeline } from "@/lib/server/content-pack";
import { requireSession, toResponse } from "@/lib/server/guard";

/**
 * Транскрипт прогона текстом (п. 36).
 *
 * ─── Зачем отдельный маршрут ───────────────────────────────────────────────
 * Расшифровка — самый дорогой артефакт прогона и единственный, которым
 * пользуются вне продукта: её вставляют в презентацию, шлют монтажёру, ищут по
 * ней цитату. Пока её нельзя было забрать, каждый такой случай означал
 * переписывание с экрана.
 *
 * ─── Почему из пакета, а не из отдельного хранилища ────────────────────────
 * Ровно те реплики, которые видела персона, и ровно с теми таймкодами, по
 * которым её проверял судья. Отдельная копия расшифровки разошлась бы с пакетом
 * при первой же правке сборки — и расхождение было бы невидимым, потому что оба
 * текста выглядят правильными.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Секунды → M:SS. Тот же формат, что в пакете и в отчёте. */
function timecode(sec: number): string {
  const total = Math.max(0, Math.floor(sec));
  const s = String(total % 60).padStart(2, "0");
  const m = Math.floor(total / 60) % 60;
  const h = Math.floor(total / 3600);
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const session = await requireSession();

    const timeline = await loadTimeline(session, id);
    if (!timeline) {
      return Response.json({ error: "расшифровка не найдена" }, { status: 404 });
    }

    const lines: string[] = [];
    for (const cell of timeline.cells) {
      for (const line of cell.lines) {
        const who = line.speaker ? `${line.speaker}: ` : "";
        lines.push(`[${timecode(line.start)}] ${who}${line.text}`);
      }
    }

    // Пустая расшифровка — законный исход: ролик без речи. Отдаём пустой файл с
    // пояснением, а не 404: 404 отправил бы искать причину в правах и ссылке.
    const body = lines.length
      ? lines.join("\n") + "\n"
      : "В материале не распознано ни одной реплики.\n";

    return new Response(body, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Disposition": `attachment; filename="transcript-${id}.txt"`,
      },
    });
  } catch (error) {
    return toResponse(error);
  }
}
