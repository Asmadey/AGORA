import { NextRequest, NextResponse } from 'next/server';
import { generateAudience } from '@/lib/ai-server';

export const runtime = 'nodejs';

export async function POST(req: NextRequest) {
  try {
    const { size, context, options } = await req.json();
    const agents = await generateAudience(size ?? 20, context, options);
    return NextResponse.json({ agents });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || 'error' }, { status: 500 });
  }
}
