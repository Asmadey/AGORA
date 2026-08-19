import { NextRequest, NextResponse } from "next/server";

import { requireSession, toResponse } from "@/lib/server/guard";

/**
 * POST /api/personas/generate
 *
 * Прокси к agent-core FastAPI: POST /api/personas/generate.
 * Генерация синтетических персон по методологии PRD §10.
 *
 * Тело: { size, seed, serial?, city?, segment?, use_llm? }
 * Ответ: { personas: PersonaDNA[], seed, size }
 *
 * ─── Про проверку сессии ────────────────────────────────────────────────────
 * Она появилась здесь 19.08.2026, после того как статическая проверка
 * `lib/tenant-isolation.test.ts` нашла единственный маршрут во всём API без
 * собственного `requireSession`.
 *
 * Открытой дверью наружу это не было: middleware закрыт по умолчанию, и
 * неавторизованный запрос сюда не доходит. Но защита была в один слой вместо
 * двух, а маршрут при этом ходит в воркер и умеет тратить вызовы модели
 * (`use_llm: true`). Любой участник любой команды мог позвать его в обход
 * ролей и тенант-контекста, и по ответу это было бы неотличимо от законного
 * вызова.
 *
 * ─── Чем этот маршрут отличается от /api/audience ───────────────────────────
 * Он ничего не сохраняет: отдаёт сгенерированное тело в ответ и забывает.
 * Наборы персон заводит `/api/audience` — там и тенант, и фоновая задача, и
 * запись в базу. Этот остаётся ради контракта OpenAPI и CDD-теста задачи #5.
 */
export const runtime = "nodejs";

const AGENT_CORE_URL = process.env.AGENT_CORE_URL || "http://localhost:8001";

export async function POST(req: NextRequest) {
  try {
    // Сессия проверяется ДО чтения тела: разбирать присланное от того, кого мы
    // не пускаем, незачем.
    await requireSession();

    const body = await req.json();

    const resp = await fetch(`${AGENT_CORE_URL}/api/personas/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      return NextResponse.json(err, { status: resp.status });
    }

    return NextResponse.json(await resp.json());
  } catch (e) {
    // Отказ гварда обязан доехать своим кодом (401/403), а не превратиться в
    // 502: «agent-core недоступен» вместо «вы не вошли» отправляет разбираться
    // не туда.
    const guarded = toResponse(e);
    if (guarded.status === 401 || guarded.status === 403) return guarded;

    return NextResponse.json(
      {
        error: e instanceof Error ? e.message : "agent-core unavailable",
        hint: "is AGENT_CORE_URL set?",
      },
      { status: 502 },
    );
  }
}
