import { parseAudienceChoice, toGenerationConfig } from "@/lib/audience";
import { audienceGrounding, warningsFor } from "@/lib/audience-grounding";
import { createSnapshot, listDatasets } from "@/lib/server/corpus-db";
import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import {
  createPersonaSet,
  listPersonaSets,
  listPersonas,
} from "@/lib/server/personas";
import { enqueueAudience } from "@/lib/server/queue";
import { buildSettingsSnapshot } from "@/lib/server/tasks";

/**
 * Шаг «Аудитория» визарда (задача #9).
 *
 * POST /api/audience — либо генерация по критериям, либо переиспользование
 *                      существующего набора персон.
 * GET  /api/audience — охват критериев корпусом, чтобы шаг показал пометки
 *                      заземления до того, как пользователь нажмёт «Запустить».
 *
 * ─── Что здесь изменилось и почему ─────────────────────────────────────────
 * Прежняя версия маршрута звала generateAudience() из lib/ai-server, то есть
 * шла в LLM напрямую, минуя заземлённый генератор из корпуса. Для продукта,
 * который продаётся фразой «прогноз, а не догадка», это подмена сути: персоны
 * получались правдоподобными и ни на чём не основанными, а persona_grounding о
 * них ничего не знала — метрика считается по другому пути.
 *
 * Заодно у маршрута не было ни аутентификации, ни тенант-контекста: любой
 * запрос порождал вызовы модели за счёт владельца стенда.
 *
 * ─── Два исхода, а не один с флагом ────────────────────────────────────────
 * Пункт cdd «выбор существующего persona_set пропускает генерацию» виден в
 * ответе полем generated. Оно не декоративное: переиспользование набора —
 * главная экономия при перезапуске исследования (#30), и по ответу должно быть
 * видно, платили мы за генерацию или нет.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Тип ответа подпроцесса генерации (GenerationResult) убран вместе с самим
// подпроцессом: маршрут больше не ждёт персон, он ставит задачу в очередь.
// Оставленный тип описывал бы контракт, которого нет, — и первый же читатель
// решил бы, что маршрут по-прежнему возвращает персоны.

export async function POST(request: Request) {
  try {
    const { tenantId, userId } = await requireSession();

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json(
        { error: "тело запроса не является корректным JSON" },
        { status: 400 },
      );
    }

    const parsed = parseAudienceChoice(body);
    if (!parsed.ok) {
      return Response.json(
        { error: "некорректные критерии", details: parsed.errors },
        { status: 400 },
      );
    }

    // ── Существующий набор: генерации нет ──────────────────────────────────
    if (parsed.value.kind === "reuse") {
      const { personaSetId } = parsed.value;

      const found = await withTenant(tenantId, async (client) => {
        const sets = await listPersonaSets(client, personaSetId);
        if (sets.length === 0) return null;
        return { personas: await listPersonas(client, personaSetId) };
      });

      // 404, а не 403: существование чужого набора не подтверждается — тот же
      // приём, что в #6, неотличимо от несуществующего.
      if (!found) {
        return Response.json({ error: "набор персон не найден" }, { status: 404 });
      }

      return Response.json({
        generated: false,
        personaSetId,
        size: found.personas.length,
        personas: found.personas,
        warnings: [],
      });
    }

    // ── Генерация по критериям ─────────────────────────────────────────────
    const { criteria } = parsed.value;

    // Предупреждения считаются ДО генерации и отдаются вместе с результатом:
    // сообщать, что сегмент не заземлён, после запуска — поздно.
    const warnings = warningsFor({
      ageGroups: criteria.ageGroups,
      geos: criteria.geos,
      genders: criteria.genders,
      education: criteria.education,
    });

    const rawSeed = (body as { seed?: unknown }).seed;
    const seed = typeof rawSeed === "number" && Number.isInteger(rawSeed) && rawSeed >= 0
      ? rawSeed
      : 42;
    // use_llm — обогащение narrative моделью поверх заземлённого скелета.
    // Включено по умолчанию: продукт обещает живые портреты, а не строки
    // таблицы. Выключается телом запроса — это нужно эталонному прогону
    // persona_grounding, которому важна воспроизводимость, а не читаемость.
    const useLlm = (body as { useLlm?: unknown }).useLlm !== false;
    const config = { ...toGenerationConfig(criteria, seed), use_llm: useLlm };

    // ── Набор создаётся СРАЗУ, наполняется в фоне ──────────────────────────
    //
    // Раньше здесь запускался подпроцесс `generate_cli` и маршрут ждал его с
    // таймаутом 120 секунд. Обогащение — последовательный цикл с таймаутом 60
    // секунд на персону: шестьдесят персон в такой бюджет не помещаются никак.
    // Пользователь видел спиннер, превращавшийся в ошибку, а всё написанное к
    // этому моменту выбрасывалось.
    //
    // Вторая причина переезда в воркер: в образе веба нет `openai`. Обогащение
    // отсюда всегда падало на ModuleNotFoundError и честно сообщало
    // `enriched: false` — то есть самая дорогая часть генерации не работала
    // вовсе, а выглядело это как привычная «деградация».
    //
    // Теперь строка набора появляется в списке немедленно, со статусом
    // `generating` и счётчиком «сделано из заказанного».
    // ── Слепок корпуса снимается ЗДЕСЬ ─────────────────────────────────────
    //
    // Корпус читается ровно один раз — когда генератор сэмплирует персон по его
    // долям. Слепок в момент запуска исследования опоздал бы: персоны к тому
    // времени собраны, и слепок описывал бы корпус, по которому их не собирали.
    //
    // Датасет выбирается на шаге «Аудитория». Если не выбран — берётся
    // единственный; если их несколько, выбор обязателен: молча взять первый
    // значило бы заземлить аудиторию на выборку, которой не просили.
    const requestedDataset = (body as { datasetId?: unknown }).datasetId;
    let snapshotId: string | null = null;
    let snapshotError: string | null = null;

    try {
      snapshotId = await withTenant(tenantId, async (client) => {
        const datasets = await listDatasets(client);
        if (datasets.length === 0) return null;

        const chosen =
          typeof requestedDataset === "string"
            ? datasets.find((d) => d.id === requestedDataset)
            : datasets.length === 1
              ? datasets[0]
              : undefined;

        if (!chosen) {
          throw new Error(
            typeof requestedDataset === "string"
              ? "датасет не найден"
              : `датасетов ${datasets.length}: выберите, на каком заземлять аудиторию`,
          );
        }
        const snapshot = await createSnapshot(client, chosen.id);
        return snapshot.id;
      });
    } catch (e) {
      snapshotError = (e as Error).message;
    }

    if (snapshotError) {
      return Response.json({ error: snapshotError, warnings }, { status: 400 });
    }

    const set = await withTenant(tenantId, (client) =>
      createPersonaSet(
        client,
        ((body as { name?: unknown }).name as string) ||
          `Аудитория от ${new Date().toLocaleDateString("ru-RU")}`,
        criteria.size,
        config,
        seed,
        "generating",
        snapshotId,
        userId,
      ),
    );

    // Настройки пиннятся на задание генерации так же, как на прогон: пока
    // набор считается, команда может сменить температуру создания персон, и
    // тогда часть аудитории получилась бы под одним разбросом формулировок, а
    // часть под другим — внутри одного набора, который потом сравнивают как
    // целое.
    const settings = await withTenant(tenantId, (client) =>
      buildSettingsSnapshot(client),
    );

    try {
      await enqueueAudience({
        persona_set_id: set.id,
        tenant_id: tenantId,
        config: config as Record<string, unknown>,
        // По слепку воркер сэмплирует персон. null — корпуса в базе нет, и
        // генератор берёт файл образа: прежнее поведение, честно названное.
        corpus_snapshot_id: snapshotId,
        settings_snapshot: settings,
      });
    } catch (e) {
      // Набор создан, но воркер о нём не знает. Молчать нельзя: строка висела
      // бы в «generating» вечно, и это выглядело бы как медленная генерация,
      // а не как недоехавшая задача.
      await withTenant(tenantId, (client) =>
        client.query(
          "UPDATE persona_sets SET status='failed', error=$2, finished_at=now() WHERE id=$1",
          [set.id, `очередь недоступна: ${(e as Error).message}`],
        ),
      );
      return Response.json(
        { error: `не удалось поставить генерацию в очередь: ${(e as Error).message}`, warnings },
        { status: 503 },
      );
    }

    // 202: набор заведён, персон в нём ещё нет. Отвечать 200 значило бы
    // сказать «готово» про то, что только началось.
    return Response.json(
      {
        generated: true,
        personaSetId: set.id,
        status: "generating",
        size: criteria.size,
        generatedCount: 0,
        warnings,
      },
      { status: 202 },
    );
  } catch (error) {
    return toResponse(error);
  }
}

export async function GET() {
  try {
    await requireSession();
    return Response.json(audienceGrounding());
  } catch (error) {
    return toResponse(error);
  }
}
