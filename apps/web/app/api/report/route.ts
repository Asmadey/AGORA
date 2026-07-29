import { NextRequest, NextResponse } from 'next/server';
import { generateReport } from '@/lib/ai-server';

export const runtime = 'nodejs';

export async function POST(req: NextRequest) {
  try {
    const { responses, survey } = await req.json();
    const report = await generateReport(responses, survey);
    return NextResponse.json({ report });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || 'error' }, { status: 500 });
  }
}
