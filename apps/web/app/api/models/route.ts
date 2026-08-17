import { requireSession, toResponse } from "@/lib/server/guard";

/**
 * Модели провайдера — живым списком, а не зашитым перечнем.
 *
 * ─── Почему не константа в коде ────────────────────────────────────────────
 * Зашитый список устаревает молча. Ровно так вышло с моделями транскрипции:
 * интерфейс годами предлагал `large-v3` и `large-v3-turbo`, а в образе воркера
 * лежала одна, и выбор второй уводил прогон качать веса посреди работы.
 * Провайдер отдаёт `/v1/models` — сейчас 97 штук, — и спрашивать надо его.
 *
 * ─── Зачем деление на зрение и текст ───────────────────────────────────────
 * Разбор кадра идёт в модель ЗРЕНИЯ, и текстовая картинку не примет. Один
 * общий список сломал бы разбор кадров молча: прогон дошёл бы до него после
 * расшифровки и упал на каждой панели. Провайдер про модальность не сообщает,
 * поэтому зрение опознаётся по имени — правило грубое, зато видимое, и рядом с
 * ним стоит оговорка для читателя интерфейса.
 *
 * ─── Ключ ──────────────────────────────────────────────────────────────────
 * Наружу не выходит ни в каком виде: маршрут ходит к провайдеру сам и отдаёт
 * только имена. Маска ключа собирается здесь же — по ней видно, какой ключ
 * действует, и по ней нельзя его восстановить.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Признаки vision-модели в имени.
 *
 * `vl` — семейство Qwen-VL, `-v` на конце — GLM-4.6v, `gpt-5` мультимодальны
 * целиком. Список заведомо неполон, и это названо в ответе полем `guessed`:
 * читатель должен знать, что деление сделано по имени, а не по паспорту модели.
 */
const VISION_HINTS = [/-vl-/i, /vl-/i, /-v$/i, /^openai\/gpt-5/i, /vision/i];

/** Модели, которые не годятся ни одной нашей роли: эмбеддинги и реранкеры. */
const NOT_CHAT = [/embedding/i, /reranker/i, /whisper/i, /^BAAI\//i];

function maskKey(key: string): string {
  if (!key) return "не задан";
  if (key.length <= 10) return "задан";
  return `${key.slice(0, 4)}…${key.slice(-4)}`;
}

export async function GET() {
  try {
    await requireSession();

    const baseUrl = process.env.OPENAI_BASE_URL ?? "";
    const apiKey = process.env.OPENAI_API_KEY ?? "";
    const current = {
      endpoint: baseUrl,
      keyMask: maskKey(apiKey),
      text: process.env.AI_MODEL ?? "",
      // VLM_MODEL передаётся только воркеру: разбор кадров живёт там. Пустая
      // строка здесь означает «спросите у воркера», а не «модели зрения нет».
      vision: process.env.VLM_MODEL ?? "",
    };

    if (!baseUrl || !apiKey) {
      return Response.json({
        current,
        models: [],
        error: "провайдер не настроен в окружении сервера",
      });
    }

    let ids: string[] = [];
    let error: string | null = null;
    try {
      const res = await fetch(`${baseUrl.replace(/\/+$/, "")}/models`, {
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "x-proxy-source": process.env.MODEL_PROXY_SOURCE ?? "agora",
        },
        signal: AbortSignal.timeout(15_000),
      });
      if (!res.ok) {
        error = `провайдер ответил ${res.status}`;
      } else {
        const payload = (await res.json()) as { data?: { id?: unknown }[] };
        ids = (payload.data ?? [])
          .map((m) => (typeof m.id === "string" ? m.id : ""))
          .filter(Boolean)
          .filter((id) => !NOT_CHAT.some((re) => re.test(id)))
          .sort((a, b) => a.localeCompare(b));
      }
    } catch (e) {
      // Недоступность провайдера не должна ронять экран настроек: остальные
      // поля там работают, а список — единственное, что зависит от сети.
      error = (e as Error).message;
    }

    return Response.json({
      current,
      models: ids.map((id) => ({
        id,
        vision: VISION_HINTS.some((re) => re.test(id)),
      })),
      // Честно: модальность угадана по имени, провайдер её не сообщает.
      guessed: true,
      error,
    });
  } catch (error) {
    return toResponse(error);
  }
}
