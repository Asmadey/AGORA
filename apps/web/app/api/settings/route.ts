import {
  DEFAULT_MODELS,
  DEFAULT_REASONING,
  DEFAULT_SETTINGS,
  DEFAULT_TEMPERATURES,
  parseSettings,
  REASONING_EFFORTS,
  TEMPERATURE_STAGES,
  type TenantSettings,
} from "@/lib/settings";
import { withTenant } from "@/lib/server/db";
import { requireOwner, requireSession, toResponse } from "@/lib/server/guard";
import { encryptSecret, maskSecret, secretsAvailable } from "@/lib/server/secrets";

/**
 * Настройки арендатора (задача #27), этап 2 из 2.
 *
 * Хранилище в памяти процесса, стоявшее здесь до задачи #3, заменено на таблицу
 * settings. Появление сессии сняло причину заглушки: теперь есть tenant_id, от
 * чьего имени идёт запись, и RLS отвечает за то, что команда видит только свою
 * строку. Форма запроса и ответа, а также валидация в lib/settings.ts не
 * изменились — как и обещал комментарий этапа 1.
 *
 * ─── Кто что может ─────────────────────────────────────────────────────
 * Чтение — любой участник команды: значения влияют на все её прогоны, и member
 * должен видеть, по каким правилам считается его исследование.
 * Запись — только owner: смена модели транскрипции и потолка стоимости меняет
 * цену и длительность прогонов для всей команды.
 *
 * ─── Известное ограничение ─────────────────────────────────────────────
 * В схеме cost_cap_calls IS NULL означает «авто». Числовое значение при этом
 * хранить негде, поэтому после переключения на «авто» и перезагрузки страницы
 * ползунок показывает значение по умолчанию, а не последнее выбранное.
 * Кандидат на исправление — отдельная колонка settings.cost_cap_value; заводить
 * её вместе с миграцией аутентификации было бы не к месту.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface SettingsRow {
  cost_cap_calls: number | null;
  whisper_model: TenantSettings["whisperModel"];
  default_replication_count: number;
  provider_config: Record<string, unknown> | null;
  provider_api_key_hint: string | null;
}

/**
 * Температуры лежат в `provider_config`, а не в собственных колонках.
 *
 * Колонка заведена схемой с самого начала и до сих пор не использовалась ничем.
 * Шесть новых колонок под шесть стадий означали бы миграцию на каждую будущую
 * стадию конвейера — а стадии добавляются: этим же планом добавляется валидация
 * персон. Разбор всё равно идёт через `parseSettings`, поэтому мусор в jsonb
 * отсекается там же, где мусор из HTTP.
 */
function rowToSettings(row: SettingsRow): TenantSettings {
  const stored = (row.provider_config ?? {}) as Record<string, unknown>;

  const temperatures = { ...DEFAULT_TEMPERATURES };
  const raw = stored.temperatures;
  if (raw && typeof raw === "object") {
    for (const stage of TEMPERATURE_STAGES) {
      const value = (raw as Record<string, unknown>)[stage.key];
      if (typeof value === "number" && Number.isFinite(value)) {
        temperatures[stage.key] = value;
      }
    }
  }

  const models = { ...DEFAULT_MODELS };
  const rawModels = stored.models;
  if (rawModels && typeof rawModels === "object") {
    for (const role of ["text", "vision", "judge"] as const) {
      const value = (rawModels as Record<string, unknown>)[role];
      if (typeof value === "string") models[role] = value;
    }
  }

  function reasoningOf(key: string): TenantSettings["reasoning"] {
    const source = stored[key];
    const out = { ...DEFAULT_REASONING };
    if (!source || typeof source !== "object") return out;
    const r = source as Record<string, unknown>;
    if (typeof r.thinking === "boolean") out.thinking = r.thinking;
    if (REASONING_EFFORTS.includes(r.effort as never)) {
      out.effort = r.effort as TenantSettings["reasoning"]["effort"];
    }
    return out;
  }

  return {
    costCap: row.cost_cap_calls === null ? "auto" : "hard",
    costCapValue: row.cost_cap_calls ?? DEFAULT_SETTINGS.costCapValue,
    whisperModel: row.whisper_model,
    defaultReplication: row.default_replication_count as TenantSettings["defaultReplication"],
    temperatures,
    models,
    reasoning: reasoningOf("reasoning"),
    judgeReasoning: reasoningOf("judgeReasoning"),
    endpoint: typeof stored.endpoint === "string" ? stored.endpoint : "",
    // Только маска. Сам ключ не покидает сервер ни в одном ответе: даже
    // владельцу — потому что ответ уезжает в браузер, в его историю и в любой
    // прокси по дороге, а отозвать его оттуда нечем.
    apiKeyMask: row.provider_api_key_hint ?? envKeyMask(),
  };
}

