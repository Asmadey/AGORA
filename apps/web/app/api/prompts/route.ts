import { withTenant } from "@/lib/server/db";
import { requireOwner, requireSession, toResponse } from "@/lib/server/guard";
import { checkTemplateContract, describeViolation } from "@/lib/prompt-contract";
import { listActivePromptsByStage, extractPlaceholderNames, type PromptVersion } from "@/lib/server/prompts";

/**
 * API промпт-студии (задача #26) — список и создание версии.
 *
 * GET /api/prompts — список активных промптов по стадиям. Доступен любому
 *   участнику: видеть, какие промпты используются, не привилегия.
 * PUT /api/prompts — создать новую версию промпта. Только owner: правка
 *   промпта меняет то, что уходит в модель, и владелец отвечает за это.
 *   version = max + 1, активной становится новая версия. Прошлые версии
 *   сохраняются — воспроизводимость прогонов пиннуется на снимок.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  try {
    const { tenantId } = await requireSession();

    const byStage = await withTenant(tenantId, async (client) => {
      return listActivePromptsByStage(client);
    });

    return Response.json({ stages: byStage });
  } catch (error) {
    return toResponse(error);
  }
}

interface PutBody {
  key: string;
  template: string;
  modelParams?: Record<string, unknown>;
}

export async function PUT(request: Request) {
  try {
    const { tenantId } = await requireOwner();

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "тело запроса не является корректным JSON" }, { status: 400 });
    }

    const raw = body as PutBody;
    if (!raw || typeof raw.key !== "string" || typeof raw.template !== "string") {
      return Response.json(
        { error: "требуются поля key (string) и template (string)" },
        { status: 400 },
      );
    }

    // Переменные извлекаем из шаблона — они единственный источник правды.
    const variables = extractPlaceholderNames(raw.template);
    const modelParams = raw.modelParams ?? {};

    const result = await withTenant(tenantId, async (client) => {
      // ─── Сверка с контрактом стадии ───────────────────────────────────────
      //
      // Раньше здесь звался `validateVariables(template, variables)`, где
      // `variables` извлекались из этого же шаблона. Такая проверка не может
      // не пройти, и именно поэтому сюда доехало переопределение
      // `analytics.report` длиной в шестнадцать символов: `test {{content}}`.
      // Отчёты после него собирались с пустым нарративом и не жаловались.
      //
      // Сверять надо с ДЕФОЛТОМ того же ключа: его переменные — это ровно то,
      // что стадия подставляет. См. lib/prompt-contract.ts.
      const { rows: defaults } = await client.query<{ template: string }>(
        `SELECT template FROM prompts
          WHERE key = $1 AND tenant_id IS NULL AND is_active = true
          LIMIT 1`,
        [raw.key],
      );
      const violation = checkTemplateContract(raw.template, defaults[0]?.template);
      if (violation) {
        return { violation } as const;
      }

      // version = max + 1 среди версий арендатора + дефолта.
      // Берём max по всем версиям этого ключа (включая дефолт), чтобы
      // гарантировать монотонный рост даже после restore default.
      const { rows: versionRows } = await client.query<{ max_ver: number | null }>(
        `SELECT COALESCE(max(version), 0) AS max_ver FROM prompts WHERE key = $1`,
        [raw.key],
      );
      const nextVersion = (versionRows[0]?.max_ver ?? 0) + 1;

      // Деактивируем все текущие активные версии арендатора для этого ключа.
      // Дефолт (tenant_id IS NULL) трогать нельзя — политика не даст, да и
      // незачем: дефолт остаётся как fallback.
      await client.query(
        `UPDATE prompts SET is_active = false
         WHERE key = $1 AND tenant_id = $2 AND is_active = true`,
        [raw.key, tenantId],
      );

      // Вставляем новую версию, она становится активной.
      const { rows } = await client.query<PromptVersion>(
        `INSERT INTO prompts (tenant_id, key, stage, template, variables, model_params, version, is_active, is_default)
         VALUES ($1, $2,
                 (SELECT stage FROM prompts WHERE key = $2 ORDER BY tenant_id NULLS LAST LIMIT 1),
                 $3, $4::jsonb, $5::jsonb, $6, true, false)
         RETURNING id, tenant_id, key, stage, template, variables, model_params, version, is_active, is_default, created_at::text as created_at`,
        [tenantId, raw.key, raw.template, JSON.stringify(variables), JSON.stringify(modelParams), nextVersion],
      );

      return { prompt: rows[0] } as const;
    });

    if ("violation" in result && result.violation) {
      const { missing, unknown } = result.violation;
      return Response.json(
        { error: describeViolation(raw.key, result.violation), missing, unknown },
        { status: 400 },
      );
    }

    if (!("prompt" in result) || !result.prompt) {
      return Response.json({ error: "не удалось создать версию" }, { status: 500 });
    }

    return Response.json({ prompt: result.prompt });
  } catch (error) {
    return toResponse(error);
  }
}