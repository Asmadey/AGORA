import { NextRequest, NextResponse } from 'next/server';
import { generateNewsAnalysis } from '@/lib/ai-server';

export const runtime = 'nodejs';

export async function POST(req: NextRequest) {
  try {
    const { agents, realNews } = await req.json();
    const result = await generateNewsAnalysis(agents || [], realNews || []);
    return NextResponse.json(result);
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || 'error' }, { status: 500 });
  }
}