/** Маска ключа из окружения — он действует, пока свой не задан. */
function envKeyMask(): string {
  return maskSecret(process.env.OPENAI_API_KEY ?? "");
}

export async function GET() {
  try {
    const { tenantId } = await requireSession();

    const settings = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<SettingsRow>(
        "SELECT cost_cap_calls, whisper_model, default_replication_count, provider_config, provider_api_key_hint FROM settings WHERE tenant_id = $1",
        [tenantId],
      );
      // Строки может не быть: команда заведена, настройки ни разу не сохранялись.
      // Это не ошибка — отдаём умолчания, те же, что показывает интерфейс.
      return rows[0] ? rowToSettings(rows[0]) : DEFAULT_SETTINGS;
    });

    return Response.json({ settings, persistence: "postgres" });
  } catch (error) {
    return toResponse(error);
  }
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

    const parsed = parseSettings(body);
    if (!parsed.ok) {
      return Response.json(
        { error: "настройки не прошли валидацию", details: parsed.errors },
        { status: 400 },
      );
    }

    const value = parsed.value;
    const costCapCalls = value.costCap === "auto" ? null : value.costCapValue;

    // ─── Ключ провайдера ──────────────────────────────────────────────────
    //
    // Приходит отдельным полем и только на запись: в ответе его нет никогда.
    // Пустое или отсутствующее поле означает «не менять» — иначе сохранение
    // любой соседней настройки стирало бы ключ, и заметили бы это на первом же
    // прогоне, уже потратив расшифровку.
    const rawKey = (body as { apiKey?: unknown })?.apiKey;
    let encryptedKey: Buffer | null = null;
    let keyHint: string | null = null;
    if (typeof rawKey === "string" && rawKey.trim()) {
      if (!secretsAvailable()) {
        return Response.json(
          {
            error:
              "SETTINGS_SECRET не задан в окружении: ключ негде зашифровать. " +
              "Задайте переменную одинаковой для web и worker — иначе воркер не " +
              "расшифрует то, что сохранит интерфейс",
          },
          { status: 400 },
        );
      }
      const plain = rawKey.trim();
      encryptedKey = encryptSecret(plain);
      keyHint = maskSecret(plain);
    }

    const settings = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<SettingsRow>(
        `INSERT INTO settings (tenant_id, cost_cap_calls, whisper_model,
                               default_replication_count, provider_config,
                               provider_api_key, provider_api_key_hint)
         -- При вставке сливать не с чем: строки ещё нет, и ссылка на
         -- settings.provider_config здесь была бы неразрешимой.
         VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
         ON CONFLICT (tenant_id) DO UPDATE SET
           cost_cap_calls            = EXCLUDED.cost_cap_calls,
           whisper_model             = EXCLUDED.whisper_model,
           default_replication_count = EXCLUDED.default_replication_count,
           -- Слияние, а не замена: в provider_config со временем лягут и другие
           -- настройки провайдера, и запись температур не должна стирать соседей.
           provider_config           = COALESCE(settings.provider_config, '{}'::jsonb) || $5::jsonb,
           -- COALESCE: пустое поле означает «не менять ключ». Иначе сохранение
           -- любой соседней настройки стирало бы его, и заметили бы это на
           -- первом же прогоне, уже потратив расшифровку.
           provider_api_key          = COALESCE($6, settings.provider_api_key),
           provider_api_key_hint     = COALESCE($7, settings.provider_api_key_hint),
           updated_at                = now()
         RETURNING cost_cap_calls, whisper_model, default_replication_count, provider_config,
                   provider_api_key_hint`,
        [
          tenantId,
          costCapCalls,
          value.whisperModel,
          value.defaultReplication,
          JSON.stringify({
            temperatures: value.temperatures,
            models: value.models,
            reasoning: value.reasoning,
            judgeReasoning: value.judgeReasoning,
            endpoint: value.endpoint,
          }),
          encryptedKey,
          keyHint,
        ],
      );
      return rowToSettings(rows[0]);
    });

    return Response.json({ settings, persistence: "postgres" });
  } catch (error) {
    return toResponse(error);
  }
}
