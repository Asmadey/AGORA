import { parseAudienceChoice, toGenerationConfig } from "@/lib/audience";
import { audienceGrounding, warningsFor } from "@/lib/audience-grounding";
import { withTenant } from "@/lib/server/db";
import { requireSession, toResponse } from "@/lib/server/guard";
import {
  createPersonaSet,
  insertPersonas,
  listPersonaSets,
  listPersonas,
} from "@/lib/server/personas";

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
  personas: Record<string, unknown>[];
  /** Имена персон отдельным списком: DNA описана закрытой схемой (#4). */
  names?: string[];
  /** Для каждой персоны: "model" или "template". */
  sources?: string[];
  meta?: {
    enriched: boolean;
    llm_calls: number;
    cache_hits: number;
    degraded_reason?: string | null;
  };
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
    // use_llm — обогащение narrative моделью поверх заземлённого скелета.
    // Включено по умолчанию: продукт обещает живые портреты, а не строки
    // таблицы. Выключается телом запроса — это нужно эталонному прогону
    // persona_grounding, которому важна воспроизводимость, а не читаемость.
    const useLlm = (body as { useLlm?: unknown }).useLlm !== false;
    const config = { ...toGenerationConfig(criteria, seed), use_llm: useLlm };

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

    // ── Сохранение набора ──────────────────────────────────────────────────
    // Без него результат генерации существует только в теле ответа: запуск
    // (#11) принимает personaSetId, и передать ему было бы нечего. Раньше здесь
    // возвращался personaSetId: null — то есть ветка «создать аудиторию»
    // обрывалась ровно на этом месте, и заметить это по зелёному CDD #9 было
    // невозможно: тот прогоняет генератор напрямую, минуя маршрут.
    const names = result.names ?? [];
    const saved = await withTenant(tenantId, async (client) => {
      const set = await createPersonaSet(
        client,
        (body as { name?: unknown }).name as string ||
          `Аудитория от ${new Date().toLocaleDateString("ru-RU")}`,
        result.personas.length,
        config,
        seed,
      );
      const inserted = await insertPersonas(
        client,
        set.id,
        result.personas.map((dna, i) => ({
          // Имя приходит списком рядом с DNA. Запасной вариант нужен не для
          // красоты: колонка NOT NULL, и персона без имени обрушила бы вставку
          // целиком, потеряв весь набор из-за одного пропуска.
          name: names[i] || `Персона ${i + 1}`,
          dna,
          narrative: (dna.narrative as string) ?? null,
          seed: (dna.seed as number) ?? seed,
        })),
      );
      return { set, inserted };
    });

    return Response.json({
      generated: true,
      personaSetId: saved.set.id,
      size: saved.inserted,
      personas: result.personas,
      config,
      warnings,
      // Видно, поработала ли модель. Без этого «живой портрет» и «шаблон из
      // полей» различимы только на глаз, а причина деградации не видна вовсе.
      enrichment: result.meta ?? { enriched: false, llm_calls: 0, cache_hits: 0 },
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
