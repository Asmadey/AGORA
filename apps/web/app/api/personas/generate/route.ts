import { NextRequest, NextResponse } from 'next/server';

/**
 * POST /api/personas/generate
 *
 * Прокси к agent-core FastAPI: POST /api/personas/generate.
 * Генерация синтетических персон по методологии PRD §10.
 *
 * Тело: { size, seed, serial?, city?, segment?, use_llm? }
 * Ответ: { personas: PersonaDNA[], seed, size }
 */
export const runtime = 'nodejs';

const AGENT_CORE_URL = process.env.AGENT_CORE_URL || 'http://localhost:8001';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const resp = await fetch(`${AGENT_CORE_URL}/api/personas/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      return NextResponse.json(err, { status: resp.status });
    }

    const data = await resp.json();
    return NextResponse.json(data);
  } catch (e: any) {
    // Fallback: если agent-core не поднят — возвращаем ошибку с контекстом
    return NextResponse.json(
      { error: e?.message || 'agent-core unavailable', hint: 'is AGENT_CORE_URL set?' },
      { status: 502 },
    );
  }
}