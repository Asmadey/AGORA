import { parseAudienceChoice, toGenerationConfig } from "@/lib/audience";
import { audienceGrounding, warningsFor } from "@/lib/audience-grounding";
import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import { listPersonaSets, listPersonas } from "@/lib/server/personas";

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

interface GenerationResult {
  personas: unknown[];
}

export async function POST(request: Request) {
  try {
    const { tenantId } = await requireSession();

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
    const config = toGenerationConfig(criteria, seed);

    const { execFile } = await import("node:child_process");
    const { promisify } = await import("node:util");
    const execFileAsync = promisify(execFile);

    // AGORA_REPO_ROOT обязателен: у standalone-сервера Next process.cwd() равен
    // /app/apps/web, а не корню монорепо. Тот же дефект уже ловили в #24.
    const repoRoot = process.env.AGORA_REPO_ROOT || `${process.cwd()}/../..`;
    const core = `${repoRoot}/services/agent-core`;

    let result: GenerationResult;
    try {
      const { stdout } = await execFileAsync(
        "python3",
        ["-m", "agent_core.persona.generate_cli", "--config", JSON.stringify(config)],
        {
          cwd: core,
          timeout: 120_000,
          maxBuffer: 32 * 1024 * 1024,
          env: { ...process.env, PYTHONPATH: core },
        },
      );
      result = JSON.parse(stdout) as GenerationResult;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      // Отказ по невозможным критериям — 400, а не 500: виноват выбор
      // пользователя, и ему надо показать, какой именно критерий пуст.
      const criteriaError = /отсутствуют в корпусе/.test(msg);
      return Response.json(
        { error: `генерация не удалась: ${msg.slice(-300)}`, warnings },
        { status: criteriaError ? 400 : 500 },
      );
    }

    return Response.json({
      generated: true,
      personaSetId: null,
      size: result.personas.length,
      personas: result.personas,
      config,
      warnings,
    });
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
