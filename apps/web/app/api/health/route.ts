import { NextResponse } from "next/server";

/**
 * Health-эндпоинт для docker compose healthcheck (задача #1).
 *
 * Намеренно не ходит в БД: healthcheck должен отвечать на вопрос «процесс Next.js
 * поднялся и обслуживает запросы», а не «вся система здорова». Готовность
 * хранилищ проверяют их собственные healthcheck'и в compose, и они стоят
 * в depends_on у web — то есть web стартует уже после них.
 */
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    service: "agora-web",
    timestamp: new Date().toISOString(),
  });
}
