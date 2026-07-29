import { DEFAULT_SETTINGS, parseSettings, type TenantSettings } from "@/lib/settings";
import { withTenant } from "@/lib/server/db";
import { requireOwner, requireSession, toResponse } from "@/lib/server/guard";

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
}

function rowToSettings(row: SettingsRow): TenantSettings {
  return {
    costCap: row.cost_cap_calls === null ? "auto" : "hard",
    costCapValue: row.cost_cap_calls ?? DEFAULT_SETTINGS.costCapValue,
    whisperModel: row.whisper_model,
    defaultReplication: row.default_replication_count as TenantSettings["defaultReplication"],
  };
}

export async function GET() {
  try {
    const { tenantId } = await requireSession();

    const settings = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<SettingsRow>(
        "SELECT cost_cap_calls, whisper_model, default_replication_count FROM settings WHERE tenant_id = $1",
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

    const settings = await withTenant(tenantId, async (client) => {
      const { rows } = await client.query<SettingsRow>(
        `INSERT INTO settings (tenant_id, cost_cap_calls, whisper_model, default_replication_count)
         VALUES ($1, $2, $3, $4)
         ON CONFLICT (tenant_id) DO UPDATE SET
           cost_cap_calls            = EXCLUDED.cost_cap_calls,
           whisper_model             = EXCLUDED.whisper_model,
           default_replication_count = EXCLUDED.default_replication_count,
           updated_at                = now()
         RETURNING cost_cap_calls, whisper_model, default_replication_count`,
        [tenantId, costCapCalls, value.whisperModel, value.defaultReplication],
      );
      return rowToSettings(rows[0]);
    });

    return Response.json({ settings, persistence: "postgres" });
  } catch (error) {
    return toResponse(error);
  }
}
