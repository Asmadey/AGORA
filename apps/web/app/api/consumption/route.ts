import { aggregateByDay, totalsOf } from "@/lib/consumption";
import { CloudRuNotConfigured, fetchConsumption } from "@/lib/server/cloudru";
import { requireOwner, toResponse } from "@/lib/server/guard";

/**
 * Потребление и расходы за период — источник для раздела «Статистика».
 *
 * Только владелец: это деньги договора целиком, а не расходы конкретного
 * исследования. Участник команды видит свои прогоны, но не счёт компании.
 */

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export async function GET(request: Request) {
  try {
    await requireOwner();

    const params = new URL(request.url).searchParams;
    const from = params.get("from") ?? "";
    const to = params.get("to") ?? "";

    if (!ISO_DATE.test(from) || !ISO_DATE.test(to)) {
      return Response.json(
        { error: "нужны from и to в виде ГГГГ-ММ-ДД" },
        { status: 400 },
      );
    }
    if (from > to) {
      return Response.json({ error: "начало периода позже его конца" }, { status: 400 });
    }

    const rows = aggregateByDay(await fetchConsumption(from, to));
    return Response.json({ from, to, rows, totals: totalsOf(rows) });
  } catch (error) {
    if (error instanceof CloudRuNotConfigured) {
      // 501, а не 500: сервис жив, возможность не настроена. Разные коды
      // отправляют разбираться в разные места — в конфигурацию, а не в логи.
      return Response.json({ error: error.message }, { status: 501 });
    }
    return toResponse(error);
  }
}
