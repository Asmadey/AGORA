import { CONTEXT_LIMIT_CHARS, normalizeContext } from "@/lib/context-file";
import { checkVideoRef } from "@/lib/launch-contract";
import { normalizeTitle } from "@/lib/research-title";
import { DEFAULT_SETTINGS } from "@/lib/settings";
import { withTenant } from "@/lib/server/db";
import { HttpError, requireSession, toResponse } from "@/lib/server/guard";
import { enqueuePipeline } from "@/lib/server/queue";
import { launchTask, listTasks, type LaunchParams } from "@/lib/server/tasks";

/**
 * Запуск исследования (задача #11).
 *
 * POST /api/tasks — создать прогон. Идемпотентен по параметрам вместе с seed.
 * GET  /api/tasks — прогоны арендатора.
 *
 * ─── Почему ответ 200, а не 201, на повторный запуск ───────────────────────
 * Повторный запуск ничего не создал, и код обязан это отражать: 201 на второй
 * вызов означал бы «создано», а создано не было. Флаг created в теле говорит то
 * же самое явно — по нему интерфейс отличает «прогон пошёл» от «прогон уже был».
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface LaunchBody {
  mode?: unknown;
  videoRef?: unknown;
  sourceName?: unknown;
  title?: unknown;
  personaSetId?: unknown;
  surveyId?: unknown;
  projectId?: unknown;
  replicationCount?: unknown;
  seed?: unknown;
  audienceContext?: unknown;
}

const REPLICATION_BOUNDS = { min: 1, max: 10 } as const;

function optionalId(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export async function POST(request: Request) {
  try {
    const { tenantId, userId } = await requireSession();

    let body: LaunchBody;
    try {
      body = (await request.json()) as LaunchBody;
    } catch {
      return Response.json(
        { error: "тело запроса не является корректным JSON" },
        { status: 400 },
      );
    }

    const errors: string[] = [];

    const mode = body.mode === undefined ? "short" : body.mode;
    if (mode !== "short" && mode !== "long") {
      errors.push("mode: ожидается short | long");
    }

    // Контекст персон проверяется ЗДЕСЬ ещё раз, а не только в браузере:
    // маршрут открыт для любого клиента, а текст уедет в промпт каждой персоны
    // и будет оплачен на каждом вызове.
    if (body.audienceContext !== undefined) {
      if (typeof body.audienceContext !== "string") {
        errors.push("audienceContext: строка либо отсутствует");
      } else if (normalizeContext(body.audienceContext).length > CONTEXT_LIMIT_CHARS) {
        errors.push(
          `audienceContext: длиннее ${CONTEXT_LIMIT_CHARS} символов — см. lib/context-file.ts`,
        );
      }
    }
    // Материал проверяется ЗДЕСЬ, а не только в браузере, и проверяется по
    // существу, а не «строка либо отсутствует».
    //
    // Прежняя формулировка пропускала и пустой ключ, и заведомо негодный:
    // задача создавалась, вставала в очередь, воркер её забирал и падал в
    // первом же узле — `ValueError: video_ref пуст` или `FileNotFoundError`.
    // Пользователь видел появившееся исследование, через полминуты ставшее
    // FAILED, и причина лежала в логе воркера, а не в ответе на его запрос.
    //
    // Это то же рассуждение, что двадцатью строками ниже про пустой набор
    // персон: поздний дорогой отказ превращается в немедленный 400 с
    // названной причиной. К материалу его просто не применили.
    const videoRefError = checkVideoRef(body.videoRef, tenantId);
    if (videoRefError) errors.push(videoRefError);
    if (body.sourceName !== undefined && typeof body.sourceName !== "string") {
      errors.push("sourceName: строка либо отсутствует");
    }
    // Название разбирается общей функцией — той же, что и при переименовании.
    // Своя проверка здесь разошлась бы с ней, и создание принимало бы то, что
    // потом нельзя сохранить правкой.
    let title: string | null = null;
    if (body.title !== undefined && body.title !== null) {
      if (typeof body.title !== "string") {
        errors.push("title: строка либо отсутствует");
      } else {
        try {
          title = normalizeTitle(body.title);
        } catch (e) {
          errors.push(`title: ${(e as Error).message}`);
        }
      }
    }

    // seed обязателен: без него идемпотентность бессмысленна — каждый запуск
    // давал бы новый ключ, и защита от двойного клика не работала бы вовсе.
    // Молча подставить случайный seed нельзя: это выглядело бы как рабочая
    // идемпотентность, которая никогда не срабатывает.
    if (
      typeof body.seed !== "number" ||
      !Number.isInteger(body.seed) ||
      body.seed < 0
    ) {
      errors.push("seed: неотрицательное целое (обязательно — от него зависит идемпотентность)");
    }

    if (body.replicationCount !== undefined) {
      const rc = body.replicationCount;
      if (
        typeof rc !== "number" ||
        !Number.isInteger(rc) ||
        rc < REPLICATION_BOUNDS.min ||
        rc > REPLICATION_BOUNDS.max
      ) {
        errors.push(
          `replicationCount: целое ${REPLICATION_BOUNDS.min}–${REPLICATION_BOUNDS.max}`,
        );
      }
    }

    if (errors.length > 0) {
      return Response.json({ error: "некорректные параметры", details: errors }, {
        status: 400,
      });
    }

    const task = await withTenant(tenantId, async (client) => {
      // Дефолт «Перекрытия» — из Настроек арендатора (#27), а не число в коде.
      // Читается ЗДЕСЬ, в момент запуска, и дальше едет в задачу снимком: пока
      // прогон стоит в очереди, команда может сменить настройку, и тогда часть
      // персон прошла бы анкету один раз, часть — три.
      let replicationCount = body.replicationCount as number | undefined;
      if (replicationCount === undefined) {
        const { rows } = await client.query<{ default_replication_count: number }>(
          "SELECT default_replication_count FROM settings WHERE tenant_id = $1",
          [tenantId],
        );
        replicationCount =
          rows[0]?.default_replication_count ?? DEFAULT_SETTINGS.defaultReplication;
      }

      const params: LaunchParams = {
        mode: mode as "short" | "long",
        videoRef: optionalId(body.videoRef),
        sourceName: typeof body.sourceName === "string" ? body.sourceName.slice(0, 300) : null,
        title,
        audienceContext:
          typeof body.audienceContext === "string"
            ? normalizeContext(body.audienceContext)
            : null,
        personaSetId: optionalId(body.personaSetId),
        surveyId: optionalId(body.surveyId),
        projectId: optionalId(body.projectId),
        replicationCount,
        seed: body.seed as number,
      };

      // Персоны набора читаются ДО создания задачи, внутри тенант-контекста:
      // воркер получает готовый список идентификаторов и не ходит за ним сам.
      const personaIds = params.personaSetId
        ? (
            await client.query<{ id: string }>(
              "SELECT id::text FROM personas WHERE persona_set_id = $1::uuid",
              [params.personaSetId],
            )
          ).rows.map((r) => r.id)
        : [];

      // Пустой набор — отказ здесь, а не через шесть минут.
      //
      // Прогон с нулём персон обречён: конвейер скачает ролик, нормализует
      // его, расшифрует речь, разберёт кадры моделью со зрением — и упадёт на
      // узле опроса с «персоны не загружены». Всё оплаченное к этому моменту
      // потрачено, а причина выглядит сбоем воркера, хотя известна была до
      // старта. Именно так и вышло на первом сквозном прогоне: набор создали
      // маршрутом /api/persona-sets, который заводит запись, но не генерирует
      // персон, и отказ приехал на 363-й секунде.
      //
      // Проверка стоит один COUNT и превращает поздний дорогой отказ в
      // немедленный 400 с названной причиной.
      if (params.personaSetId && personaIds.length === 0) {
        throw new HttpError(
          400,
          "в выбранном наборе нет ни одной персоны: прогон дошёл бы до опроса " +
            "и упал там, уже потратив расшифровку и разбор кадров. Соберите " +
            "аудиторию заново — набор создаётся маршрутом POST /api/audience, " +
            "а POST /api/persona-sets только заводит запись о нём",
        );
      }

      const launched = await launchTask(client, params, userId ?? null);

      const survey = params.surveyId
        ? (
            await client.query<{ questions: unknown }>(
              "SELECT questions FROM surveys WHERE id = $1::uuid",
              [params.surveyId],
            )
          ).rows[0]?.questions ?? null
        : null;

      return { launched, personaIds, survey };
    });

    // Постановка в очередь — только для действительно созданного прогона.
    // Повторный запуск ничего не создал, и слать вторую задачу воркеру значило
    // бы обойти идемпотентность там, где она и заводилась: прогон платный.
    let queued = false;
    let queueError: string | null = null;
    if (task.launched.created) {
      try {
        await enqueuePipeline({
          task_id: task.launched.id,
          tenant_id: tenantId,
          mode: task.launched.mode as "short" | "long",
          video_ref: task.launched.videoRef,
          persona_ids: task.personaIds,
          survey: task.survey,
          replication_count: task.launched.replicationCount,
          prompts_snapshot: task.launched.promptsSnapshot,
          // Кап вызовов VLM: до этого он оставался в интерфейсе и до воркера
          // не доезжал вовсе — то есть жёсткий потолок не действовал никогда.
          settings_snapshot: task.launched.settingsSnapshot,
        });
        queued = true;
      } catch (e) {
        // Прогон создан, но воркер о нём не знает. Молчать нельзя: экран
        // прогресса показывал бы QUEUED вечно, и это выглядело бы как медленная
        // система, а не как недоехавшая задача.
        queueError = e instanceof Error ? e.message : "очередь недоступна";
      }
    }

    return Response.json(
      { ...task.launched, queued, queueError },
      { status: task.launched.created ? 201 : 200 },
    );
  } catch (error) {
    return toResponse(error);
  }
}

export async function GET() {
  try {
    const { tenantId } = await requireSession();
    const tasks = await withTenant(tenantId, (client) => listTasks(client));
    return Response.json({ tasks });
  } catch (error) {
    return toResponse(error);
  }
}
