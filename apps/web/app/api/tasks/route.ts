import { DEFAULT_SETTINGS } from "@/lib/settings";
import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
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
  personaSetId?: unknown;
  surveyId?: unknown;
  projectId?: unknown;
  replicationCount?: unknown;
  seed?: unknown;
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

    if (body.videoRef !== undefined && typeof body.videoRef !== "string") {
      errors.push("videoRef: строка либо отсутствует");
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
        personaSetId: optionalId(body.personaSetId),
        surveyId: optionalId(body.surveyId),
        projectId: optionalId(body.projectId),
        replicationCount,
        seed: body.seed as number,
      };

      const launched = await launchTask(client, params, userId ?? null);

      // Персоны набора читаются здесь же, внутри тенант-контекста: воркер
      // получает готовый список идентификаторов и не ходит за ним отдельно.
      const personaIds = params.personaSetId
        ? (
            await client.query<{ id: string }>(
              "SELECT id::text FROM personas WHERE persona_set_id = $1::uuid",
              [params.personaSetId],
            )
          ).rows.map((r) => r.id)
        : [];

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
