import { NextRequest, NextResponse } from 'next/server';
import { simulateSurvey } from '@/lib/ai-server';

export const runtime = 'nodejs';

export async function POST(req: NextRequest) {
  try {
    const { agents, project, survey } = await req.json();
    const responses = await simulateSurvey(agents, project, survey);
    return NextResponse.json({ responses });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || 'error' }, { status: 500 });
  }
}
