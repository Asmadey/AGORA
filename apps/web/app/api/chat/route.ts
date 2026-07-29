import { NextRequest, NextResponse } from 'next/server';
import { chatWithAudience } from '@/lib/ai-server';

export const runtime = 'nodejs';

export async function POST(req: NextRequest) {
  try {
    const { message, history, agents, responses, selectedAgentId, projectContext } =
      await req.json();
    const response = await chatWithAudience(
      message,
      history || [],
      agents || [],
      responses || [],
      selectedAgentId ?? 'all',
      projectContext
    );
    return NextResponse.json({ response });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || 'error' }, { status: 500 });
  }
}
